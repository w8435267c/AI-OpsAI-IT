"""正式知识管理区视图。"""

import json

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.shortcuts import render
from django.urls import reverse

from apps.knowledge.manage_forms import ArticleCreateForm
from apps.knowledge.manage_http import manage_get_page, manage_get_post_page
from apps.knowledge.manage_readers import (
    MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
    ManageArticleCreateOptionsReadError,
    ManageArticleListReadError,
    ManageWorkingArticleReadError,
    get_manage_article_list,
    get_manage_working_article_detail,
)
from apps.knowledge.services import (
    ARTICLE_CREATE_INVALID_INPUT,
    ARTICLE_CREATE_PERMISSION_DENIED,
    SPACE_CATEGORY_MISMATCH,
    ArticleCreationError,
    create_article,
)

MANAGE_ARTICLE_PAGE_SIZE = 20
_CREATE_FORM_ERROR_CODES = {
    ARTICLE_CREATE_INVALID_INPUT,
    SPACE_CATEGORY_MISMATCH,
}


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


def _render_article_create(
    request: HttpRequest,
    form: ArticleCreateForm,
    *,
    status: int = 200,
) -> HttpResponse:
    return render(
        request,
        "knowledge/manage/create.html",
        {"form": form},
        status=status,
    )


@manage_get_post_page
def manage_article_create(request: HttpRequest) -> HttpResponse:
    """展示创建表单，并仅通过正式 Service 原子创建 Article。"""

    try:
        form = ArticleCreateForm(
            actor=request.user,
            data=request.POST if request.method == "POST" else None,
        )
    except ManageArticleCreateOptionsReadError as error:
        return HttpResponse(error.public_message, status=403)

    if request.method == "GET" or not form.is_valid():
        return _render_article_create(request, form)

    cleaned = form.cleaned_data
    try:
        article, _draft = create_article(
            actor=request.user,
            space=cleaned["space"],
            category=cleaned["category"],
            article_type=cleaned["article_type"],
            title=cleaned["title"],
            summary=cleaned["summary"],
            applicable_scope=cleaned["applicable_scope"],
            body_text=cleaned["body_text"],
            change_summary=cleaned["change_summary"],
            review_due_at=cleaned["review_due_at"],
            owner=cleaned.get("owner"),
            audience_policy=cleaned["audience_policy"],
            effective_at=cleaned["effective_at"],
        )
    except ArticleCreationError as error:
        if error.code == ARTICLE_CREATE_PERMISSION_DENIED:
            return HttpResponse("没有创建文章的权限。", status=403)
        if error.code in _CREATE_FORM_ERROR_CODES:
            form.add_error(None, error.public_message)
            return _render_article_create(request, form)
        form.add_error(None, "系统暂时无法创建知识，请稍后重试或联系管理员。")
        return _render_article_create(request, form, status=503)

    response = HttpResponse(status=303)
    response["Location"] = reverse("knowledge_manage:edit", args=[article.kb_no])
    return response


@manage_get_page
def manage_article_edit(request: HttpRequest, kb_no: str) -> HttpResponse:
    """展示 current DRAFT 的最小只读落地页。"""

    try:
        detail = get_manage_working_article_detail(actor=request.user, kb_no=kb_no)
    except ManageWorkingArticleReadError as error:
        if error.code == MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE:
            return HttpResponseNotFound("未找到可查看的文章草稿。")
        return HttpResponse(error.public_message, status=403)

    return render(
        request,
        "knowledge/manage/edit.html",
        {
            "detail": detail,
            "applicable_scope_text": json.dumps(
                detail.applicable_scope,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        },
    )
