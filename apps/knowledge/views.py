"""正式员工知识页面视图。"""

import json

from django.core.paginator import Paginator
from django.db.models import F
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.shortcuts import render

from apps.knowledge.http import employee_get_page
from apps.knowledge.models import Article, Category
from apps.knowledge.readers import employee_visible_articles, get_employee_article_detail

HOME_RECENT_LIMIT = 12
CATEGORY_PAGE_SIZE = 20


def _employee_article_ordering():
    """返回员工列表共用的稳定倒序规则。"""

    return (
        F("current_published_version__published_at").desc(nulls_last=True),
        "-updated_at",
        "pk",
    )


def _applicable_scope_text(value: object) -> str:
    """将 Reader 白名单中的 JSON 值确定性地展示为安全普通文本。"""

    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


@employee_get_page
def employee_home(request: HttpRequest) -> HttpResponse:
    """展示当前员工可见的分类摘要和最近正式知识。"""

    recent_rows = employee_visible_articles(request.user).order_by(*_employee_article_ordering())[
        :HOME_RECENT_LIMIT
    ]
    recent_articles = [
        {
            "kb_no": article.kb_no,
            "title": article.current_published_version.title,
            "summary": article.current_published_version.summary,
            "category_name": article.category.name,
            "published_at": article.current_published_version.published_at,
        }
        for article in recent_rows
    ]

    category_rows = (
        employee_visible_articles(request.user)
        .filter(category__is_active=True)
        .order_by("category__sort_order", "category__name", "category_id")
        .values("category_id", "category__name")
        .distinct()
    )
    categories = [
        {"id": row["category_id"], "name": row["category__name"]} for row in category_rows
    ]

    return render(
        request,
        "knowledge/home.html",
        {
            "categories": categories,
            "recent_articles": recent_articles,
        },
    )


@employee_get_page
def employee_category_detail(request: HttpRequest, category_id) -> HttpResponse:
    """展示有效分类下当前员工可见的正式知识。"""

    category = (
        Category.objects.filter(
            pk=category_id,
            is_active=True,
            space__is_active=True,
        )
        .only("name")
        .first()
    )
    if category is None:
        return HttpResponseNotFound("未找到可查看的分类。")

    base = Article.objects.filter(category_id=category_id)
    visible_articles = employee_visible_articles(request.user, base=base).order_by(
        *_employee_article_ordering()
    )
    paginator = Paginator(visible_articles, CATEGORY_PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    articles = [
        {
            "kb_no": article.kb_no,
            "title": article.current_published_version.title,
            "summary": article.current_published_version.summary,
            "published_at": article.current_published_version.published_at,
        }
        for article in page.object_list
    ]
    pagination = {
        "number": page.number,
        "num_pages": paginator.num_pages,
        "count": paginator.count,
        "has_previous": page.has_previous(),
        "previous_page_number": page.previous_page_number() if page.has_previous() else None,
        "has_next": page.has_next(),
        "next_page_number": page.next_page_number() if page.has_next() else None,
    }

    return render(
        request,
        "knowledge/category_detail.html",
        {
            "category": {"name": category.name},
            "articles": articles,
            "pagination": pagination,
        },
    )


@employee_get_page
def employee_article_detail(request: HttpRequest, kb_no: str) -> HttpResponse:
    """按员工侧知识编号展示当前用户可见的正式版本快照。"""

    detail = get_employee_article_detail(request.user, kb_no)
    if detail is None:
        return HttpResponseNotFound("未找到可查看的知识。")

    return render(
        request,
        "knowledge/article_detail.html",
        {
            "detail": detail,
            "applicable_scope_text": _applicable_scope_text(detail.applicable_scope),
        },
    )
