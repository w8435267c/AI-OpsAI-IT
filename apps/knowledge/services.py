"""知识文章的正式业务写入入口。"""

from __future__ import annotations

import json
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import AccountStatus, User
from apps.accounts.roles import (
    ROLE_EDITOR,
    ROLE_KNOWLEDGE_ADMIN,
    SYSTEM_ROLE_BY_CODE,
)

from .content import build_plaintext_body
from .models import (
    Article,
    ArticleStatus,
    ArticleType,
    ArticleVersion,
    AudiencePolicy,
    Category,
    KnowledgeNumberCounter,
    KnowledgeSpace,
    VersionStatus,
)

ARTICLE_CREATE_PERMISSION_DENIED = "ARTICLE_CREATE_PERMISSION_DENIED"
ARTICLE_CREATE_INVALID_INPUT = "ARTICLE_CREATE_INVALID_INPUT"
SPACE_CATEGORY_MISMATCH = "SPACE_CATEGORY_MISMATCH"
KNOWLEDGE_NUMBER_COUNTER_MISSING = "KNOWLEDGE_NUMBER_COUNTER_MISSING"
KB_NUMBER_EXHAUSTED = "KB_NUMBER_EXHAUSTED"
COUNTER_OUT_OF_SYNC = "COUNTER_OUT_OF_SYNC"
MODEL_CONSISTENCY_FAILED = "MODEL_CONSISTENCY_FAILED"
DATABASE_WRITE_FAILED = "DATABASE_WRITE_FAILED"
ARTICLE_VERSION_WRITE_PERMISSION_DENIED = "ARTICLE_VERSION_WRITE_PERMISSION_DENIED"
ARTICLE_VERSION_WRITE_INVALID_INPUT = "ARTICLE_VERSION_WRITE_INVALID_INPUT"
DRAFT_NOT_FOUND_OR_INACCESSIBLE = "DRAFT_NOT_FOUND_OR_INACCESSIBLE"
DRAFT_CONFLICT = "DRAFT_CONFLICT"
DRAFT_NOT_CURRENT = "DRAFT_NOT_CURRENT"
INVALID_DRAFT_STATE = "INVALID_DRAFT_STATE"

_MAX_KB_NUMBER = 999_999
_REQUIRED_PERMISSIONS = (
    "knowledge.view_knowledgespace",
    "knowledge.view_category",
    "knowledge.add_article",
    "knowledge.change_article",
    "knowledge.view_article",
    "knowledge.add_articleversion",
    "knowledge.change_articleversion",
    "knowledge.view_articleversion",
)
_EDITOR_ROLE_NAME = SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name
_ADMIN_ROLE_NAME = SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name
_VERSION_WRITE_REQUIRED_PERMISSIONS = (
    "knowledge.view_article",
    "knowledge.change_article",
    "knowledge.view_articleversion",
    "knowledge.change_articleversion",
)


class KnowledgeServiceError(Exception):
    """知识写入失败的公共业务异常；公开消息不得包含数据库内部信息。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.public_message = message
        super().__init__(message)


class ArticleCreationError(KnowledgeServiceError):
    """创建失败的稳定业务异常；保持 Task 12C 接口兼容。"""


class ArticleVersionWriteError(KnowledgeServiceError):
    """版本写入失败的稳定业务异常。"""


def _raise_invalid(message: str) -> None:
    raise ArticleCreationError(ARTICLE_CREATE_INVALID_INPUT, message)


def _raise_version_write_invalid(message: str) -> None:
    raise ArticleVersionWriteError(ARTICLE_VERSION_WRITE_INVALID_INPUT, message)


def _validate_editable_version_fields(
    *,
    title,
    summary,
    applicable_scope,
    change_summary,
    raise_invalid,
) -> None:
    for value, field_name, max_length in (
        (title, "标题", 60),
        (summary, "摘要", 500),
        (change_summary, "版本说明", 500),
    ):
        if not isinstance(value, str) or not value.strip():
            raise_invalid(f"{field_name}不能为空。")
        if len(value) > max_length:
            raise_invalid(f"{field_name}超过最大长度。")

    if not isinstance(applicable_scope, dict):
        raise_invalid("适用范围必须是对象。")
    try:
        json.dumps(applicable_scope)
    except (TypeError, ValueError) as exc:
        try:
            raise_invalid("适用范围不是有效的 JSON 对象。")
        except KnowledgeServiceError as error:
            raise error from exc


def _build_validated_plaintext_body(*, body_text, raise_invalid) -> tuple[dict[str, str], str]:
    try:
        return build_plaintext_body(body_text)
    except ValueError as exc:
        try:
            raise_invalid(str(exc))
        except KnowledgeServiceError as error:
            raise error from exc


def _validate_scalar_inputs(
    *,
    article_type: str,
    title: str,
    summary: str,
    applicable_scope: dict[str, object],
    body_text: str,
    change_summary: str,
    review_due_at: datetime,
    audience_policy: str | None,
    effective_at: datetime | None,
) -> tuple[dict[str, str], str]:
    if article_type not in ArticleType.values:
        _raise_invalid("文章类型无效。")
    if audience_policy is not None and audience_policy not in AudiencePolicy.values:
        _raise_invalid("内容受众策略无效。")

    _validate_editable_version_fields(
        title=title,
        summary=summary,
        applicable_scope=applicable_scope,
        change_summary=change_summary,
        raise_invalid=_raise_invalid,
    )

    if not isinstance(review_due_at, datetime) or not timezone.is_aware(review_due_at):
        _raise_invalid("复审截止时间必须是带时区的日期时间。")
    if effective_at is not None and (
        not isinstance(effective_at, datetime) or not timezone.is_aware(effective_at)
    ):
        _raise_invalid("生效时间必须是带时区的日期时间。")

    return _build_validated_plaintext_body(body_text=body_text, raise_invalid=_raise_invalid)


def _saved_instance(value, model) -> bool:
    return isinstance(value, model) and value.pk is not None and not value._state.adding


def _resolve_writer_actor(
    *,
    actor,
    user_query,
    required_permissions,
    error_type,
    error_code,
    public_message,
) -> tuple[User, bool, bool]:
    if not _saved_instance(actor, User) or not actor.is_authenticated:
        raise error_type(error_code, public_message)

    try:
        current_actor = user_query.get(pk=actor.pk)
    except User.DoesNotExist as exc:
        raise error_type(error_code, public_message) from exc

    if not current_actor.is_active or current_actor.account_status != AccountStatus.ACTIVE:
        raise error_type(error_code, public_message)

    role_names = set(
        current_actor.groups.filter(name__in=(_EDITOR_ROLE_NAME, _ADMIN_ROLE_NAME)).values_list(
            "name", flat=True
        )
    )
    is_admin = _ADMIN_ROLE_NAME in role_names
    is_editor = _EDITOR_ROLE_NAME in role_names
    if not (is_admin or is_editor) or not current_actor.has_perms(required_permissions):
        raise error_type(error_code, public_message)
    return current_actor, is_admin, is_editor


def _resolve_creation_context(
    *,
    actor,
    space,
    category,
    owner,
    audience_policy,
    lock: bool,
) -> tuple[User, KnowledgeSpace, Category, User, str]:
    # 保持 Task 12C 的失败优先级：无效 actor 必须先于对象输入被拒绝。
    if not _saved_instance(actor, User) or not actor.is_authenticated:
        raise ArticleCreationError(
            ARTICLE_CREATE_PERMISSION_DENIED,
            "没有创建文章的权限。",
        )
    if not _saved_instance(space, KnowledgeSpace) or not _saved_instance(category, Category):
        _raise_invalid("知识空间或分类无效。")

    user_query = User.objects
    space_query = KnowledgeSpace.objects
    category_query = Category.objects
    if lock:
        user_query = user_query.select_for_update()
        space_query = space_query.select_for_update()
        category_query = category_query.select_for_update()

    current_actor, is_admin, _is_editor = _resolve_writer_actor(
        actor=actor,
        user_query=user_query,
        required_permissions=_REQUIRED_PERMISSIONS,
        error_type=ArticleCreationError,
        error_code=ARTICLE_CREATE_PERMISSION_DENIED,
        public_message="没有创建文章的权限。",
    )

    try:
        current_space = space_query.get(pk=space.pk)
        current_category = category_query.get(pk=category.pk)
    except (KnowledgeSpace.DoesNotExist, Category.DoesNotExist) as exc:
        raise ArticleCreationError(
            ARTICLE_CREATE_INVALID_INPUT,
            "知识空间或分类无效。",
        ) from exc

    if not current_space.is_active:
        _raise_invalid("知识空间未启用。")
    if current_category.space_id != current_space.pk:
        raise ArticleCreationError(
            SPACE_CATEGORY_MISMATCH,
            "业务分类不属于所选知识空间。",
        )
    if not current_category.is_active:
        _raise_invalid("业务分类未启用。")

    if is_admin:
        requested_owner = current_actor if owner is None else owner
        if not _saved_instance(requested_owner, User):
            _raise_invalid("知识负责人无效。")
        try:
            current_owner = user_query.get(pk=requested_owner.pk)
        except User.DoesNotExist as exc:
            raise ArticleCreationError(
                ARTICLE_CREATE_INVALID_INPUT,
                "知识负责人无效。",
            ) from exc
        if not current_owner.is_active or current_owner.account_status != AccountStatus.ACTIVE:
            _raise_invalid("知识负责人不是有效账号。")
    else:
        if current_space.owner_id != current_actor.pk:
            raise ArticleCreationError(
                ARTICLE_CREATE_PERMISSION_DENIED,
                "没有在该知识空间创建文章的权限。",
            )
        current_owner = current_actor

    resolved_policy = audience_policy or current_space.default_audience_policy
    if resolved_policy not in AudiencePolicy.values:
        _raise_invalid("内容受众策略无效。")
    return current_actor, current_space, current_category, current_owner, resolved_policy


def _create_in_transaction(
    *,
    actor,
    space,
    category,
    article_type,
    title,
    summary,
    applicable_scope,
    body,
    body_plaintext,
    change_summary,
    review_due_at,
    owner,
    audience_policy,
    effective_at,
) -> tuple[Article, ArticleVersion]:
    with transaction.atomic():
        try:
            counter = KnowledgeNumberCounter.objects.select_for_update().get(pk=1)
        except KnowledgeNumberCounter.DoesNotExist as exc:
            raise ArticleCreationError(
                KNOWLEDGE_NUMBER_COUNTER_MISSING,
                "知识编号计数器缺失，已拒绝创建文章。",
            ) from exc

        current_actor, current_space, current_category, current_owner, resolved_policy = (
            _resolve_creation_context(
                actor=actor,
                space=space,
                category=category,
                owner=owner,
                audience_policy=audience_policy,
                lock=True,
            )
        )

        number = counter.next_value
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise ArticleCreationError(
                COUNTER_OUT_OF_SYNC,
                "知识编号计数器状态异常，已拒绝创建文章。",
            )
        if number > _MAX_KB_NUMBER:
            raise ArticleCreationError(
                KB_NUMBER_EXHAUSTED,
                "六位知识编号已耗尽，已拒绝创建文章。",
            )

        kb_no = f"KB-{number:06d}"
        if Article.objects.filter(kb_no=kb_no).exists():
            raise ArticleCreationError(
                COUNTER_OUT_OF_SYNC,
                "知识编号计数器与现有文章不一致，已拒绝创建文章。",
            )

        article = Article(
            kb_no=kb_no,
            title=title,
            space=current_space,
            category=current_category,
            article_type=article_type,
            audience_policy=resolved_policy,
            owner=current_owner,
            article_status=ArticleStatus.ACTIVE,
            effective_at=effective_at,
            review_due_at=review_due_at,
            current_published_version=None,
            latest_working_version=None,
            created_by=current_actor,
            updated_by=current_actor,
        )
        article.full_clean()
        article.save(force_insert=True)

        draft = ArticleVersion(
            article=article,
            version_no=1,
            status=VersionStatus.DRAFT,
            lock_version=1,
            title=title,
            summary=summary,
            applicable_scope=applicable_scope,
            body=body,
            body_plaintext=body_plaintext,
            change_summary=change_summary,
            restored_from_version=None,
            created_by=current_actor,
            submitted_by=None,
            submitted_at=None,
            published_at=None,
        )
        draft.full_clean()
        draft.save(force_insert=True)

        article.latest_working_version = draft
        article.full_clean()
        if (
            article.latest_working_version.article_id != article.pk
            or article.latest_working_version.status != VersionStatus.DRAFT
            or article.current_published_version_id is not None
        ):
            raise ArticleCreationError(
                MODEL_CONSISTENCY_FAILED,
                "文章工作版本未通过一致性校验。",
            )
        article.save(update_fields=("latest_working_version", "updated_at"))

        counter.next_value = number + 1
        counter.save(update_fields=("next_value", "updated_at"))
        return article, draft


def create_article(
    *,
    actor,
    space,
    category,
    article_type,
    title,
    summary,
    applicable_scope,
    body_text,
    change_summary,
    review_due_at,
    owner=None,
    audience_policy=None,
    effective_at=None,
) -> tuple[Article, ArticleVersion]:
    """原子创建 Article、首个 DRAFT、工作指针并推进全局 KB 编号。"""
    body, body_plaintext = _validate_scalar_inputs(
        article_type=article_type,
        title=title,
        summary=summary,
        applicable_scope=applicable_scope,
        body_text=body_text,
        change_summary=change_summary,
        review_due_at=review_due_at,
        audience_policy=audience_policy,
        effective_at=effective_at,
    )
    try:
        _resolve_creation_context(
            actor=actor,
            space=space,
            category=category,
            owner=owner,
            audience_policy=audience_policy,
            lock=False,
        )
        return _create_in_transaction(
            actor=actor,
            space=space,
            category=category,
            article_type=article_type,
            title=title,
            summary=summary,
            applicable_scope=applicable_scope,
            body=body,
            body_plaintext=body_plaintext,
            change_summary=change_summary,
            review_due_at=review_due_at,
            owner=owner,
            audience_policy=audience_policy,
            effective_at=effective_at,
        )
    except ArticleCreationError:
        raise
    except ValidationError as exc:
        raise ArticleCreationError(
            MODEL_CONSISTENCY_FAILED,
            "文章数据未通过一致性校验。",
        ) from exc
    except DatabaseError as exc:
        raise ArticleCreationError(
            DATABASE_WRITE_FAILED,
            "文章创建失败，请稍后重试。",
        ) from exc


def _resolve_article_version_write_context(*, actor, article) -> tuple[User, Article]:
    current_actor, is_admin, _is_editor = _resolve_writer_actor(
        actor=actor,
        user_query=User.objects,
        required_permissions=_VERSION_WRITE_REQUIRED_PERMISSIONS,
        error_type=ArticleVersionWriteError,
        error_code=ARTICLE_VERSION_WRITE_PERMISSION_DENIED,
        public_message="没有保存文章草稿的权限。",
    )
    if not _saved_instance(article, Article):
        raise ArticleVersionWriteError(
            DRAFT_NOT_FOUND_OR_INACCESSIBLE,
            "草稿不存在或不可访问。",
        )

    try:
        current_article = Article.objects.select_related("space").get(pk=article.pk)
    except Article.DoesNotExist as exc:
        raise ArticleVersionWriteError(
            DRAFT_NOT_FOUND_OR_INACCESSIBLE,
            "草稿不存在或不可访问。",
        ) from exc

    if not current_article.space.is_active:
        _raise_version_write_invalid("文章所属知识空间未启用。")
    if not is_admin and (
        current_article.owner_id != current_actor.pk
        and current_article.space.owner_id != current_actor.pk
    ):
        raise ArticleVersionWriteError(
            DRAFT_NOT_FOUND_OR_INACCESSIBLE,
            "草稿不存在或不可访问。",
        )
    return current_actor, current_article


def _normalize_draft_id(draft_id):
    try:
        return ArticleVersion._meta.pk.to_python(draft_id)
    except (TypeError, ValueError, ValidationError) as exc:
        raise ArticleVersionWriteError(
            DRAFT_NOT_FOUND_OR_INACCESSIBLE,
            "草稿不存在或不可访问。",
        ) from exc


def _raise_cas_zero_result(*, article: Article, draft_id, expected_lock_version: int) -> None:
    snapshot = (
        ArticleVersion.objects.filter(pk=draft_id, article_id=article.pk)
        .annotate(current_draft_id=F("article__latest_working_version_id"))
        .values("status", "lock_version", "current_draft_id")
        .first()
    )
    if snapshot is None:
        raise ArticleVersionWriteError(
            DRAFT_NOT_FOUND_OR_INACCESSIBLE,
            "草稿不存在或不可访问。",
        )
    if snapshot["current_draft_id"] != draft_id:
        raise ArticleVersionWriteError(
            DRAFT_NOT_CURRENT,
            "该版本已不是当前工作草稿。",
        )
    if snapshot["status"] != VersionStatus.DRAFT:
        raise ArticleVersionWriteError(
            INVALID_DRAFT_STATE,
            "该版本不是可编辑草稿。",
        )
    if snapshot["lock_version"] != expected_lock_version:
        raise ArticleVersionWriteError(
            DRAFT_CONFLICT,
            "草稿已被其他操作更新，请刷新后重试。",
        )
    raise ArticleVersionWriteError(
        DRAFT_CONFLICT,
        "草稿状态已发生变化，请刷新后重试。",
    )


def _autosave_draft(
    *,
    actor,
    article,
    draft_id,
    expected_lock_version,
    title,
    summary,
    applicable_scope,
    body_text,
    change_summary,
) -> ArticleVersion:
    _current_actor, current_article = _resolve_article_version_write_context(
        actor=actor,
        article=article,
    )
    if (
        not isinstance(expected_lock_version, int)
        or isinstance(expected_lock_version, bool)
        or expected_lock_version < 1
    ):
        _raise_version_write_invalid("草稿锁版本必须是正整数。")
    _validate_editable_version_fields(
        title=title,
        summary=summary,
        applicable_scope=applicable_scope,
        change_summary=change_summary,
        raise_invalid=_raise_version_write_invalid,
    )
    body, body_plaintext = _build_validated_plaintext_body(
        body_text=body_text,
        raise_invalid=_raise_version_write_invalid,
    )
    normalized_draft_id = _normalize_draft_id(draft_id)
    updated_at = timezone.now()

    updated_rows = ArticleVersion.objects.filter(
        pk=normalized_draft_id,
        article_id=current_article.pk,
        article__latest_working_version_id=normalized_draft_id,
        status=VersionStatus.DRAFT,
        lock_version=expected_lock_version,
    ).update(
        title=title,
        summary=summary,
        applicable_scope=applicable_scope,
        body=body,
        body_plaintext=body_plaintext,
        change_summary=change_summary,
        lock_version=F("lock_version") + 1,
        updated_at=updated_at,
    )
    if updated_rows != 1:
        _raise_cas_zero_result(
            article=current_article,
            draft_id=normalized_draft_id,
            expected_lock_version=expected_lock_version,
        )

    try:
        draft = ArticleVersion.objects.get(
            pk=normalized_draft_id,
            article_id=current_article.pk,
        )
    except ArticleVersion.DoesNotExist as exc:
        raise ArticleVersionWriteError(
            DRAFT_CONFLICT,
            "草稿状态已发生变化，请刷新后重试。",
        ) from exc

    expected_values = (
        draft.status == VersionStatus.DRAFT,
        draft.lock_version == expected_lock_version + 1,
        draft.title == title,
        draft.summary == summary,
        draft.applicable_scope == applicable_scope,
        draft.body == body,
        draft.body_plaintext == body_plaintext,
        draft.change_summary == change_summary,
    )
    if not all(expected_values):
        raise ArticleVersionWriteError(
            DRAFT_CONFLICT,
            "草稿状态已发生变化，请刷新后重试。",
        )
    return draft


def autosave_draft(
    *,
    actor,
    article,
    draft_id,
    expected_lock_version,
    title,
    summary,
    applicable_scope,
    body_text,
    change_summary,
) -> ArticleVersion:
    """使用乐观锁原地更新当前 DRAFT；不创建版本或写入 Article。"""
    try:
        return _autosave_draft(
            actor=actor,
            article=article,
            draft_id=draft_id,
            expected_lock_version=expected_lock_version,
            title=title,
            summary=summary,
            applicable_scope=applicable_scope,
            body_text=body_text,
            change_summary=change_summary,
        )
    except ArticleVersionWriteError:
        raise
    except ValidationError as exc:
        raise ArticleVersionWriteError(
            MODEL_CONSISTENCY_FAILED,
            "草稿数据未通过一致性校验。",
        ) from exc
    except DatabaseError as exc:
        raise ArticleVersionWriteError(
            DATABASE_WRITE_FAILED,
            "草稿保存失败，请稍后重试。",
        ) from exc
