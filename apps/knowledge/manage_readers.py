"""正式知识管理区 Article 只读查询入口。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID

from django.db.models import Q, QuerySet, Value
from django.db.models.functions import Coalesce

from apps.accounts.models import AccountStatus, User

from .models import Article, Category, KnowledgeSpace, VersionStatus
from .services import (
    _REQUIRED_PERMISSIONS,
    KnowledgeServiceError,
    _has_article_version_object_access,
    _resolve_writer_actor,
)

MANAGE_ARTICLE_LIST_PERMISSION_DENIED = "MANAGE_ARTICLE_LIST_PERMISSION_DENIED"
MANAGE_ARTICLE_CREATE_PERMISSION_DENIED = "MANAGE_ARTICLE_CREATE_PERMISSION_DENIED"
MANAGE_WORKING_ARTICLE_PERMISSION_DENIED = "MANAGE_WORKING_ARTICLE_PERMISSION_DENIED"
MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE = (
    "MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE"
)

_MANAGE_ARTICLE_LIST_REQUIRED_PERMISSIONS = (
    "knowledge.view_article",
    "knowledge.view_articleversion",
)


class ManageArticleListReadError(KnowledgeServiceError):
    """管理文章列表不可读取时的稳定安全异常。"""


class ManageArticleCreateOptionsReadError(KnowledgeServiceError):
    """管理侧文章创建选项不可读取时的稳定安全异常。"""


class ManageWorkingArticleReadError(KnowledgeServiceError):
    """管理侧 working DRAFT 不可读取时的稳定安全异常。"""


@dataclass(frozen=True, slots=True)
class ManageArticleCreateOptions:
    """创建表单可用选项；QuerySet 均已按 actor 权限收窄。"""

    is_admin: bool
    spaces: QuerySet[KnowledgeSpace]
    categories: QuerySet[Category]
    owners: QuerySet[User]


@dataclass(frozen=True, slots=True)
class ManageWorkingArticleDetail:
    """最小编辑落地页读取的 working DRAFT 安全快照。"""

    kb_no: str
    draft_id: UUID
    version_no: int
    lock_version: int
    status: str
    status_label: str
    title: str
    summary: str
    applicable_scope: object
    body_text: str
    change_summary: str
    space_name: str
    category_name: str
    owner_name: str
    restored_from_version_no: int | None


def get_manage_article_create_options(*, actor) -> ManageArticleCreateOptions:
    """返回符合正式 create_article 权限合同的创建表单选项。"""

    current_actor, is_admin, _is_editor = _resolve_writer_actor(
        actor=actor,
        user_query=User.objects,
        required_permissions=_REQUIRED_PERMISSIONS,
        error_type=ManageArticleCreateOptionsReadError,
        error_code=MANAGE_ARTICLE_CREATE_PERMISSION_DENIED,
        public_message="没有创建文章的权限。",
    )

    spaces = KnowledgeSpace.objects.filter(is_active=True)
    if not is_admin:
        spaces = spaces.filter(owner=current_actor)
    spaces = spaces.order_by("name", "pk")
    categories = (
        Category.objects.filter(is_active=True, space__in=spaces)
        .select_related("space")
        .order_by("space__name", "sort_order", "name", "pk")
    )
    owners = User.objects.none()
    if is_admin:
        owners = User.objects.filter(
            is_active=True,
            account_status=AccountStatus.ACTIVE,
        ).order_by("display_name", "username", "pk")

    return ManageArticleCreateOptions(
        is_admin=is_admin,
        spaces=spaces,
        categories=categories,
        owners=owners,
    )


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


def _raise_working_not_found() -> None:
    raise ManageWorkingArticleReadError(
        MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
        "文章草稿不存在或不可访问。",
    )


def get_manage_working_article_detail(*, actor, kb_no: str) -> ManageWorkingArticleDetail:
    """按 KB 编号返回 actor 可管理的 current DRAFT 安全快照。"""

    current_actor, is_admin, _is_editor = _resolve_writer_actor(
        actor=actor,
        user_query=User.objects,
        required_permissions=_MANAGE_ARTICLE_LIST_REQUIRED_PERMISSIONS,
        error_type=ManageWorkingArticleReadError,
        error_code=MANAGE_WORKING_ARTICLE_PERMISSION_DENIED,
        public_message="没有查看文章草稿的权限。",
    )
    try:
        article = Article.objects.select_related(
            "space",
            "category",
            "owner",
            "latest_working_version",
            "latest_working_version__restored_from_version",
        ).get(kb_no=kb_no, space__is_active=True)
    except Article.DoesNotExist:
        _raise_working_not_found()

    if not _has_article_version_object_access(
        actor=current_actor,
        article=article,
        is_admin=is_admin,
    ):
        _raise_working_not_found()

    draft = article.latest_working_version
    if draft is None or draft.article_id != article.pk or draft.status != VersionStatus.DRAFT:
        _raise_working_not_found()

    return ManageWorkingArticleDetail(
        kb_no=article.kb_no,
        draft_id=draft.pk,
        version_no=draft.version_no,
        lock_version=draft.lock_version,
        status=draft.status,
        status_label=draft.get_status_display(),
        title=draft.title,
        summary=draft.summary,
        applicable_scope=deepcopy(draft.applicable_scope),
        body_text=draft.body_plaintext,
        change_summary=draft.change_summary,
        space_name=article.space.name,
        category_name=article.category.name,
        owner_name=str(article.owner),
        restored_from_version_no=(
            draft.restored_from_version.version_no
            if draft.restored_from_version is not None
            else None
        ),
    )
