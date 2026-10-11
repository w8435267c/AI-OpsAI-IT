"""管理与编辑侧 ArticleVersion 历史只读入口。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import QuerySet

from apps.accounts.models import User

from .models import Article, ArticleVersion
from .services import (
    _RESTORE_SOURCE_STATUSES,
    KnowledgeServiceError,
    _has_article_version_object_access,
    _resolve_writer_actor,
    _saved_instance,
)

ARTICLE_VERSION_HISTORY_PERMISSION_DENIED = "ARTICLE_VERSION_HISTORY_PERMISSION_DENIED"
ARTICLE_VERSION_HISTORY_NOT_FOUND_OR_INACCESSIBLE = (
    "ARTICLE_VERSION_HISTORY_NOT_FOUND_OR_INACCESSIBLE"
)

_VERSION_HISTORY_REQUIRED_PERMISSIONS = (
    "knowledge.view_article",
    "knowledge.view_articleversion",
)


class ArticleVersionHistoryReadError(KnowledgeServiceError):
    """管理侧版本历史不可读取时的稳定安全异常。"""


@dataclass(frozen=True, slots=True)
class ArticleVersionHistoryDetail:
    """历史版本详情页可读取的只读白名单快照。"""

    kb_no: str
    version_id: UUID
    version_no: int
    status: str
    status_label: str
    title: str
    summary: str
    applicable_scope: object
    body_text: str
    change_summary: str
    created_by_name: str
    created_at: datetime
    submitted_by_name: str | None
    submitted_at: datetime | None
    published_at: datetime | None
    restored_from_version_no: int | None
    is_current_working: bool
    is_current_published: bool
    can_restore: bool


def _raise_history_not_found() -> None:
    raise ArticleVersionHistoryReadError(
        ARTICLE_VERSION_HISTORY_NOT_FOUND_OR_INACCESSIBLE,
        "文章版本历史不存在或不可访问。",
    )


def get_article_version_history(
    *,
    actor,
    article,
) -> QuerySet[ArticleVersion]:
    """返回指定 Article 的完整版本链，按正式版本号倒序排列。"""
    current_actor, is_admin, _is_editor = _resolve_writer_actor(
        actor=actor,
        user_query=User.objects,
        required_permissions=_VERSION_HISTORY_REQUIRED_PERMISSIONS,
        error_type=ArticleVersionHistoryReadError,
        error_code=ARTICLE_VERSION_HISTORY_PERMISSION_DENIED,
        public_message="没有查看文章版本历史的权限。",
    )
    if not _saved_instance(article, Article):
        _raise_history_not_found()

    try:
        current_article = Article.objects.select_related("space").get(pk=article.pk)
    except Article.DoesNotExist:
        _raise_history_not_found()

    if not current_article.space.is_active or not _has_article_version_object_access(
        actor=current_actor,
        article=current_article,
        is_admin=is_admin,
    ):
        _raise_history_not_found()

    return (
        ArticleVersion.objects.filter(article=current_article)
        .select_related(
            "article",
            "created_by",
            "submitted_by",
            "restored_from_version",
        )
        .order_by(
            "-version_no",
            "-pk",
        )
    )


def _display_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.get_full_name() or user.username


def get_article_version_history_detail(
    *,
    actor,
    kb_no,
    version_id,
) -> ArticleVersionHistoryDetail:
    """按 KB 编号和 UUID 返回经对象权限过滤的历史版本详情。"""
    if not isinstance(kb_no, str):
        _raise_history_not_found()
    article = Article.objects.filter(kb_no=kb_no).first()
    if article is None:
        _raise_history_not_found()

    history = get_article_version_history(actor=actor, article=article)
    try:
        version = history.filter(pk=version_id).first()
    except (TypeError, ValueError, ValidationError):
        _raise_history_not_found()
    if version is None:
        _raise_history_not_found()

    return ArticleVersionHistoryDetail(
        kb_no=article.kb_no,
        version_id=version.pk,
        version_no=version.version_no,
        status=version.status,
        status_label=version.get_status_display(),
        title=version.title,
        summary=version.summary,
        applicable_scope=deepcopy(version.applicable_scope),
        body_text=version.body_plaintext,
        change_summary=version.change_summary,
        created_by_name=_display_name(version.created_by) or "",
        created_at=version.created_at,
        submitted_by_name=_display_name(version.submitted_by),
        submitted_at=version.submitted_at,
        published_at=version.published_at,
        restored_from_version_no=(
            version.restored_from_version.version_no
            if version.restored_from_version_id is not None
            else None
        ),
        is_current_working=article.latest_working_version_id == version.pk,
        is_current_published=article.current_published_version_id == version.pk,
        can_restore=version.status in _RESTORE_SOURCE_STATUSES,
    )
