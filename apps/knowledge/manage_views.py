"""正式知识管理区视图。"""

import json
from uuid import uuid4

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import render
from django.urls import reverse

from apps.knowledge.docx_import import DocxImportError, import_docx_draft
from apps.knowledge.manage_forms import (
    ArticleAutosaveIdentityForm,
    ArticleCreateForm,
    ArticleDocxImportForm,
    ArticleDraftForm,
    ArticleRestoreForm,
)
from apps.knowledge.manage_http import (
    manage_get_page,
    manage_get_post_page,
    manage_post_json_page,
    manage_post_page,
)
from apps.knowledge.manage_readers import (
    MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
    ManageArticleCreateOptionsReadError,
    ManageArticleListReadError,
    ManageWorkingArticleReadError,
    get_manage_article_list,
    get_manage_working_article_detail,
)
from apps.knowledge.media_services import (
    KnowledgeMediaError,
    get_draft_media,
    remove_draft_media,
    upload_draft_media,
)
from apps.knowledge.models import Article, Category
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
    RESTORE_SOURCE_INVALID,
    RESTORE_SOURCE_WRONG_ARTICLE,
    SPACE_CATEGORY_MISMATCH,
    VERSION_NUMBER_CONFLICT,
    ArticleCreationError,
    ArticleVersionWriteError,
    autosave_draft,
    create_article,
    manual_save_draft,
    restore_article_version,
)
from apps.knowledge.version_readers import (
    ARTICLE_VERSION_HISTORY_NOT_FOUND_OR_INACCESSIBLE,
    ArticleVersionHistoryDetail,
    ArticleVersionHistoryReadError,
    get_article_version_history,
    get_article_version_history_detail,
)
from apps.workflow.readers import WorkflowReaderError, get_rejection_context

MANAGE_ARTICLE_PAGE_SIZE = 20
MANAGE_ARTICLE_HISTORY_PAGE_SIZE = 20
_CREATE_FORM_ERROR_CODES = {
    ARTICLE_CREATE_INVALID_INPUT,
    SPACE_CATEGORY_MISMATCH,
}
_DRAFT_WRITE_FIELDS = frozenset(
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
_DRAFT_WRITE_OPTIONAL_FIELDS = frozenset({"category"})
_DRAFT_WRITE_CONFLICT_CODES = {
    DRAFT_CONFLICT,
    DRAFT_NOT_CURRENT,
    INVALID_DRAFT_STATE,
    MODEL_CONSISTENCY_FAILED,
    VERSION_NUMBER_CONFLICT,
}
_RESTORE_FORM_FIELDS = frozenset(ArticleRestoreForm.base_fields) | {"csrfmiddlewaretoken"}
_RESTORE_REQUIRED_FIELDS = frozenset(ArticleRestoreForm.base_fields)
_RESTORE_NOT_FOUND_CODES = {
    DRAFT_NOT_FOUND_OR_INACCESSIBLE,
    RESTORE_SOURCE_INVALID,
    RESTORE_SOURCE_WRONG_ARTICLE,
}


def _draft_write_error(*, code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "error": {"code": code, "message": message}},
        status=status,
    )


def _parse_draft_write_json(
    request: HttpRequest,
) -> tuple[dict | None, JsonResponse | None]:
    if request.content_type != "application/json":
        return None, _draft_write_error(
            code="INVALID_JSON",
            message="请求必须使用 application/json。",
            status=400,
        )
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, _draft_write_error(
            code="INVALID_JSON",
            message="请求正文不是有效的 JSON 对象。",
            status=400,
        )
    if not isinstance(payload, dict):
        return None, _draft_write_error(
            code="INVALID_JSON",
            message="请求正文必须是 JSON 对象。",
            status=400,
        )
    if unknown_fields := payload.keys() - _DRAFT_WRITE_FIELDS - _DRAFT_WRITE_OPTIONAL_FIELDS:
        return None, _draft_write_error(
            code="UNKNOWN_FIELDS",
            message=f"请求包含不支持的字段：{', '.join(sorted(unknown_fields))}。",
            status=400,
        )
    if missing_fields := _DRAFT_WRITE_FIELDS - payload.keys():
        return None, _draft_write_error(
            code="INVALID_REQUEST",
            message=f"请求缺少必填字段：{', '.join(sorted(missing_fields))}。",
            status=400,
        )
    return payload, None


def _map_draft_write_service_error(
    error: ArticleVersionWriteError,
    *,
    fallback_code: str,
    fallback_message: str,
) -> JsonResponse:
    if error.code == ARTICLE_VERSION_WRITE_PERMISSION_DENIED:
        return _draft_write_error(code=error.code, message=error.public_message, status=403)
    if error.code == DRAFT_NOT_FOUND_OR_INACCESSIBLE:
        return _draft_write_error(code=error.code, message=error.public_message, status=404)
    if error.code in _DRAFT_WRITE_CONFLICT_CODES:
        return _draft_write_error(code=error.code, message=error.public_message, status=409)
    if error.code == ARTICLE_VERSION_WRITE_INVALID_INPUT:
        return _draft_write_error(code=error.code, message=error.public_message, status=400)
    if error.code == DATABASE_WRITE_FAILED:
        return _draft_write_error(code=error.code, message=error.public_message, status=503)
    return _draft_write_error(
        code=fallback_code,
        message=fallback_message,
        status=503,
    )


def _prepare_draft_write(
    request: HttpRequest,
    *,
    kb_no: str,
    invalid_content_message: str,
) -> tuple[Article | None, dict | None, dict | None, JsonResponse | None]:
    """复用管理权限、严格 JSON、身份与五字段内容验证。"""

    try:
        get_manage_working_article_detail(actor=request.user, kb_no=kb_no)
    except ManageWorkingArticleReadError as error:
        if error.code == MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE:
            return (
                None,
                None,
                None,
                _draft_write_error(
                    code=DRAFT_NOT_FOUND_OR_INACCESSIBLE,
                    message="草稿不存在或不可访问。",
                    status=404,
                ),
            )
        return (
            None,
            None,
            None,
            _draft_write_error(
                code="PERMISSION_DENIED",
                message=error.public_message,
                status=403,
            ),
        )

    payload, parse_error = _parse_draft_write_json(request)
    if parse_error is not None:
        return None, None, None, parse_error
    assert payload is not None

    identity_form = ArticleAutosaveIdentityForm(data=payload)
    if not identity_form.is_valid():
        return (
            None,
            None,
            None,
            _draft_write_error(
                code="INVALID_REQUEST",
                message="草稿身份或锁版本无效。",
                status=400,
            ),
        )

    try:
        article = Article.objects.select_related("space").get(kb_no=kb_no)
    except Article.DoesNotExist:
        return (
            None,
            None,
            None,
            _draft_write_error(
                code=DRAFT_NOT_FOUND_OR_INACCESSIBLE, message="草稿不存在或不可访问。", status=404
            ),
        )
    content_data = {
        **payload,
        "applicable_scope": json.dumps(payload["applicable_scope"], ensure_ascii=False),
        "category": payload.get("category"),
    }
    content_form = ArticleDraftForm(
        data=content_data,
        categories=Category.objects.filter(space=article.space, is_active=True),
    )
    if not content_form.is_valid():
        return (
            None,
            None,
            None,
            _draft_write_error(
                code="INVALID_CONTENT",
                message=invalid_content_message,
                status=400,
            ),
        )

    return article, identity_form.cleaned_data, content_form.cleaned_data, None


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


def _history_article_or_404(kb_no: str) -> Article | None:
    return Article.objects.filter(kb_no=kb_no).first()


@manage_get_page
def manage_article_history(request: HttpRequest, kb_no: str) -> HttpResponse:
    """展示经过正式 Reader 权限过滤的完整版本链。"""

    article = _history_article_or_404(kb_no)
    if article is None:
        return HttpResponseNotFound("文章版本历史不存在或不可访问。")
    try:
        history = get_article_version_history(actor=request.user, article=article)
    except ArticleVersionHistoryReadError as error:
        if error.code == ARTICLE_VERSION_HISTORY_NOT_FOUND_OR_INACCESSIBLE:
            return HttpResponseNotFound(error.public_message)
        return HttpResponse(error.public_message, status=403)

    paginator = Paginator(history, MANAGE_ARTICLE_HISTORY_PAGE_SIZE)
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
        "knowledge/manage/history_list.html",
        {
            "article": article,
            "versions": page.object_list,
            "pagination": pagination,
        },
    )


def _restore_form_initial(detail) -> dict:
    return {
        "draft_id": detail.draft_id,
        "expected_lock_version": detail.lock_version,
        "title": detail.title,
        "summary": detail.summary,
        "applicable_scope": detail.applicable_scope,
        "body_text": detail.body_text,
        "change_summary": detail.change_summary,
    }


def _render_history_detail(
    request: HttpRequest,
    detail: ArticleVersionHistoryDetail,
    *,
    restore_form: ArticleRestoreForm | None,
    status: int = 200,
) -> HttpResponse:
    return render(
        request,
        "knowledge/manage/history_detail.html",
        {
            "detail": detail,
            "scope_json": json.dumps(
                detail.applicable_scope,
                ensure_ascii=False,
                indent=2,
            ),
            "restore_form": restore_form,
        },
        status=status,
    )


@manage_get_page
def manage_article_history_detail(
    request: HttpRequest,
    kb_no: str,
    version_id,
) -> HttpResponse:
    """展示单个历史版本的只读白名单快照。"""

    try:
        detail = get_article_version_history_detail(
            actor=request.user,
            kb_no=kb_no,
            version_id=version_id,
        )
    except ArticleVersionHistoryReadError as error:
        if error.code == ARTICLE_VERSION_HISTORY_NOT_FOUND_OR_INACCESSIBLE:
            return HttpResponseNotFound(error.public_message)
        return HttpResponse(error.public_message, status=403)

    restore_form = None
    if detail.can_restore:
        try:
            working = get_manage_working_article_detail(actor=request.user, kb_no=kb_no)
        except ManageWorkingArticleReadError:
            working = None
        if working is not None:
            restore_form = ArticleRestoreForm(initial=_restore_form_initial(working))
    return _render_history_detail(request, detail, restore_form=restore_form)


def _restore_error_response(
    request: HttpRequest,
    detail: ArticleVersionHistoryDetail,
    form: ArticleRestoreForm,
    *,
    message: str,
    status: int,
) -> HttpResponse:
    form.add_error(None, message)
    return _render_history_detail(
        request,
        detail,
        restore_form=form,
        status=status,
    )


@manage_post_json_page
def manage_article_restore(
    request: HttpRequest,
    kb_no: str,
    version_id,
) -> HttpResponse:
    """以普通 HTML Form 调用正式 Restore Service。"""

    try:
        detail = get_article_version_history_detail(
            actor=request.user,
            kb_no=kb_no,
            version_id=version_id,
        )
    except ArticleVersionHistoryReadError as error:
        if error.code == ARTICLE_VERSION_HISTORY_NOT_FOUND_OR_INACCESSIBLE:
            return HttpResponseNotFound(error.public_message)
        return HttpResponse(error.public_message, status=403)

    unknown_fields = set(request.POST) - _RESTORE_FORM_FIELDS
    missing_fields = _RESTORE_REQUIRED_FIELDS - set(request.POST)
    form = ArticleRestoreForm(data=request.POST)
    if unknown_fields:
        form.add_error(
            None,
            f"请求包含不支持的字段：{', '.join(sorted(unknown_fields))}。",
        )
        return _render_history_detail(
            request,
            detail,
            restore_form=form,
            status=400,
        )
    if missing_fields:
        form.add_error(
            None,
            f"请求缺少必填字段：{', '.join(sorted(missing_fields))}。",
        )
        return _render_history_detail(
            request,
            detail,
            restore_form=form,
            status=400,
        )
    if not form.is_valid():
        return _render_history_detail(
            request,
            detail,
            restore_form=form,
            status=400,
        )

    article = _history_article_or_404(kb_no)
    if article is None:
        return HttpResponseNotFound("文章版本历史不存在或不可访问。")
    cleaned = form.cleaned_data
    try:
        restore_article_version(
            actor=request.user,
            article=article,
            source_version_id=version_id,
            draft_id=cleaned["draft_id"],
            expected_lock_version=cleaned["expected_lock_version"],
            current_title=cleaned["title"],
            current_summary=cleaned["summary"],
            current_applicable_scope=cleaned["applicable_scope"],
            current_body_text=cleaned["body_text"],
            current_change_summary=cleaned["change_summary"],
        )
    except ArticleVersionWriteError as error:
        if error.code == ARTICLE_VERSION_WRITE_PERMISSION_DENIED:
            return HttpResponse("没有恢复文章版本的权限。", status=403)
        if error.code in _RESTORE_NOT_FOUND_CODES:
            return HttpResponseNotFound("历史版本不存在或不可恢复。")
        if error.code in _DRAFT_WRITE_CONFLICT_CODES:
            return _restore_error_response(
                request,
                detail,
                form,
                message="当前草稿已发生变化，请刷新后重新确认恢复操作。",
                status=409,
            )
        if error.code == ARTICLE_VERSION_WRITE_INVALID_INPUT:
            return _restore_error_response(
                request,
                detail,
                form,
                message="恢复请求内容无效，请刷新后重新确认。",
                status=400,
            )
        return _restore_error_response(
            request,
            detail,
            form,
            message="系统暂时无法恢复历史版本，请稍后重试或联系管理员。",
            status=503,
        )

    response = HttpResponse(status=303)
    response["Location"] = reverse("knowledge_manage:edit", args=[kb_no])
    return response


def _render_article_create(
    request: HttpRequest,
    form: ArticleCreateForm,
    import_form: ArticleDocxImportForm | None = None,
    *,
    status: int = 200,
) -> HttpResponse:
    return render(
        request,
        "knowledge/manage/create.html",
        {
            "form": form,
            "import_form": import_form
            or ArticleDocxImportForm(actor=request.user, initial={"import_token": uuid4()}),
        },
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


@manage_post_page
def manage_article_docx_import(request: HttpRequest) -> HttpResponse:
    """Import one scanned .docx into a brand-new draft, never an existing article."""

    try:
        import_form = ArticleDocxImportForm(
            actor=request.user, data=request.POST, files=request.FILES
        )
        create_form = ArticleCreateForm(actor=request.user)
    except ManageArticleCreateOptionsReadError as error:
        return HttpResponse(error.public_message, status=403)
    if not import_form.is_valid():
        return _render_article_create(request, create_form, import_form, status=400)

    token = str(import_form.cleaned_data["import_token"])
    completed = request.session.get("docx_import_completed", {})
    if token in completed:
        response = HttpResponse(status=303)
        response["Location"] = reverse("knowledge_manage:edit", args=[completed[token]])
        return response
    try:
        article, parsed = import_docx_draft(
            actor=request.user,
            upload=import_form.cleaned_data["docx_file"],
            form_data=import_form.cleaned_data,
        )
    except ArticleCreationError as error:
        if error.code == ARTICLE_CREATE_PERMISSION_DENIED:
            return HttpResponse("没有创建知识的权限。", status=403)
        import_form.add_error(None, error.public_message)
        return _render_article_create(request, create_form, import_form, status=400)
    except DocxImportError as error:
        import_form.add_error(None, error.public_message)
        return _render_article_create(request, create_form, import_form, status=400)

    completed[token] = article.kb_no
    request.session["docx_import_completed"] = completed
    if parsed.warnings:
        warnings = request.session.get("docx_import_warnings", {})
        warnings[article.kb_no] = list(parsed.warnings)
        request.session["docx_import_warnings"] = warnings
    request.session.modified = True
    response = HttpResponse(status=303)
    response["Location"] = reverse("knowledge_manage:edit", args=[article.kb_no])
    return response


@manage_post_json_page
def manage_article_autosave(request: HttpRequest, kb_no: str) -> HttpResponse:
    """校验完整草稿快照，并仅通过正式 Service 执行 autosave CAS。"""

    article, identity, content, request_error = _prepare_draft_write(
        request,
        kb_no=kb_no,
        invalid_content_message="当前内容无法自动保存，请检查输入。",
    )
    if request_error is not None:
        return request_error
    assert article is not None and identity is not None and content is not None
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
            proposed_category=content["category"],
        )
    except ArticleVersionWriteError as error:
        return _map_draft_write_service_error(
            error,
            fallback_code="AUTOSAVE_FAILED",
            fallback_message="系统暂时无法自动保存，请稍后重试或联系管理员。",
        )

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


@manage_post_json_page
def manage_article_manual_save(request: HttpRequest, kb_no: str) -> HttpResponse:
    """冻结当前 DRAFT，并通过正式 Service 创建下一工作 DRAFT。"""

    article, identity, content, request_error = _prepare_draft_write(
        request,
        kb_no=kb_no,
        invalid_content_message="当前内容无法保存版本，请检查输入。",
    )
    if request_error is not None:
        return request_error
    assert article is not None and identity is not None and content is not None

    try:
        saved, draft = manual_save_draft(
            actor=request.user,
            article=article,
            draft_id=identity["draft_id"],
            expected_lock_version=identity["expected_lock_version"],
            title=content["title"],
            summary=content["summary"],
            applicable_scope=content["applicable_scope"],
            body_text=content["body_text"],
            change_summary=content["change_summary"],
            proposed_category=content["category"],
        )
    except ArticleVersionWriteError as error:
        return _map_draft_write_service_error(
            error,
            fallback_code="MANUAL_SAVE_FAILED",
            fallback_message="系统暂时无法保存版本，请稍后重试或联系管理员。",
        )

    restored_from_version_no = None
    if draft.restored_from_version_id is not None:
        restored_from_version_no = draft.restored_from_version.version_no
    return JsonResponse(
        {
            "ok": True,
            "saved": {
                "id": str(saved.pk),
                "version_no": saved.version_no,
                "status": saved.status,
                "lock_version": saved.lock_version,
            },
            "draft": {
                "id": str(draft.pk),
                "version_no": draft.version_no,
                "status": draft.status,
                "status_label": draft.get_status_display(),
                "lock_version": draft.lock_version,
                "title": draft.title,
                "summary": draft.summary,
                "applicable_scope": draft.applicable_scope,
                "body_text": draft.body_plaintext,
                "change_summary": draft.change_summary,
                "restored_from_version_no": restored_from_version_no,
                "updated_at": draft.updated_at.isoformat(),
            },
        }
    )


@manage_get_page
def manage_article_preview(request: HttpRequest, kb_no: str) -> HttpResponse:
    """只读展示 current working DRAFT 的安全预览。"""

    try:
        detail = get_manage_working_article_detail(actor=request.user, kb_no=kb_no)
    except ManageWorkingArticleReadError as error:
        if error.code == MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE:
            return HttpResponseNotFound("未找到可预览的文章草稿。")
        return HttpResponse(error.public_message, status=403)

    return render(
        request,
        "knowledge/manage/preview.html",
        {
            "detail": detail,
            "scope_json": json.dumps(
                detail.applicable_scope,
                ensure_ascii=False,
                indent=2,
            ),
        },
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
        categories=Category.objects.filter(space_id=detail.space_id, is_active=True),
        initial={
            "title": detail.title,
            "summary": detail.summary,
            "applicable_scope": detail.applicable_scope,
            "body_text": detail.body_text,
            "change_summary": detail.change_summary,
            "category": detail.proposed_category_id,
        },
    )
    import_warnings = request.session.get("docx_import_warnings", {}).get(kb_no, [])
    try:
        rejection_context = get_rejection_context(actor=request.user, kb_no=kb_no)
    except WorkflowReaderError:
        rejection_context = None
    return render(
        request,
        "knowledge/manage/edit.html",
        {
            "detail": detail,
            "form": form,
            "media_links": get_draft_media(actor=request.user, kb_no=kb_no),
            "import_warnings": import_warnings,
            "rejection_context": rejection_context,
        },
    )


@manage_post_page
def manage_article_media_upload(request: HttpRequest, kb_no: str) -> HttpResponse:
    """独立上传媒体，JSON 返回使编辑中的正文不因失败或成功而丢失。"""

    try:
        link = upload_draft_media(
            actor=request.user,
            kb_no=kb_no,
            draft_id=request.POST.get("draft_id"),
            upload=request.FILES.get("file"),
            caption=request.POST.get("caption", ""),
            body_position=request.POST.get("body_position"),
        )
    except KnowledgeMediaError as error:
        return JsonResponse(
            {"ok": False, "error": {"code": error.code, "message": error.public_message}},
            status=400 if error.code == "MEDIA_INVALID_INPUT" else 409,
        )
    return JsonResponse(
        {
            "ok": True,
            "media": {
                "id": str(link.pk),
                "kind": link.asset.kind,
                "name": link.asset.original_name,
                "caption": link.caption,
                "body_position": link.body_position,
                "scan_status": link.asset.scan_status,
                "scan_message": link.asset.scan_message,
            },
        }
    )


@manage_post_page
def manage_article_media_remove(request: HttpRequest, kb_no: str, media_id) -> HttpResponse:
    """仅停用当前草稿媒体关联，保留历史关联和私有资产。"""

    try:
        remove_draft_media(
            actor=request.user,
            kb_no=kb_no,
            draft_id=request.POST.get("draft_id"),
            media_id=media_id,
        )
    except KnowledgeMediaError as error:
        return JsonResponse(
            {"ok": False, "error": {"code": error.code, "message": error.public_message}},
            status=404 if error.code == "MEDIA_NOT_FOUND_OR_INACCESSIBLE" else 409,
        )
    return JsonResponse({"ok": True})
