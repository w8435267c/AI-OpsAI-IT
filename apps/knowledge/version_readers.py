"""管理与编辑侧 ArticleVersion 历史只读入口。"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.models import User

from .models import Article, ArticleVersion
from .services import (
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

    return ArticleVersion.objects.filter(article=current_article).order_by(
        "-version_no",
        "-pk",
    )
