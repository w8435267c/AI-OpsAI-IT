"""正式员工搜索页面视图。"""

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.knowledge.http import employee_get_page
from apps.search.readers import search_employee_articles

SEARCH_PAGE_SIZE = 20


@employee_get_page
def employee_search_results(request: HttpRequest) -> HttpResponse:
    """展示当前员工可见正式知识的安全搜索结果。"""

    query = request.GET.get("q", "").strip()
    search_results = search_employee_articles(request.user, query)
    paginator = Paginator(search_results, SEARCH_PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    articles = [
        {
            "kb_no": article.kb_no,
            "title": article.current_published_version.title,
            "summary": article.current_published_version.summary,
            "category_name": article.category.name,
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
        "search/results.html",
        {
            "query": query,
            "query_string": urlencode({"q": query}),
            "articles": articles,
            "pagination": pagination,
        },
    )
