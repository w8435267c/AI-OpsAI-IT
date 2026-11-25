"""正式员工知识只读入口。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import QuerySet
from django.urls import reverse

from apps.accounts.models import User
from apps.knowledge.models import Article, ArticleVersionMedia, MediaKind, MediaScanStatus
from apps.knowledge.richtext_render import RichTextRenderError, render_richtext_html
from apps.knowledge.selectors import visible_articles


@dataclass(frozen=True, slots=True)
class EmployeeArticleDetail:
    """员工详情页可读取的正式版本白名单快照。"""

    kb_no: str
    title: str
    summary: str
    applicable_scope: object
    body_text: str
    category_id: UUID
    category_name: str
    space_id: UUID
    space_code: str
    space_name: str
    published_at: datetime
    media: tuple[EmployeeArticleMedia, ...]
    body_paragraphs: tuple[EmployeeBodyParagraph, ...]
    body_html: str | None


@dataclass(frozen=True, slots=True)
class EmployeeArticleMedia:
    link_id: UUID
    kind: str
    original_name: str
    caption: str
    body_position: int | None


@dataclass(frozen=True, slots=True)
class EmployeeBodyParagraph:
    text: str
    images: tuple[EmployeeArticleMedia, ...]


def employee_visible_articles(
    user: User,
    *,
    base: QuerySet[Article] | None = None,
    now: datetime | None = None,
) -> QuerySet[Article]:
    """返回员工可见文章，并预取后续页面读取所需的单值关联。"""
    return visible_articles(user, base=base, now=now).select_related(
        "current_published_version",
        "category",
        "space",
    )


def get_employee_article_detail(
    user: User,
    kb_no: str,
    *,
    now: datetime | None = None,
) -> EmployeeArticleDetail | None:
    """按员工侧稳定编号返回正式详情快照；不可见或不存在均返回 None。

    Task 10 读取侧将 current_published_version + published 视为正式发布事实。
    ReviewRecord 与发布状态的一致性由后续正式审核/发布事务负责，读取侧不重新推导。
    """
    if not isinstance(kb_no, str):
        return None

    base = Article.objects.filter(kb_no=kb_no)
    article = employee_visible_articles(user, base=base, now=now).first()
    if article is None:
        return None

    version = article.current_published_version
    links = list(
        ArticleVersionMedia.objects.filter(
            article_version=version,
            is_active=True,
            asset__scan_status=MediaScanStatus.CLEAN,
        )
        .select_related("asset")
        .order_by("display_order", "pk")
    )
    media = tuple(
        EmployeeArticleMedia(
            link_id=link.pk,
            kind=link.asset.kind,
            original_name=link.asset.original_name,
            caption=link.caption,
            body_position=link.body_position,
        )
        for link in links
    )
    images_by_position: dict[int, list[EmployeeArticleMedia]] = {}
    for item in media:
        if item.kind == MediaKind.IMAGE:
            images_by_position.setdefault(item.body_position or 0, []).append(item)
    paragraphs = version.body_plaintext.splitlines() or [version.body_plaintext]
    body_paragraphs = tuple(
        EmployeeBodyParagraph(text=text, images=tuple(images_by_position.get(index + 1, [])))
        for index, text in enumerate(paragraphs)
    )
    leading_images = images_by_position.get(0, [])
    if leading_images:
        body_paragraphs = (
            EmployeeBodyParagraph(text="", images=tuple(leading_images)),
            *body_paragraphs,
        )
    media_urls = {
        item.link_id: reverse("knowledge:media_content", args=[article.kb_no, item.link_id])
        for item in media
        if item.kind == MediaKind.IMAGE
    }
    try:
        body_html = render_richtext_html(body=version.body, media_urls=media_urls)
    except RichTextRenderError:
        # A corrupt historical rich snapshot must never expose an unauthorised
        # media reference through the employee read path.
        return None
    return EmployeeArticleDetail(
        kb_no=article.kb_no,
        title=version.title,
        summary=version.summary,
        applicable_scope=deepcopy(version.applicable_scope),
        body_text=version.body_plaintext,
        category_id=article.category_id,
        category_name=article.category.name,
        space_id=article.space_id,
        space_code=article.space.code,
        space_name=article.space.name,
        published_at=version.published_at,
        media=media,
        body_paragraphs=body_paragraphs,
        body_html=body_html,
    )
