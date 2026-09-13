"""实验后台操作端点；认证、CSRF、字段白名单及数据库事务真实生效。"""

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from wagtail.admin.auth import require_admin_access
from wagtail.models import WorkflowState
from wagtail.snippets.views.snippets import SnippetViewSet

from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04b.views import (
    DraftEditView,
    KnowledgeContentViewSet,
    close_patterns,
)

from . import services


class ReviewEditView(DraftEditView):
    def post(self, request, *args, **kwargs):
        # 重新查询而不使用 GET 时的状态，包含旧编辑表单的顺序提交。
        obj = KnowledgeContent.objects.get(pk=self.object.pk)
        if obj.workflow_states.filter(status=WorkflowState.STATUS_IN_PROGRESS).exists():
            return HttpResponse("审核中禁止编辑", status=409)
        return super().post(request, *args, **kwargs)

    def save_instance(self):
        # 实际保存边界再次校验；不宣称这是数据库并发锁。
        if (
            KnowledgeContent.objects.get(pk=self.object.pk)
            .workflow_states.filter(status=WorkflowState.STATUS_IN_PROGRESS)
            .exists()
        ):
            raise services.Conflict("审核中禁止替换草稿")
        return super().save_instance()


class ReviewViewSet(KnowledgeContentViewSet):
    edit_view_class = ReviewEditView

    def get_urlpatterns(self):
        # 包含 WorkflowMixin 新增的原生路由，但全部保持拒绝。
        return close_patterns(
            SnippetViewSet.get_urlpatterns(self), {"list", "list_results", "edit", "inspect"}
        )


@require_admin_access
def review(request, pk):
    obj = get_object_or_404(KnowledgeContent, pk=pk)
    state = services.active_state(obj)
    can_submit = request.user.has_perms(
        ["fusion_f04a.change_knowledgecontent", "fusion_f04a.submit_knowledgecontent"]
    )
    can_reject = bool(
        state
        and state.current_task_state
        and state.current_task_state.task.specific.allowed_reviewer(request.user)
    )
    if not (can_submit or can_reject):
        return HttpResponseForbidden("无本实验审核操作权限")
    if request.method != "GET":
        return HttpResponse(status=405)
    return render(
        request,
        "wagtail_f05a/review.html",
        {
            "content": obj,
            "state": state,
            "can_submit": can_submit,
            "can_reject": can_reject,
        },
    )


def operation(request, pk, kind):
    allowed = (
        {"csrfmiddlewaretoken", "revision_id"}
        if kind == "submit"
        else {"csrfmiddlewaretoken", "task_state_id", "comment"}
    )
    if set(request.POST) - allowed:
        return HttpResponseBadRequest("不接受内部状态或其他操作字段")
    key = "revision_id" if kind == "submit" else "task_state_id"
    try:
        value = int(request.POST.get(key, ""))
    except (ValueError, TypeError):
        return HttpResponseBadRequest("需要有效修订或任务 ID")
    get_object_or_404(KnowledgeContent, pk=pk)
    try:
        if kind == "submit":
            services.submit(pk, value, request.user)
        else:
            services.reject(pk, value, request.user, request.POST.get("comment", ""))
    except (services.Conflict, ValidationError, ObjectDoesNotExist):
        return HttpResponse("目标修订或任务不符合当前操作条件", status=409)
    return redirect("f05a_review", pk=pk)


@require_admin_access
@require_POST
def submit(request, pk):
    return operation(request, pk, "submit")


@require_admin_access
@require_POST
def reject(request, pk):
    return operation(request, pk, "reject")
