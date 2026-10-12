"""Task 13 审核工作流的正式事务 Service。"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import AccountStatus, User
from apps.accounts.roles import (
    ROLE_EDITOR,
    ROLE_KNOWLEDGE_ADMIN,
    SYSTEM_ROLE_BY_CODE,
)
from apps.audit.models import AuditEvent, AuditEventType
from apps.knowledge.models import Article, ArticleVersion, VersionStatus

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

_KB_NO_PATTERN = re.compile(r"^KB-[0-9]{6}$")
_EDITOR_ROLE_NAME = SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name
_ADMIN_ROLE_NAME = SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name
_SUBMIT_PERMISSION = "knowledge.submit_articleversion"


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


def _raise_invalid(message: str) -> None:
    raise SubmitArticleForReviewError(INVALID_INPUT, message)


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
    if not isinstance(idempotency_key, str):
        _raise_invalid("幂等键格式无效。")
    if (
        not idempotency_key
        or not idempotency_key.strip()
        or idempotency_key != idempotency_key.strip()
        or len(idempotency_key) > 128
        or any(unicodedata.category(character) == "Cc" for character in idempotency_key)
    ):
        _raise_invalid("幂等键格式无效。")
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


def _load_idempotency_record(*, actor: User, key: str):
    return (
        WorkflowIdempotencyRecord.objects.select_for_update()
        .filter(
            actor=actor,
            operation=IdempotencyOperation.SUBMIT,
            key=key,
        )
        .first()
    )


def _prepare_idempotency(
    *,
    actor: User,
    key: str,
    fingerprint: str,
) -> tuple[WorkflowIdempotencyRecord, bool]:
    existing = _load_idempotency_record(actor=actor, key=key)
    if existing is not None:
        return existing, False

    try:
        # 独立 savepoint 只隔离唯一键竞争；外层事务仍覆盖全部业务写入。
        with transaction.atomic():
            record = WorkflowIdempotencyRecord.objects.create(
                actor=actor,
                operation=IdempotencyOperation.SUBMIT,
                key=key,
                request_fingerprint=fingerprint,
            )
        return record, True
    except IntegrityError as exc:
        # 并发首次请求可能同时看不到记录；数据库唯一约束决定胜者。
        existing = _load_idempotency_record(actor=actor, key=key)
        if existing is None:
            raise SubmitArticleForReviewError(
                WORKFLOW_UNAVAILABLE,
                "提交审核暂时不可用，请稍后重试。",
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
            key=idempotency_key,
            fingerprint=fingerprint,
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
