"""Task 13 审核工作流的正式事务 Service。"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.models import AccountStatus, User
from apps.accounts.roles import (
    ROLE_EDITOR,
    ROLE_KNOWLEDGE_ADMIN,
    ROLE_REVIEWER,
    SYSTEM_ROLE_BY_CODE,
)
from apps.audit.models import AuditEvent, AuditEventType
from apps.knowledge.models import (
    Article,
    ArticleVersion,
    ReviewDecision,
    ReviewerSpaceScope,
    ReviewRecord,
    ReviewType,
    VersionStatus,
)

from .models import (
    IdempotencyOperation,
    IdempotencyStatus,
    WorkflowEventType,
    WorkflowIdempotencyRecord,
    WorkflowOutboxEvent,
)

INVALID_INPUT = "INVALID_INPUT"
IDENTITY_DENIED = "IDENTITY_DENIED"
SUBMIT_FORBIDDEN = "SUBMIT_FORBIDDEN"
ARTICLE_NOT_FOUND_OR_INACCESSIBLE = "ARTICLE_NOT_FOUND_OR_INACCESSIBLE"
DRAFT_NOT_CURRENT = "DRAFT_NOT_CURRENT"
DRAFT_CONFLICT = "DRAFT_CONFLICT"
IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
IDEMPOTENCY_IN_PROGRESS = "IDEMPOTENCY_IN_PROGRESS"
WORKFLOW_UNAVAILABLE = "WORKFLOW_UNAVAILABLE"
REVIEW_SUBMITTED = "REVIEW_SUBMITTED"
REJECT_FORBIDDEN = "REJECT_FORBIDDEN"
VERSION_NOT_FOUND_OR_INACCESSIBLE = "VERSION_NOT_FOUND_OR_INACCESSIBLE"
SELF_REVIEW_FORBIDDEN = "SELF_REVIEW_FORBIDDEN"
VERSION_NOT_IN_REVIEW = "VERSION_NOT_IN_REVIEW"
REVIEW_REJECTED = "REVIEW_REJECTED"
APPROVE_PUBLISH_FORBIDDEN = "APPROVE_PUBLISH_FORBIDDEN"
PUBLISH_STATE_INCONSISTENT = "PUBLISH_STATE_INCONSISTENT"
REVIEW_APPROVED_PUBLISHED = "REVIEW_APPROVED_PUBLISHED"

_KB_NO_PATTERN = re.compile(r"^KB-[0-9]{6}$")
_EDITOR_ROLE_NAME = SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name
_ADMIN_ROLE_NAME = SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name
_REVIEWER_ROLE_NAME = SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name
_SUBMIT_PERMISSION = "knowledge.submit_articleversion"
_REJECT_PERMISSION = "knowledge.reject_articleversion"
_APPROVE_PERMISSION = "knowledge.approve_articleversion"
_PUBLISH_PERMISSION = "knowledge.publish_articleversion"


class SubmitArticleForReviewError(Exception):
    """提交审核失败的稳定 Service 异常；不暴露数据库或对象内部信息。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.public_message = message
        super().__init__(message)


@dataclass(frozen=True)
class SubmitReviewResult:
    """首次提交与合法幂等重放共享的不可变业务结果。"""

    kb_no: str
    article_id: UUID
    version_id: UUID
    version_no: int
    status: str
    lock_version: int
    submitted_at: datetime

    def to_payload(self) -> dict[str, object]:
        return {
            "kb_no": self.kb_no,
            "article_id": str(self.article_id),
            "version_id": str(self.version_id),
            "version_no": self.version_no,
            "status": self.status,
            "lock_version": self.lock_version,
            "submitted_at": self.submitted_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> SubmitReviewResult:
        try:
            result = cls(
                kb_no=str(payload["kb_no"]),
                article_id=UUID(str(payload["article_id"])),
                version_id=UUID(str(payload["version_id"])),
                version_no=int(payload["version_no"]),
                status=str(payload["status"]),
                lock_version=int(payload["lock_version"]),
                submitted_at=datetime.fromisoformat(str(payload["submitted_at"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SubmitArticleForReviewError(
                WORKFLOW_UNAVAILABLE,
                "提交审核结果暂时不可用，请稍后重试。",
            ) from exc
        if (
            result.version_no < 1
            or result.lock_version < 1
            or result.status != VersionStatus.IN_REVIEW
            or not timezone.is_aware(result.submitted_at)
        ):
            raise SubmitArticleForReviewError(
                WORKFLOW_UNAVAILABLE,
                "提交审核结果暂时不可用，请稍后重试。",
            )
        return result


class RejectArticleVersionError(Exception):
    """驳回审核失败的稳定 Service 异常；不暴露数据库或对象内部信息。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.public_message = message
        super().__init__(message)


@dataclass(frozen=True)
class RejectReviewResult:
    """首次驳回与合法幂等重放共享的不可变业务结果。"""

    kb_no: str
    article_id: UUID
    rejected_version_id: UUID
    rejected_version_no: int
    rejected_status: str
    review_record_id: UUID
    successor_draft_id: UUID
    successor_version_no: int
    successor_status: str
    successor_lock_version: int

    def to_payload(self) -> dict[str, object]:
        return {
            "kb_no": self.kb_no,
            "article_id": str(self.article_id),
            "rejected_version_id": str(self.rejected_version_id),
            "rejected_version_no": self.rejected_version_no,
            "rejected_status": self.rejected_status,
            "review_record_id": str(self.review_record_id),
            "successor_draft_id": str(self.successor_draft_id),
            "successor_version_no": self.successor_version_no,
            "successor_status": self.successor_status,
            "successor_lock_version": self.successor_lock_version,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> RejectReviewResult:
        try:
            result = cls(
                kb_no=str(payload["kb_no"]),
                article_id=UUID(str(payload["article_id"])),
                rejected_version_id=UUID(str(payload["rejected_version_id"])),
                rejected_version_no=int(payload["rejected_version_no"]),
                rejected_status=str(payload["rejected_status"]),
                review_record_id=UUID(str(payload["review_record_id"])),
                successor_draft_id=UUID(str(payload["successor_draft_id"])),
                successor_version_no=int(payload["successor_version_no"]),
                successor_status=str(payload["successor_status"]),
                successor_lock_version=int(payload["successor_lock_version"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RejectArticleVersionError(
                WORKFLOW_UNAVAILABLE,
                "审核驳回结果暂时不可用，请稍后重试。",
            ) from exc
        if (
            result.rejected_version_no < 1
            or result.rejected_status != VersionStatus.REJECTED
            or result.successor_version_no < 1
            or result.successor_status != VersionStatus.DRAFT
            or result.successor_lock_version != 1
        ):
            raise RejectArticleVersionError(
                WORKFLOW_UNAVAILABLE,
                "审核驳回结果暂时不可用，请稍后重试。",
            )
        return result


class ApprovePublishArticleVersionError(Exception):
    """批准发布失败的稳定 Service 异常；不暴露数据库或对象内部信息。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.public_message = message
        super().__init__(message)


@dataclass(frozen=True)
class ApprovePublishResult:
    """首次批准发布与合法幂等重放共享的不可变业务结果。"""

    kb_no: str
    article_id: UUID
    published_version_id: UUID
    published_version_no: int
    published_status: str
    published_at: datetime
    previous_published_version_id: UUID | None
    review_record_id: UUID
    successor_draft_id: UUID
    successor_version_no: int
    successor_status: str
    successor_lock_version: int

    def to_payload(self) -> dict[str, object]:
        return {
            "kb_no": self.kb_no,
            "article_id": str(self.article_id),
            "published_version_id": str(self.published_version_id),
            "published_version_no": self.published_version_no,
            "published_status": self.published_status,
            "published_at": self.published_at.isoformat(),
            "previous_published_version_id": (
                str(self.previous_published_version_id)
                if self.previous_published_version_id is not None
                else None
            ),
            "review_record_id": str(self.review_record_id),
            "successor_draft_id": str(self.successor_draft_id),
            "successor_version_no": self.successor_version_no,
            "successor_status": self.successor_status,
            "successor_lock_version": self.successor_lock_version,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> ApprovePublishResult:
        try:
            previous_value = payload["previous_published_version_id"]
            result = cls(
                kb_no=str(payload["kb_no"]),
                article_id=UUID(str(payload["article_id"])),
                published_version_id=UUID(str(payload["published_version_id"])),
                published_version_no=int(payload["published_version_no"]),
                published_status=str(payload["published_status"]),
                published_at=datetime.fromisoformat(str(payload["published_at"])),
                previous_published_version_id=(
                    UUID(str(previous_value)) if previous_value is not None else None
                ),
                review_record_id=UUID(str(payload["review_record_id"])),
                successor_draft_id=UUID(str(payload["successor_draft_id"])),
                successor_version_no=int(payload["successor_version_no"]),
                successor_status=str(payload["successor_status"]),
                successor_lock_version=int(payload["successor_lock_version"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ApprovePublishArticleVersionError(
                WORKFLOW_UNAVAILABLE,
                "审核发布结果暂时不可用，请稍后重试。",
            ) from exc
        if (
            result.published_version_no < 1
            or result.published_status != VersionStatus.PUBLISHED
            or not timezone.is_aware(result.published_at)
            or result.successor_version_no < 1
            or result.successor_status != VersionStatus.DRAFT
            or result.successor_lock_version != 1
        ):
            raise ApprovePublishArticleVersionError(
                WORKFLOW_UNAVAILABLE,
                "审核发布结果暂时不可用，请稍后重试。",
            )
        return result


def _raise_invalid(message: str) -> None:
    raise SubmitArticleForReviewError(INVALID_INPUT, message)


def _validate_idempotency_key(*, key, raise_invalid) -> None:
    if not isinstance(key, str):
        raise_invalid("幂等键格式无效。")
    if (
        not key
        or not key.strip()
        or key != key.strip()
        or len(key) > 128
        or any(unicodedata.category(character) == "Cc" for character in key)
    ):
        raise_invalid("幂等键格式无效。")


def _validate_inputs(*, kb_no, draft_id, expected_lock_version, idempotency_key):
    if not isinstance(kb_no, str) or not _KB_NO_PATTERN.fullmatch(kb_no):
        _raise_invalid("知识编号格式无效。")
    try:
        normalized_draft_id = ArticleVersion._meta.pk.to_python(draft_id)
    except (TypeError, ValueError, ValidationError) as exc:
        try:
            _raise_invalid("草稿标识格式无效。")
        except SubmitArticleForReviewError as error:
            raise error from exc
    if (
        not isinstance(expected_lock_version, int)
        or isinstance(expected_lock_version, bool)
        or expected_lock_version < 1
    ):
        _raise_invalid("草稿锁版本必须是正整数。")
    _validate_idempotency_key(key=idempotency_key, raise_invalid=_raise_invalid)
    return normalized_draft_id


def _is_saved_user(actor) -> bool:
    return isinstance(actor, User) and actor.pk is not None and not actor._state.adding


def _resolve_submit_actor(actor) -> tuple[User, bool]:
    if not _is_saved_user(actor) or not actor.is_authenticated:
        raise SubmitArticleForReviewError(
            IDENTITY_DENIED,
            "当前账号不能提交审核。",
        )
    try:
        current_actor = User.objects.get(pk=actor.pk)
    except User.DoesNotExist as exc:
        raise SubmitArticleForReviewError(
            IDENTITY_DENIED,
            "当前账号不能提交审核。",
        ) from exc
    if not current_actor.is_active or current_actor.account_status != AccountStatus.ACTIVE:
        raise SubmitArticleForReviewError(
            IDENTITY_DENIED,
            "当前账号不能提交审核。",
        )

    role_names = set(
        current_actor.groups.filter(name__in=(_EDITOR_ROLE_NAME, _ADMIN_ROLE_NAME)).values_list(
            "name", flat=True
        )
    )
    is_admin = _ADMIN_ROLE_NAME in role_names
    if not (is_admin or _EDITOR_ROLE_NAME in role_names) or not current_actor.has_perm(
        _SUBMIT_PERMISSION
    ):
        raise SubmitArticleForReviewError(
            SUBMIT_FORBIDDEN,
            "没有提交文章审核的权限。",
        )
    return current_actor, is_admin


def _validate_article_access(*, actor: User, article: Article, is_admin: bool) -> None:
    if not article.space.is_active or not (
        is_admin or article.owner_id == actor.pk or article.space.owner_id == actor.pk
    ):
        raise SubmitArticleForReviewError(
            ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
            "文章不存在或不可访问。",
        )


def _resolve_accessible_article(*, actor: User, kb_no: str, is_admin: bool) -> Article:
    try:
        article = Article.objects.select_related("space").get(kb_no=kb_no)
    except Article.DoesNotExist as exc:
        raise SubmitArticleForReviewError(
            ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
            "文章不存在或不可访问。",
        ) from exc
    _validate_article_access(actor=actor, article=article, is_admin=is_admin)
    return article


def _build_fingerprint(*, kb_no: str, draft_id: UUID, expected_lock_version: int) -> str:
    canonical = json.dumps(
        {
            "draft_id": str(draft_id),
            "expected_lock_version": expected_lock_version,
            "kb_no": kb_no,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _load_idempotency_record(*, actor: User, operation: str, key: str):
    return (
        WorkflowIdempotencyRecord.objects.select_for_update()
        .filter(
            actor=actor,
            operation=operation,
            key=key,
        )
        .first()
    )


def _prepare_idempotency(
    *,
    actor: User,
    operation: str,
    key: str,
    fingerprint: str,
    error_type,
    unavailable_message: str,
) -> tuple[WorkflowIdempotencyRecord, bool]:
    existing = _load_idempotency_record(actor=actor, operation=operation, key=key)
    if existing is not None:
        return existing, False

    try:
        # 独立 savepoint 只隔离唯一键竞争；外层事务仍覆盖全部业务写入。
        with transaction.atomic():
            record = WorkflowIdempotencyRecord.objects.create(
                actor=actor,
                operation=operation,
                key=key,
                request_fingerprint=fingerprint,
            )
        return record, True
    except IntegrityError as exc:
        # 并发首次请求可能同时看不到记录；数据库唯一约束决定胜者。
        existing = _load_idempotency_record(actor=actor, operation=operation, key=key)
        if existing is None:
            raise error_type(
                WORKFLOW_UNAVAILABLE,
                unavailable_message,
            ) from exc
        return existing, False


def _resolve_idempotency(
    *,
    record: WorkflowIdempotencyRecord,
    created: bool,
    fingerprint: str,
    article: Article,
    draft_id: UUID,
) -> SubmitReviewResult | None:
    if created:
        return None
    if record.request_fingerprint != fingerprint:
        raise SubmitArticleForReviewError(
            IDEMPOTENCY_CONFLICT,
            "该幂等键已用于不同的提交请求。",
        )
    if record.status == IdempotencyStatus.IN_PROGRESS:
        raise SubmitArticleForReviewError(
            IDEMPOTENCY_IN_PROGRESS,
            "相同提交请求正在处理中。",
        )
    if record.status != IdempotencyStatus.COMPLETED or record.result_code != REVIEW_SUBMITTED:
        raise SubmitArticleForReviewError(
            WORKFLOW_UNAVAILABLE,
            "提交审核结果暂时不可用，请稍后重试。",
        )

    result = SubmitReviewResult.from_payload(record.result_payload)
    if (
        result.kb_no != article.kb_no
        or result.article_id != article.pk
        or result.version_id != draft_id
    ):
        raise SubmitArticleForReviewError(
            WORKFLOW_UNAVAILABLE,
            "提交审核结果暂时不可用，请稍后重试。",
        )
    return result


def _lock_current_draft(
    *,
    article: Article,
    draft_id: UUID,
    expected_lock_version: int,
) -> ArticleVersion:
    if article.latest_working_version_id != draft_id:
        raise SubmitArticleForReviewError(
            DRAFT_NOT_CURRENT,
            "该版本已不是当前工作草稿。",
        )
    try:
        draft = ArticleVersion.objects.select_for_update().get(
            pk=draft_id,
            article_id=article.pk,
        )
    except ArticleVersion.DoesNotExist as exc:
        raise SubmitArticleForReviewError(
            DRAFT_NOT_CURRENT,
            "该版本已不是当前工作草稿。",
        ) from exc
    if draft.status != VersionStatus.DRAFT:
        raise SubmitArticleForReviewError(
            DRAFT_NOT_CURRENT,
            "该版本已不是当前工作草稿。",
        )
    if draft.lock_version != expected_lock_version:
        raise SubmitArticleForReviewError(
            DRAFT_CONFLICT,
            "草稿已被其他操作更新，请刷新后重试。",
        )
    return draft


def _transition_to_in_review(*, draft: ArticleVersion, actor: User) -> SubmitReviewResult:
    submitted_at = timezone.now()
    draft.status = VersionStatus.IN_REVIEW
    draft.submitted_by = actor
    draft.submitted_at = submitted_at
    draft.lock_version += 1
    draft.full_clean()
    draft.save(
        update_fields=(
            "status",
            "submitted_by",
            "submitted_at",
            "lock_version",
            "updated_at",
        )
    )
    return SubmitReviewResult(
        kb_no=draft.article.kb_no,
        article_id=draft.article_id,
        version_id=draft.pk,
        version_no=draft.version_no,
        status=draft.status,
        lock_version=draft.lock_version,
        submitted_at=submitted_at,
    )


def _clear_working_pointer(*, article: Article, actor: User) -> None:
    article.latest_working_version = None
    article.updated_by = actor
    article.full_clean()
    article.save(
        update_fields=(
            "latest_working_version",
            "updated_by",
            "updated_at",
        )
    )


def _write_submission_evidence(
    *,
    actor: User,
    article: Article,
    draft: ArticleVersion,
    result: SubmitReviewResult,
) -> None:
    AuditEvent.objects.create(
        event_type=AuditEventType.REVIEW_SUBMITTED,
        actor=actor,
        article=article,
        article_version=draft,
        metadata={
            "kb_no": article.kb_no,
            "version_no": draft.version_no,
            "space_id": str(article.space_id),
            "lock_version": draft.lock_version,
        },
    )
    WorkflowOutboxEvent.objects.create(
        event_type=WorkflowEventType.REVIEW_SUBMITTED,
        dedupe_key=f"review_submitted:{draft.pk}",
        payload={
            "kb_no": article.kb_no,
            "article_id": str(article.pk),
            "version_id": str(draft.pk),
            "version_no": draft.version_no,
            "space_id": str(article.space_id),
            "actor_id": str(actor.pk),
        },
    )
    if result.status != VersionStatus.IN_REVIEW:
        raise SubmitArticleForReviewError(
            WORKFLOW_UNAVAILABLE,
            "提交审核结果暂时不可用，请稍后重试。",
        )


def _complete_idempotency(
    *,
    record: WorkflowIdempotencyRecord,
    result: SubmitReviewResult,
) -> None:
    record.status = IdempotencyStatus.COMPLETED
    record.result_code = REVIEW_SUBMITTED
    record.result_payload = result.to_payload()
    record.full_clean()
    record.save(
        update_fields=(
            "status",
            "result_code",
            "result_payload",
            "updated_at",
        )
    )


def _submit_in_transaction(
    *,
    original_actor,
    accessible_article: Article,
    kb_no: str,
    draft_id: UUID,
    expected_lock_version: int,
    idempotency_key: str,
    fingerprint: str,
) -> SubmitReviewResult:
    with transaction.atomic():
        try:
            locked_article = (
                Article.objects.select_for_update()
                .select_related("space", "current_published_version")
                .get(pk=accessible_article.pk, kb_no=kb_no)
            )
        except Article.DoesNotExist as exc:
            raise SubmitArticleForReviewError(
                ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
                "文章不存在或不可访问。",
            ) from exc

        current_actor, is_admin = _resolve_submit_actor(original_actor)
        _validate_article_access(
            actor=current_actor,
            article=locked_article,
            is_admin=is_admin,
        )
        idempotency, created = _prepare_idempotency(
            actor=current_actor,
            operation=IdempotencyOperation.SUBMIT,
            key=idempotency_key,
            fingerprint=fingerprint,
            error_type=SubmitArticleForReviewError,
            unavailable_message="提交审核暂时不可用，请稍后重试。",
        )
        replay = _resolve_idempotency(
            record=idempotency,
            created=created,
            fingerprint=fingerprint,
            article=locked_article,
            draft_id=draft_id,
        )
        if replay is not None:
            return replay

        draft = _lock_current_draft(
            article=locked_article,
            draft_id=draft_id,
            expected_lock_version=expected_lock_version,
        )
        result = _transition_to_in_review(draft=draft, actor=current_actor)
        _clear_working_pointer(article=locked_article, actor=current_actor)
        _write_submission_evidence(
            actor=current_actor,
            article=locked_article,
            draft=draft,
            result=result,
        )
        _complete_idempotency(record=idempotency, result=result)
        return result


def submit_article_for_review(
    *,
    actor,
    kb_no,
    draft_id,
    expected_lock_version,
    idempotency_key,
) -> SubmitReviewResult:
    """原子提交服务器当前 DRAFT，并写入幂等、审计与 Outbox 证据。"""
    try:
        current_actor, is_admin = _resolve_submit_actor(actor)
        normalized_draft_id = _validate_inputs(
            kb_no=kb_no,
            draft_id=draft_id,
            expected_lock_version=expected_lock_version,
            idempotency_key=idempotency_key,
        )
        accessible_article = _resolve_accessible_article(
            actor=current_actor,
            kb_no=kb_no,
            is_admin=is_admin,
        )
        fingerprint = _build_fingerprint(
            kb_no=kb_no,
            draft_id=normalized_draft_id,
            expected_lock_version=expected_lock_version,
        )
        return _submit_in_transaction(
            original_actor=actor,
            accessible_article=accessible_article,
            kb_no=kb_no,
            draft_id=normalized_draft_id,
            expected_lock_version=expected_lock_version,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )
    except SubmitArticleForReviewError:
        raise
    except (ValidationError, DatabaseError) as exc:
        raise SubmitArticleForReviewError(
            WORKFLOW_UNAVAILABLE,
            "提交审核暂时不可用，请稍后重试。",
        ) from exc


def _raise_reject_invalid(message: str) -> None:
    raise RejectArticleVersionError(INVALID_INPUT, message)


def _validate_reject_inputs(*, version_id, comment, idempotency_key) -> tuple[UUID, str]:
    try:
        normalized_version_id = ArticleVersion._meta.pk.to_python(version_id)
    except (TypeError, ValueError, ValidationError) as exc:
        try:
            _raise_reject_invalid("文章版本标识格式无效。")
        except RejectArticleVersionError as error:
            raise error from exc
    if normalized_version_id is None:
        _raise_reject_invalid("文章版本标识格式无效。")
    if not isinstance(comment, str):
        _raise_reject_invalid("驳回原因格式无效。")
    normalized_comment = comment.strip()
    if not normalized_comment:
        _raise_reject_invalid("驳回原因不能为空。")
    _validate_idempotency_key(key=idempotency_key, raise_invalid=_raise_reject_invalid)
    return normalized_version_id, normalized_comment


def _resolve_reviewer_actor(
    actor,
    *,
    required_permissions: tuple[str, ...],
    error_type,
    forbidden_code: str,
    identity_message: str,
    forbidden_message: str,
) -> User:
    if not _is_saved_user(actor) or not actor.is_authenticated:
        raise error_type(
            IDENTITY_DENIED,
            identity_message,
        )
    try:
        current_actor = User.objects.get(pk=actor.pk)
    except User.DoesNotExist as exc:
        raise error_type(
            IDENTITY_DENIED,
            identity_message,
        ) from exc
    if not current_actor.is_active or current_actor.account_status != AccountStatus.ACTIVE:
        raise error_type(
            IDENTITY_DENIED,
            identity_message,
        )
    if not current_actor.groups.filter(name=_REVIEWER_ROLE_NAME).exists() or not (
        current_actor.has_perms(required_permissions)
    ):
        raise error_type(
            forbidden_code,
            forbidden_message,
        )
    return current_actor


def _resolve_reject_actor(actor) -> User:
    return _resolve_reviewer_actor(
        actor,
        required_permissions=(_REJECT_PERMISSION,),
        error_type=RejectArticleVersionError,
        forbidden_code=REJECT_FORBIDDEN,
        identity_message="当前账号不能执行审核驳回。",
        forbidden_message="没有驳回文章版本的权限。",
    )


def _validate_reviewer_scope(
    *,
    actor: User,
    article: Article,
    error_type=RejectArticleVersionError,
) -> None:
    if (
        not article.space.is_active
        or not ReviewerSpaceScope.objects.filter(
            reviewer=actor,
            space_id=article.space_id,
            is_active=True,
        ).exists()
    ):
        raise error_type(
            VERSION_NOT_FOUND_OR_INACCESSIBLE,
            "文章版本不存在或不可访问。",
        )


def _validate_self_review(
    *,
    actor: User,
    target: ArticleVersion,
    error_type=RejectArticleVersionError,
) -> None:
    if actor.pk in (target.created_by_id, target.submitted_by_id):
        raise error_type(
            SELF_REVIEW_FORBIDDEN,
            "不能审核自己创建或提交的文章版本。",
        )


def _resolve_reject_target(*, actor: User, version_id: UUID) -> ArticleVersion:
    try:
        target = ArticleVersion.objects.select_related("article__space").get(pk=version_id)
    except ArticleVersion.DoesNotExist as exc:
        raise RejectArticleVersionError(
            VERSION_NOT_FOUND_OR_INACCESSIBLE,
            "文章版本不存在或不可访问。",
        ) from exc
    _validate_reviewer_scope(actor=actor, article=target.article)
    _validate_self_review(actor=actor, target=target)
    return target


def _build_reject_fingerprint(*, version_id: UUID, comment: str) -> str:
    canonical = json.dumps(
        {
            "comment": comment,
            "version_id": str(version_id),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _resolve_reject_idempotency(
    *,
    record: WorkflowIdempotencyRecord,
    created: bool,
    fingerprint: str,
    article: Article,
    version_id: UUID,
) -> RejectReviewResult | None:
    if created:
        return None
    if record.request_fingerprint != fingerprint:
        raise RejectArticleVersionError(
            IDEMPOTENCY_CONFLICT,
            "该幂等键已用于不同的驳回请求。",
        )
    if record.status == IdempotencyStatus.IN_PROGRESS:
        raise RejectArticleVersionError(
            IDEMPOTENCY_IN_PROGRESS,
            "相同驳回请求正在处理中。",
        )
    if record.status != IdempotencyStatus.COMPLETED or record.result_code != REVIEW_REJECTED:
        raise RejectArticleVersionError(
            WORKFLOW_UNAVAILABLE,
            "审核驳回结果暂时不可用，请稍后重试。",
        )
    result = RejectReviewResult.from_payload(record.result_payload)
    if (
        result.kb_no != article.kb_no
        or result.article_id != article.pk
        or result.rejected_version_id != version_id
    ):
        raise RejectArticleVersionError(
            WORKFLOW_UNAVAILABLE,
            "审核驳回结果暂时不可用，请稍后重试。",
        )
    return result


def _lock_review_target(
    *,
    article: Article,
    version_id: UUID,
    error_type=RejectArticleVersionError,
) -> ArticleVersion:
    try:
        target = ArticleVersion.objects.select_for_update().get(
            pk=version_id,
            article_id=article.pk,
        )
    except ArticleVersion.DoesNotExist as exc:
        raise error_type(
            VERSION_NOT_FOUND_OR_INACCESSIBLE,
            "文章版本不存在或不可访问。",
        ) from exc
    if target.status != VersionStatus.IN_REVIEW:
        raise error_type(
            VERSION_NOT_IN_REVIEW,
            "该文章版本已不处于待审核状态。",
        )
    return target


def _create_rejection_record(
    *,
    target: ArticleVersion,
    actor: User,
    comment: str,
) -> ReviewRecord:
    review = ReviewRecord(
        article_version=target,
        review_type=ReviewType.CONTENT_REVIEW,
        reviewer=actor,
        decision=ReviewDecision.REJECTED,
        comment=comment,
    )
    review.full_clean()
    review.save(force_insert=True)
    return review


def _transition_to_rejected(*, target: ArticleVersion) -> None:
    target.status = VersionStatus.REJECTED
    target.full_clean()
    target.save(update_fields=("status", "updated_at"))


def _next_reject_version_no(*, article: Article) -> int:
    max_version_no = article.versions.aggregate(max_no=Max("version_no"))["max_no"]
    if not isinstance(max_version_no, int) or isinstance(max_version_no, bool):
        raise RejectArticleVersionError(
            WORKFLOW_UNAVAILABLE,
            "审核驳回暂时不可用，请稍后重试。",
        )
    return max_version_no + 1


def _create_successor_draft(*, article: Article, target: ArticleVersion) -> ArticleVersion:
    successor = ArticleVersion(
        article=article,
        version_no=_next_reject_version_no(article=article),
        status=VersionStatus.DRAFT,
        lock_version=1,
        title=target.title,
        summary=target.summary,
        applicable_scope=deepcopy(target.applicable_scope),
        body=deepcopy(target.body),
        body_plaintext=target.body_plaintext,
        change_summary=f"基于被驳回版本 v{target.version_no} 继续编辑",
        restored_from_version=None,
        created_by=target.submitted_by or target.created_by,
        submitted_by=None,
        submitted_at=None,
        published_at=None,
    )
    successor.full_clean(validate_unique=False, validate_constraints=False)
    successor.save(force_insert=True)
    return successor


def _switch_rejected_successor(
    *,
    article: Article,
    successor: ArticleVersion,
    actor: User,
) -> None:
    article.latest_working_version = successor
    article.updated_by = actor
    article.full_clean()
    article.save(
        update_fields=(
            "latest_working_version",
            "updated_by",
            "updated_at",
        )
    )


def _write_rejection_evidence(
    *,
    actor: User,
    article: Article,
    target: ArticleVersion,
    review: ReviewRecord,
    successor: ArticleVersion,
) -> None:
    AuditEvent.objects.create(
        event_type=AuditEventType.REVIEW_REJECTED,
        actor=actor,
        article=article,
        article_version=target,
        metadata={
            "kb_no": article.kb_no,
            "version_no": target.version_no,
            "space_id": str(article.space_id),
            "review_record_id": str(review.pk),
            "successor_draft_id": str(successor.pk),
            "successor_version_no": successor.version_no,
        },
    )
    WorkflowOutboxEvent.objects.create(
        event_type=WorkflowEventType.REVIEW_REJECTED,
        dedupe_key=f"review_rejected:{target.pk}",
        payload={
            "article_id": str(article.pk),
            "kb_no": article.kb_no,
            "version_id": str(target.pk),
            "version_no": target.version_no,
            "space_id": str(article.space_id),
            "reviewer_id": str(actor.pk),
            "review_record_id": str(review.pk),
            "successor_draft_id": str(successor.pk),
            "successor_version_no": successor.version_no,
            "submitted_by_id": str(target.submitted_by_id),
        },
    )


def _complete_reject_idempotency(
    *,
    record: WorkflowIdempotencyRecord,
    result: RejectReviewResult,
) -> None:
    record.status = IdempotencyStatus.COMPLETED
    record.result_code = REVIEW_REJECTED
    record.result_payload = result.to_payload()
    record.full_clean()
    record.save(
        update_fields=(
            "status",
            "result_code",
            "result_payload",
            "updated_at",
        )
    )


def _reject_in_transaction(
    *,
    original_actor,
    accessible_target: ArticleVersion,
    version_id: UUID,
    comment: str,
    idempotency_key: str,
    fingerprint: str,
) -> RejectReviewResult:
    with transaction.atomic():
        try:
            article = (
                Article.objects.select_for_update()
                .select_related("space", "current_published_version")
                .get(pk=accessible_target.article_id)
            )
        except Article.DoesNotExist as exc:
            raise RejectArticleVersionError(
                VERSION_NOT_FOUND_OR_INACCESSIBLE,
                "文章版本不存在或不可访问。",
            ) from exc

        actor = _resolve_reject_actor(original_actor)
        _validate_reviewer_scope(actor=actor, article=article)
        idempotency, created = _prepare_idempotency(
            actor=actor,
            operation=IdempotencyOperation.REJECT,
            key=idempotency_key,
            fingerprint=fingerprint,
            error_type=RejectArticleVersionError,
            unavailable_message="审核驳回暂时不可用，请稍后重试。",
        )
        replay = _resolve_reject_idempotency(
            record=idempotency,
            created=created,
            fingerprint=fingerprint,
            article=article,
            version_id=version_id,
        )
        if replay is not None:
            return replay

        target = _lock_review_target(article=article, version_id=version_id)
        _validate_self_review(actor=actor, target=target)
        review = _create_rejection_record(target=target, actor=actor, comment=comment)
        _transition_to_rejected(target=target)
        successor = _create_successor_draft(article=article, target=target)
        _switch_rejected_successor(article=article, successor=successor, actor=actor)
        result = RejectReviewResult(
            kb_no=article.kb_no,
            article_id=article.pk,
            rejected_version_id=target.pk,
            rejected_version_no=target.version_no,
            rejected_status=target.status,
            review_record_id=review.pk,
            successor_draft_id=successor.pk,
            successor_version_no=successor.version_no,
            successor_status=successor.status,
            successor_lock_version=successor.lock_version,
        )
        _write_rejection_evidence(
            actor=actor,
            article=article,
            target=target,
            review=review,
            successor=successor,
        )
        _complete_reject_idempotency(record=idempotency, result=result)
        return result


def reject_article_version(
    *,
    actor,
    version_id,
    comment,
    idempotency_key,
) -> RejectReviewResult:
    """原子驳回 IN_REVIEW 版本，保留审核证据并创建后继 DRAFT。"""
    try:
        current_actor = _resolve_reject_actor(actor)
        normalized_version_id, normalized_comment = _validate_reject_inputs(
            version_id=version_id,
            comment=comment,
            idempotency_key=idempotency_key,
        )
        accessible_target = _resolve_reject_target(
            actor=current_actor,
            version_id=normalized_version_id,
        )
        fingerprint = _build_reject_fingerprint(
            version_id=normalized_version_id,
            comment=normalized_comment,
        )
        return _reject_in_transaction(
            original_actor=actor,
            accessible_target=accessible_target,
            version_id=normalized_version_id,
            comment=normalized_comment,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )
    except RejectArticleVersionError:
        raise
    except (ValidationError, DatabaseError) as exc:
        raise RejectArticleVersionError(
            WORKFLOW_UNAVAILABLE,
            "审核驳回暂时不可用，请稍后重试。",
        ) from exc


def _raise_approve_publish_invalid(message: str) -> None:
    raise ApprovePublishArticleVersionError(INVALID_INPUT, message)


def _validate_approve_publish_inputs(
    *,
    version_id,
    comment,
    idempotency_key,
) -> tuple[UUID, str]:
    try:
        normalized_version_id = ArticleVersion._meta.pk.to_python(version_id)
    except (TypeError, ValueError, ValidationError) as exc:
        try:
            _raise_approve_publish_invalid("文章版本标识格式无效。")
        except ApprovePublishArticleVersionError as error:
            raise error from exc
    if normalized_version_id is None:
        _raise_approve_publish_invalid("文章版本标识格式无效。")
    if not isinstance(comment, str):
        _raise_approve_publish_invalid("审核意见格式无效。")
    normalized_comment = comment.strip()
    _validate_idempotency_key(
        key=idempotency_key,
        raise_invalid=_raise_approve_publish_invalid,
    )
    return normalized_version_id, normalized_comment


def _resolve_approve_publish_actor(actor) -> User:
    return _resolve_reviewer_actor(
        actor,
        required_permissions=(_APPROVE_PERMISSION, _PUBLISH_PERMISSION),
        error_type=ApprovePublishArticleVersionError,
        forbidden_code=APPROVE_PUBLISH_FORBIDDEN,
        identity_message="当前账号不能执行审核发布。",
        forbidden_message="没有批准并发布文章版本的权限。",
    )


def _resolve_approve_publish_target(*, actor: User, version_id: UUID) -> ArticleVersion:
    try:
        target = ArticleVersion.objects.select_related("article__space").get(pk=version_id)
    except ArticleVersion.DoesNotExist as exc:
        raise ApprovePublishArticleVersionError(
            VERSION_NOT_FOUND_OR_INACCESSIBLE,
            "文章版本不存在或不可访问。",
        ) from exc
    _validate_reviewer_scope(
        actor=actor,
        article=target.article,
        error_type=ApprovePublishArticleVersionError,
    )
    _validate_self_review(
        actor=actor,
        target=target,
        error_type=ApprovePublishArticleVersionError,
    )
    return target


def _build_approve_publish_fingerprint(*, version_id: UUID, comment: str) -> str:
    canonical = json.dumps(
        {
            "comment": comment,
            "version_id": str(version_id),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _resolve_approve_publish_idempotency(
    *,
    record: WorkflowIdempotencyRecord,
    created: bool,
    fingerprint: str,
    article: Article,
    version_id: UUID,
) -> ApprovePublishResult | None:
    if created:
        return None
    if record.request_fingerprint != fingerprint:
        raise ApprovePublishArticleVersionError(
            IDEMPOTENCY_CONFLICT,
            "该幂等键已用于不同的审核发布请求。",
        )
    if record.status == IdempotencyStatus.IN_PROGRESS:
        raise ApprovePublishArticleVersionError(
            IDEMPOTENCY_IN_PROGRESS,
            "相同审核发布请求正在处理中。",
        )
    if (
        record.status != IdempotencyStatus.COMPLETED
        or record.result_code != REVIEW_APPROVED_PUBLISHED
    ):
        raise ApprovePublishArticleVersionError(
            WORKFLOW_UNAVAILABLE,
            "审核发布结果暂时不可用，请稍后重试。",
        )
    result = ApprovePublishResult.from_payload(record.result_payload)
    if (
        result.kb_no != article.kb_no
        or result.article_id != article.pk
        or result.published_version_id != version_id
    ):
        raise ApprovePublishArticleVersionError(
            WORKFLOW_UNAVAILABLE,
            "审核发布结果暂时不可用，请稍后重试。",
        )
    return result


def _validate_publish_article_state(*, article: Article) -> None:
    if article.latest_working_version_id is not None:
        raise ApprovePublishArticleVersionError(
            PUBLISH_STATE_INCONSISTENT,
            "文章发布状态不一致，已拒绝审核发布。",
        )


def _validate_no_content_review(*, target: ArticleVersion) -> None:
    if ReviewRecord.objects.filter(
        article_version=target,
        review_type=ReviewType.CONTENT_REVIEW,
    ).exists():
        raise ApprovePublishArticleVersionError(
            PUBLISH_STATE_INCONSISTENT,
            "文章版本已有终局审核记录，已拒绝重复处理。",
        )


def _lock_previous_published(*, article: Article) -> ArticleVersion | None:
    previous_id = article.current_published_version_id
    if previous_id is None:
        return None
    try:
        previous = ArticleVersion.objects.select_for_update().get(
            pk=previous_id,
            article_id=article.pk,
        )
    except ArticleVersion.DoesNotExist as exc:
        raise ApprovePublishArticleVersionError(
            PUBLISH_STATE_INCONSISTENT,
            "文章当前发布版本状态不一致。",
        ) from exc
    if previous.status != VersionStatus.PUBLISHED:
        raise ApprovePublishArticleVersionError(
            PUBLISH_STATE_INCONSISTENT,
            "文章当前发布版本状态不一致。",
        )
    return previous


def _create_approval_review(
    *,
    target: ArticleVersion,
    actor: User,
    comment: str,
) -> ReviewRecord:
    review = ReviewRecord(
        article_version=target,
        review_type=ReviewType.CONTENT_REVIEW,
        reviewer=actor,
        decision=ReviewDecision.APPROVED,
        comment=comment,
    )
    review.full_clean()
    review.save(force_insert=True)
    return review


def _transition_previous_to_superseded(*, previous: ArticleVersion) -> None:
    previous.status = VersionStatus.SUPERSEDED
    previous.full_clean()
    previous.save(update_fields=("status", "updated_at"))


def _transition_target_to_published(
    *,
    target: ArticleVersion,
    published_at: datetime,
) -> None:
    target.status = VersionStatus.PUBLISHED
    target.published_at = published_at
    target.full_clean()
    target.save(update_fields=("status", "published_at", "updated_at"))


def _next_approved_version_no(*, article: Article) -> int:
    max_version_no = article.versions.aggregate(max_no=Max("version_no"))["max_no"]
    if not isinstance(max_version_no, int) or isinstance(max_version_no, bool):
        raise ApprovePublishArticleVersionError(
            WORKFLOW_UNAVAILABLE,
            "审核发布暂时不可用，请稍后重试。",
        )
    return max_version_no + 1


def _create_approved_successor_draft(
    *,
    article: Article,
    target: ArticleVersion,
) -> ArticleVersion:
    successor = ArticleVersion(
        article=article,
        version_no=_next_approved_version_no(article=article),
        status=VersionStatus.DRAFT,
        lock_version=1,
        title=target.title,
        summary=target.summary,
        applicable_scope=deepcopy(target.applicable_scope),
        body=deepcopy(target.body),
        body_plaintext=target.body_plaintext,
        change_summary=f"基于已发布版本 v{target.version_no} 继续编辑",
        restored_from_version=None,
        created_by=target.submitted_by or target.created_by,
        submitted_by=None,
        submitted_at=None,
        published_at=None,
    )
    successor.full_clean(validate_unique=False, validate_constraints=False)
    successor.save(force_insert=True)
    return successor


def _switch_published_article(
    *,
    article: Article,
    target: ArticleVersion,
    successor: ArticleVersion,
    actor: User,
) -> None:
    article.current_published_version = target
    article.latest_working_version = successor
    article.title = target.title
    article.updated_by = actor
    article.full_clean()
    article.save(
        update_fields=(
            "current_published_version",
            "latest_working_version",
            "title",
            "updated_by",
            "updated_at",
        )
    )


def _write_approval_publish_evidence(
    *,
    actor: User,
    article: Article,
    target: ArticleVersion,
    previous: ArticleVersion | None,
    review: ReviewRecord,
    successor: ArticleVersion,
) -> None:
    previous_id = str(previous.pk) if previous is not None else None
    AuditEvent.objects.create(
        event_type=AuditEventType.REVIEW_APPROVED_PUBLISHED,
        actor=actor,
        article=article,
        article_version=target,
        metadata={
            "kb_no": article.kb_no,
            "version_no": target.version_no,
            "space_id": str(article.space_id),
            "review_record_id": str(review.pk),
            "previous_published_version_id": previous_id,
            "successor_draft_id": str(successor.pk),
            "successor_version_no": successor.version_no,
        },
    )
    WorkflowOutboxEvent.objects.create(
        event_type=WorkflowEventType.REVIEW_APPROVED_PUBLISHED,
        dedupe_key=f"review_approved_published:{target.pk}",
        payload={
            "article_id": str(article.pk),
            "kb_no": article.kb_no,
            "published_version_id": str(target.pk),
            "published_version_no": target.version_no,
            "previous_published_version_id": previous_id,
            "space_id": str(article.space_id),
            "reviewer_id": str(actor.pk),
            "review_record_id": str(review.pk),
            "successor_draft_id": str(successor.pk),
            "successor_version_no": successor.version_no,
            "submitted_by_id": str(target.submitted_by_id),
        },
    )


def _complete_approve_publish_idempotency(
    *,
    record: WorkflowIdempotencyRecord,
    result: ApprovePublishResult,
) -> None:
    record.status = IdempotencyStatus.COMPLETED
    record.result_code = REVIEW_APPROVED_PUBLISHED
    record.result_payload = result.to_payload()
    record.full_clean()
    record.save(
        update_fields=(
            "status",
            "result_code",
            "result_payload",
            "updated_at",
        )
    )


def _approve_publish_in_transaction(
    *,
    original_actor,
    accessible_target: ArticleVersion,
    version_id: UUID,
    comment: str,
    idempotency_key: str,
    fingerprint: str,
) -> ApprovePublishResult:
    with transaction.atomic():
        try:
            article = (
                Article.objects.select_for_update()
                .select_related("space")
                .get(pk=accessible_target.article_id)
            )
        except Article.DoesNotExist as exc:
            raise ApprovePublishArticleVersionError(
                VERSION_NOT_FOUND_OR_INACCESSIBLE,
                "文章版本不存在或不可访问。",
            ) from exc

        actor = _resolve_approve_publish_actor(original_actor)
        _validate_reviewer_scope(
            actor=actor,
            article=article,
            error_type=ApprovePublishArticleVersionError,
        )
        idempotency, created = _prepare_idempotency(
            actor=actor,
            operation=IdempotencyOperation.APPROVE_PUBLISH,
            key=idempotency_key,
            fingerprint=fingerprint,
            error_type=ApprovePublishArticleVersionError,
            unavailable_message="审核发布暂时不可用，请稍后重试。",
        )
        replay = _resolve_approve_publish_idempotency(
            record=idempotency,
            created=created,
            fingerprint=fingerprint,
            article=article,
            version_id=version_id,
        )
        if replay is not None:
            return replay

        target = _lock_review_target(
            article=article,
            version_id=version_id,
            error_type=ApprovePublishArticleVersionError,
        )
        _validate_publish_article_state(article=article)
        _validate_self_review(
            actor=actor,
            target=target,
            error_type=ApprovePublishArticleVersionError,
        )
        _validate_no_content_review(target=target)
        previous = _lock_previous_published(article=article)
        review = _create_approval_review(
            target=target,
            actor=actor,
            comment=comment,
        )
        if previous is not None:
            _transition_previous_to_superseded(previous=previous)
        published_at = timezone.now()
        _transition_target_to_published(
            target=target,
            published_at=published_at,
        )
        successor = _create_approved_successor_draft(
            article=article,
            target=target,
        )
        _switch_published_article(
            article=article,
            target=target,
            successor=successor,
            actor=actor,
        )
        result = ApprovePublishResult(
            kb_no=article.kb_no,
            article_id=article.pk,
            published_version_id=target.pk,
            published_version_no=target.version_no,
            published_status=target.status,
            published_at=published_at,
            previous_published_version_id=previous.pk if previous is not None else None,
            review_record_id=review.pk,
            successor_draft_id=successor.pk,
            successor_version_no=successor.version_no,
            successor_status=successor.status,
            successor_lock_version=successor.lock_version,
        )
        _write_approval_publish_evidence(
            actor=actor,
            article=article,
            target=target,
            previous=previous,
            review=review,
            successor=successor,
        )
        _complete_approve_publish_idempotency(record=idempotency, result=result)
        return result


def approve_and_publish_article_version(
    *,
    actor,
    version_id,
    comment="",
    idempotency_key,
) -> ApprovePublishResult:
    """原子批准并发布 IN_REVIEW 版本，同时建立下一工作 DRAFT。"""
    try:
        current_actor = _resolve_approve_publish_actor(actor)
        normalized_version_id, normalized_comment = _validate_approve_publish_inputs(
            version_id=version_id,
            comment=comment,
            idempotency_key=idempotency_key,
        )
        accessible_target = _resolve_approve_publish_target(
            actor=current_actor,
            version_id=normalized_version_id,
        )
        fingerprint = _build_approve_publish_fingerprint(
            version_id=normalized_version_id,
            comment=normalized_comment,
        )
        return _approve_publish_in_transaction(
            original_actor=actor,
            accessible_target=accessible_target,
            version_id=normalized_version_id,
            comment=normalized_comment,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )
    except ApprovePublishArticleVersionError:
        raise
    except (ValidationError, DatabaseError) as exc:
        raise ApprovePublishArticleVersionError(
            WORKFLOW_UNAVAILABLE,
            "审核发布暂时不可用，请稍后重试。",
        ) from exc
