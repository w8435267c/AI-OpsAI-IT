"""正式知识管理区 Article 列表只读入口。"""

from __future__ import annotations

from django.db.models import Q, QuerySet, Value
from django.db.models.functions import Coalesce

from apps.accounts.models import User

from .models import Article
from .services import KnowledgeServiceError, _resolve_writer_actor

MANAGE_ARTICLE_LIST_PERMISSION_DENIED = "MANAGE_ARTICLE_LIST_PERMISSION_DENIED"

_MANAGE_ARTICLE_LIST_REQUIRED_PERMISSIONS = (
    "knowledge.view_article",
    "knowledge.view_articleversion",
)


class ManageArticleListReadError(KnowledgeServiceError):
    """管理文章列表不可读取时的稳定安全异常。"""


def get_manage_article_list(*, actor) -> QuerySet[Article]:
    """返回 actor 可管理的有效空间文章，不要求文章已有发布版本。"""

    current_actor, is_admin, _is_editor = _resolve_writer_actor(
        actor=actor,
        user_query=User.objects,
        required_permissions=_MANAGE_ARTICLE_LIST_REQUIRED_PERMISSIONS,
        error_type=ManageArticleListReadError,
        error_code=MANAGE_ARTICLE_LIST_PERMISSION_DENIED,
        public_message="没有查看知识管理列表的权限。",
    )

    articles = Article.objects.filter(space__is_active=True)
    if not is_admin:
        articles = articles.filter(Q(owner=current_actor) | Q(space__owner=current_actor))

    return (
        articles.select_related(
            "space",
            "category",
            "owner",
            "latest_working_version",
            "current_published_version",
        )
        .annotate(
            manage_title=Coalesce(
                "latest_working_version__title",
                "current_published_version__title",
                Value("（无可用标题）"),
            )
        )
        .order_by("-updated_at", "pk")
    )
