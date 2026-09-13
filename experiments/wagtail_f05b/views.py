"""任务批准 HTTP 适配；不复制服务端资格或发布逻辑。"""

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST
from wagtail.admin.auth import require_admin_access
from wagtail.models import TaskState

from . import services
from .eligibility import check_approval_eligibility


def refusal(code, reason):
    status = (
        403
        if code
        in {
            "account_invalid",
            "reviewer_required",
            "revision_creator",
            "review_submitter",
            "configuration_disabled",
            "service_required",
        }
        else 409
    )
    return HttpResponse(reason, status=status, content_type="text/plain; charset=utf-8")


@require_admin_access
@require_GET
def review(request, task_state_id):
    state = TaskState.objects.select_related("workflow_state").filter(pk=task_state_id).first()
    if state is None:
        return refusal("binding_invalid", "审核任务不存在或已失效")
    result = check_approval_eligibility(
        content_id=state.workflow_state.object_id, task_state_id=state.pk, user=request.user
    )
    if not result.allowed:
        return refusal(result.code, result.reason)
    return render(
        request,
        "wagtail_f05b/review.html",
        {
            "task": state,
            "revision": state.revision,
            "content": state.revision.as_object(),
        },
    )


@require_admin_access
@require_POST
@csrf_protect
def approve(request, task_state_id):
    if request.GET or set(request.POST) - {"csrfmiddlewaretoken"} or request.FILES:
        return HttpResponse(
            "不接受审核人、修订或其他操作字段", status=400, content_type="text/plain; charset=utf-8"
        )
    try:
        services.approve_review(task_state_id, request.user)
    except services.ApprovalRejected as exc:
        return refusal(exc.code, str(exc))
    return render(request, "wagtail_f05b/review.html", {"approved": True})
