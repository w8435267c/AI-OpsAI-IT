"""知识文章的正式业务写入入口。"""

from __future__ import annotations

import json
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
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


class ArticleCreationError(Exception):
    """创建失败的稳定业务异常；公开消息不得包含数据库内部信息。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.public_message = message
        super().__init__(message)


def _raise_invalid(message: str) -> None:
    raise ArticleCreationError(ARTICLE_CREATE_INVALID_INPUT, message)


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

    for value, field_name, max_length in (
        (title, "标题", 60),
        (summary, "摘要", 500),
        (change_summary, "版本说明", 500),
    ):
        if not isinstance(value, str) or not value.strip():
            _raise_invalid(f"{field_name}不能为空。")
        if len(value) > max_length:
            _raise_invalid(f"{field_name}超过最大长度。")

    if not isinstance(applicable_scope, dict):
        _raise_invalid("适用范围必须是对象。")
    try:
        json.dumps(applicable_scope)
    except (TypeError, ValueError) as exc:
        raise ArticleCreationError(
            ARTICLE_CREATE_INVALID_INPUT,
            "适用范围不是有效的 JSON 对象。",
        ) from exc

    if not isinstance(review_due_at, datetime) or not timezone.is_aware(review_due_at):
        _raise_invalid("复审截止时间必须是带时区的日期时间。")
    if effective_at is not None and (
        not isinstance(effective_at, datetime) or not timezone.is_aware(effective_at)
    ):
        _raise_invalid("生效时间必须是带时区的日期时间。")

    try:
        return build_plaintext_body(body_text)
    except ValueError as exc:
        raise ArticleCreationError(ARTICLE_CREATE_INVALID_INPUT, str(exc)) from exc


def _saved_instance(value, model) -> bool:
    return isinstance(value, model) and value.pk is not None and not value._state.adding


def _resolve_creation_context(
    *,
    actor,
    space,
    category,
    owner,
    audience_policy,
    lock: bool,
) -> tuple[User, KnowledgeSpace, Category, User, str]:
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

    try:
        current_actor = user_query.get(pk=actor.pk)
    except User.DoesNotExist as exc:
        raise ArticleCreationError(
            ARTICLE_CREATE_PERMISSION_DENIED,
            "没有创建文章的权限。",
        ) from exc

    if not current_actor.is_active or current_actor.account_status != AccountStatus.ACTIVE:
        raise ArticleCreationError(
            ARTICLE_CREATE_PERMISSION_DENIED,
            "没有创建文章的权限。",
        )

    role_names = set(
        current_actor.groups.filter(name__in=(_EDITOR_ROLE_NAME, _ADMIN_ROLE_NAME)).values_list(
            "name", flat=True
        )
    )
    is_admin = _ADMIN_ROLE_NAME in role_names
    is_editor = _EDITOR_ROLE_NAME in role_names
    if not (is_admin or is_editor) or not current_actor.has_perms(_REQUIRED_PERMISSIONS):
        raise ArticleCreationError(
            ARTICLE_CREATE_PERMISSION_DENIED,
            "没有创建文章的权限。",
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
