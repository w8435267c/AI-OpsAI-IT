"""审核工作流的 HTTP 接线；所有业务状态变更仍由正式 Service 完成。"""

from uuid import uuid4

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.shortcuts import render
from django.urls import reverse

from apps.knowledge.manage_http import manage_get_page, manage_get_post_page
from apps.knowledge.manage_readers import (
    MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
    ManageWorkingArticleReadError,
    get_manage_working_article_detail,
)

from .readers import (
    REVIEW_FORBIDDEN,
    VERSION_NOT_FOUND_OR_INACCESSIBLE,
    WorkflowReaderError,
    get_review_detail,
    list_pending_reviews,
    list_reviewed_by_me,
)
from .services import (
    APPROVE_PUBLISH_FORBIDDEN,
    ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
    DRAFT_CONFLICT,
    DRAFT_NOT_CURRENT,
    IDEMPOTENCY_CONFLICT,
    IDEMPOTENCY_IN_PROGRESS,
    INVALID_INPUT,
    PUBLISH_STATE_INCONSISTENT,
    REJECT_FORBIDDEN,
    SELF_REVIEW_FORBIDDEN,
    SUBMIT_FORBIDDEN,
    VERSION_NOT_IN_REVIEW,
    WORKFLOW_UNAVAILABLE,
    ApprovePublishArticleVersionError,
    RejectArticleVersionError,
    SubmitArticleForReviewError,
    approve_and_publish_article_version,
    reject_article_version,
    submit_article_for_review,
)
from .services import (
    VERSION_NOT_FOUND_OR_INACCESSIBLE as SERVICE_VERSION_NOT_FOUND,
)


def _reader_error_response(error: WorkflowReaderError) -> HttpResponse:
    if error.code == VERSION_NOT_FOUND_OR_INACCESSIBLE:
        return HttpResponseNotFound(error.public_message)
    if error.code == REVIEW_FORBIDDEN:
        return HttpResponse(error.public_message, status=403)
    return HttpResponse(error.public_message, status=400)


def _service_error_response(error: Exception) -> HttpResponse:
    code = getattr(error, "code", "")
    message = getattr(error, "public_message", "审核操作暂时不可用，请稍后重试。")
    if code in {ARTICLE_NOT_FOUND_OR_INACCESSIBLE, SERVICE_VERSION_NOT_FOUND}:
        return HttpResponseNotFound(message)
    if code in {
        SUBMIT_FORBIDDEN,
        REJECT_FORBIDDEN,
        APPROVE_PUBLISH_FORBIDDEN,
        SELF_REVIEW_FORBIDDEN,
    }:
        return HttpResponse(message, status=403)
    if code == INVALID_INPUT:
        return HttpResponse(message, status=400)
    if code in {
        DRAFT_NOT_CURRENT,
        DRAFT_CONFLICT,
        VERSION_NOT_IN_REVIEW,
        PUBLISH_STATE_INCONSISTENT,
        IDEMPOTENCY_CONFLICT,
        IDEMPOTENCY_IN_PROGRESS,
    }:
        return HttpResponse(message, status=409)
    if code == WORKFLOW_UNAVAILABLE:
        return HttpResponse(message, status=503)
    return HttpResponse("审核操作暂时不可用，请稍后重试。", status=503)


@manage_get_page
def review_queue(request: HttpRequest) -> HttpResponse:
    """展示当前审核员经 Scope 收窄后的待审队列。"""

    try:
        pending_reviews = list_pending_reviews(request.user)
    except WorkflowReaderError as error:
        return _reader_error_response(error)
    return render(
        request,
        "workflow/review_queue.html",
        {"page_title": "待审核文章", "pending_reviews": pending_reviews, "reviewed_records": ()},
    )


@manage_get_page
def reviewed_by_me(request: HttpRequest) -> HttpResponse:
    """展示当前审核员在当前有效范围内形成的审核记录。"""

    try:
        reviewed_records = list_reviewed_by_me(request.user)
    except WorkflowReaderError as error:
        return _reader_error_response(error)
    return render(
        request,
        "workflow/review_queue.html",
        {
            "page_title": "我已审核的文章",
            "pending_reviews": (),
            "reviewed_records": reviewed_records,
        },
    )


@manage_get_post_page
def review_detail(request: HttpRequest, version_id) -> HttpResponse:
    """查看待审版本，并以 POST 调用既有批准或驳回 Service。"""

    if request.method == "POST":
        action = request.POST.get("action")
        comment = request.POST.get("comment", "")
        idempotency_key = request.POST.get("idempotency_key", "")
        try:
            if action == "approve":
                approve_and_publish_article_version(
                    actor=request.user,
                    version_id=version_id,
                    comment=comment,
                    idempotency_key=idempotency_key,
                )
            elif action == "reject":
                reject_article_version(
                    actor=request.user,
                    version_id=version_id,
                    comment=comment,
                    idempotency_key=idempotency_key,
                )
            else:
                return HttpResponse("审核操作无效。", status=400)
        except (
            ApprovePublishArticleVersionError,
            RejectArticleVersionError,
        ) as error:
            return _service_error_response(error)
        messages.success(
            request,
            "已批准并发布，员工现在可以搜索和阅读这篇正式知识。"
            if action == "approve"
            else "已驳回并通知编辑员修改后重新提交审核。",
        )
        response = HttpResponse(status=303)
        response["Location"] = reverse("workflow:queue")
        return response

    try:
        detail = get_review_detail(actor=request.user, version_id=version_id)
    except WorkflowReaderError as error:
        return _reader_error_response(error)
    return render(
        request,
        "workflow/review_detail.html",
        {
            "detail": detail,
            "idempotency_key": str(uuid4()),
            "submission": None,
            "can_take_action": detail.target.status == "in_review",
        },
    )


@manage_get_post_page
def submit_for_review(request: HttpRequest, kb_no: str) -> HttpResponse:
    """作者提交其当前 DRAFT；读取和状态变更均复用现有安全边界。"""

    if request.method == "POST":
        try:
            expected_lock_version = int(request.POST.get("expected_lock_version", ""))
        except (TypeError, ValueError):
            return HttpResponse("草稿锁版本无效。", status=400)
        try:
            submit_article_for_review(
                actor=request.user,
                kb_no=kb_no,
                draft_id=request.POST.get("draft_id"),
                expected_lock_version=expected_lock_version,
                idempotency_key=request.POST.get("idempotency_key", ""),
            )
        except SubmitArticleForReviewError as error:
            return _service_error_response(error)
        messages.success(request, "已提交审核，当前状态为“待审核”。请等待审核员处理。")
        response = HttpResponse(status=303)
        response["Location"] = reverse("knowledge_manage:list")
        return response

    try:
        draft = get_manage_working_article_detail(actor=request.user, kb_no=kb_no)
    except ManageWorkingArticleReadError as error:
        if error.code == MANAGE_WORKING_ARTICLE_NOT_FOUND_OR_INACCESSIBLE:
            return HttpResponseNotFound(error.public_message)
        return HttpResponse(error.public_message, status=403)

    return render(
        request,
        "workflow/review_detail.html",
        {"detail": None, "idempotency_key": str(uuid4()), "submission": draft},
    )
