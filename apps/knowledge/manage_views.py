"""正式知识管理区只读视图。"""

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.knowledge.manage_http import manage_get_page
from apps.knowledge.manage_readers import (
    ManageArticleListReadError,
    get_manage_article_list,
)

MANAGE_ARTICLE_PAGE_SIZE = 20


@manage_get_page
def manage_article_list(request: HttpRequest) -> HttpResponse:
    """展示当前管理人员有权维护的 Article 列表。"""

    try:
        article_rows = get_manage_article_list(actor=request.user)
    except ManageArticleListReadError as error:
        return HttpResponse(error.public_message, status=403)

    paginator = Paginator(article_rows, MANAGE_ARTICLE_PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
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
        "knowledge/manage/list.html",
        {
            "articles": page.object_list,
            "pagination": pagination,
        },
    )
