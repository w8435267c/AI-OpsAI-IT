"""正式知识管理区视图。"""

import json

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import render
from django.urls import reverse

from apps.knowledge.manage_forms import (
    ArticleAutosaveIdentityForm,
    ArticleCreateForm,
    ArticleDraftForm,
)
from apps.knowledge.manage_http import (
    manage_get_page,
    manage_get_post_page,
    manage_post_json_page,
)
from apps.knowledge.manage_readers import (
    MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
    ManageArticleCreateOptionsReadError,
    ManageArticleListReadError,
    ManageWorkingArticleReadError,
    get_manage_article_list,
    get_manage_working_article_detail,
)
from apps.knowledge.models import Article
from apps.knowledge.services import (
    ARTICLE_CREATE_INVALID_INPUT,
    ARTICLE_CREATE_PERMISSION_DENIED,
    ARTICLE_VERSION_WRITE_INVALID_INPUT,
    ARTICLE_VERSION_WRITE_PERMISSION_DENIED,
    DATABASE_WRITE_FAILED,
    DRAFT_CONFLICT,
    DRAFT_NOT_CURRENT,
    DRAFT_NOT_FOUND_OR_INACCESSIBLE,
    INVALID_DRAFT_STATE,
    MODEL_CONSISTENCY_FAILED,
    SPACE_CATEGORY_MISMATCH,
    ArticleCreationError,
    ArticleVersionWriteError,
    autosave_draft,
    create_article,
)

MANAGE_ARTICLE_PAGE_SIZE = 20
_CREATE_FORM_ERROR_CODES = {
    ARTICLE_CREATE_INVALID_INPUT,
    SPACE_CATEGORY_MISMATCH,
}
_AUTOSAVE_FIELDS = frozenset(
    {
        "draft_id",
        "expected_lock_version",
        "title",
        "summary",
        "applicable_scope",
        "body_text",
        "change_summary",
    }
)
_AUTOSAVE_CONFLICT_CODES = {
    DRAFT_CONFLICT,
    DRAFT_NOT_CURRENT,
    INVALID_DRAFT_STATE,
    MODEL_CONSISTENCY_FAILED,
}


def _autosave_error(*, code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "error": {"code": code, "message": message}},
        status=status,
    )


def _parse_autosave_json(request: HttpRequest) -> tuple[dict | None, JsonResponse | None]:
    if request.content_type != "application/json":
        return None, _autosave_error(
            code="INVALID_JSON",
            message="请求必须使用 application/json。",
            status=400,
        )
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, _autosave_error(
            code="INVALID_JSON",
            message="请求正文不是有效的 JSON 对象。",
            status=400,
        )
    if not isinstance(payload, dict):
        return None, _autosave_error(
            code="INVALID_JSON",
            message="请求正文必须是 JSON 对象。",
            status=400,
        )
    if unknown_fields := payload.keys() - _AUTOSAVE_FIELDS:
        return None, _autosave_error(
            code="UNKNOWN_FIELDS",
            message=f"请求包含不支持的字段：{', '.join(sorted(unknown_fields))}。",
            status=400,
        )
    if missing_fields := _AUTOSAVE_FIELDS - payload.keys():
        return None, _autosave_error(
            code="INVALID_REQUEST",
            message=f"请求缺少必填字段：{', '.join(sorted(missing_fields))}。",
            status=400,
        )
    return payload, None


def _map_autosave_service_error(error: ArticleVersionWriteError) -> JsonResponse:
    if error.code == ARTICLE_VERSION_WRITE_PERMISSION_DENIED:
        return _autosave_error(code=error.code, message=error.public_message, status=403)
    if error.code == DRAFT_NOT_FOUND_OR_INACCESSIBLE:
        return _autosave_error(code=error.code, message=error.public_message, status=404)
    if error.code in _AUTOSAVE_CONFLICT_CODES:
        return _autosave_error(code=error.code, message=error.public_message, status=409)
    if error.code == ARTICLE_VERSION_WRITE_INVALID_INPUT:
        return _autosave_error(code=error.code, message=error.public_message, status=400)
    if error.code == DATABASE_WRITE_FAILED:
        return _autosave_error(code=error.code, message=error.public_message, status=503)
    return _autosave_error(
        code="AUTOSAVE_FAILED",
        message="系统暂时无法自动保存，请稍后重试或联系管理员。",
        status=503,
    )


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


@manage_post_json_page
def manage_article_autosave(request: HttpRequest, kb_no: str) -> HttpResponse:
    """校验完整草稿快照，并仅通过正式 Service 执行 autosave CAS。"""

    try:
        get_manage_working_article_detail(actor=request.user, kb_no=kb_no)
    except ManageWorkingArticleReadError as error:
        if error.code == MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE:
            return _autosave_error(
                code=DRAFT_NOT_FOUND_OR_INACCESSIBLE,
                message="草稿不存在或不可访问。",
                status=404,
            )
        return _autosave_error(
            code="PERMISSION_DENIED",
            message=error.public_message,
            status=403,
        )

    payload, parse_error = _parse_autosave_json(request)
    if parse_error is not None:
        return parse_error
    assert payload is not None

    identity_form = ArticleAutosaveIdentityForm(data=payload)
    if not identity_form.is_valid():
        return _autosave_error(
            code="INVALID_REQUEST",
            message="草稿身份或锁版本无效。",
            status=400,
        )

    content_data = {
        **payload,
        "applicable_scope": json.dumps(payload["applicable_scope"], ensure_ascii=False),
    }
    content_form = ArticleDraftForm(data=content_data)
    if not content_form.is_valid():
        return _autosave_error(
            code="INVALID_CONTENT",
            message="当前内容无法自动保存，请检查输入。",
            status=400,
        )

    try:
        article = Article.objects.get(kb_no=kb_no)
    except Article.DoesNotExist:
        return _autosave_error(
            code=DRAFT_NOT_FOUND_OR_INACCESSIBLE,
            message="草稿不存在或不可访问。",
            status=404,
        )
    identity = identity_form.cleaned_data
    content = content_form.cleaned_data
    try:
        draft = autosave_draft(
            actor=request.user,
            article=article,
            draft_id=identity["draft_id"],
            expected_lock_version=identity["expected_lock_version"],
            title=content["title"],
            summary=content["summary"],
            applicable_scope=content["applicable_scope"],
            body_text=content["body_text"],
            change_summary=content["change_summary"],
        )
    except ArticleVersionWriteError as error:
        return _map_autosave_service_error(error)

    return JsonResponse(
        {
            "ok": True,
            "draft": {
                "id": str(draft.pk),
                "version_no": draft.version_no,
                "lock_version": draft.lock_version,
                "updated_at": draft.updated_at.isoformat(),
            },
        }
    )


@manage_get_page
def manage_article_edit(request: HttpRequest, kb_no: str) -> HttpResponse:
    """展示 current DRAFT 的无写入编辑器基础页。"""

    try:
        detail = get_manage_working_article_detail(actor=request.user, kb_no=kb_no)
    except ManageWorkingArticleReadError as error:
        if error.code == MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE:
            return HttpResponseNotFound("未找到可查看的文章草稿。")
        return HttpResponse(error.public_message, status=403)

    form = ArticleDraftForm(
        initial={
            "title": detail.title,
            "summary": detail.summary,
            "applicable_scope": detail.applicable_scope,
            "body_text": detail.body_text,
            "change_summary": detail.change_summary,
        }
    )
    return render(
        request,
        "knowledge/manage/edit.html",
        {"detail": detail, "form": form},
    )
