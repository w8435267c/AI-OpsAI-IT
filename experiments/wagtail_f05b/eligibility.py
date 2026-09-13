"""批准前只读资格校验；不是批准动作，也不提供并发保证。"""

from dataclasses import dataclass

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from wagtail.models import TaskState, WorkflowState

from apps.accounts.models import User
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.versions import checked_revision
from experiments.wagtail_f05a.models import RejectOnlyTask, TaskSubmission
from experiments.wagtail_f05a.policy import valid_account


@dataclass(frozen=True)
class ApprovalEligibility:
    allowed: bool
    code: str
    reason: str


def denied(code, reason):
    return ApprovalEligibility(False, code, reason)


def check_approval_eligibility(*, content_id, task_state_id, user):
    """user 必须来自服务端认证上下文；不接受创建者、提交者或组身份参数。

    每次重读账号和任务。返回值仅说明当前读取时刻的资格，不是授权令牌。
    每轮提交人只读取绑定本任务的实验提交记录，历史缺失时拒绝。
    """
    if not user or not user.is_authenticated or not user.pk or user._state.adding:
        return denied("account_invalid", "需要已登录且已保存的有效账号")
    actor = User.objects.filter(pk=user.pk).first()
    if not valid_account(actor):
        return denied("account_invalid", "账号不存在、未启用或业务账号状态无效")
    try:
        obj = KnowledgeContent.objects.get(pk=content_id)
        state = TaskState.objects.select_related("workflow_state__workflow", "task").get(
            pk=task_state_id
        )
        workflow_state = state.workflow_state
        if (
            state.status != TaskState.STATUS_IN_PROGRESS
            or workflow_state.status != WorkflowState.STATUS_IN_PROGRESS
            or workflow_state.current_task_state_id != state.pk
            or not workflow_state.workflow.active
            or not state.task.active
        ):
            return denied("task_inactive", "任务或工作流未进行，或不是当前任务")
        if (
            workflow_state.content_type_id != obj.get_content_type().pk
            or workflow_state.base_content_type_id != obj.get_base_content_type().pk
            or workflow_state.object_id != str(obj.pk)
            or obj.get_workflow() != workflow_state.workflow
            or not workflow_state.workflow.tasks.filter(pk=state.task_id).exists()
        ):
            return denied("binding_invalid", "任务、工作流与目标内容关联不一致")
        revision = checked_revision(obj, state.revision_id)
        if obj.latest_revision_id != revision.pk or obj.live_revision_id == revision.pk:
            return denied("binding_invalid", "受审修订不是当前未发布修订")
        task = state.task.specific
        if (
            not isinstance(task, RejectOnlyTask)
            or not task.groups.filter(pk__in=actor.groups.values("pk")).exists()
        ):
            return denied("reviewer_required", "不属于该任务实际授权的审核组")
        submission = TaskSubmission.objects.filter(task_state_id=state.pk).first()
        if not revision.user_id or submission is None or not submission.submitted_by_id:
            return denied("identity_missing", "受审修订创建者或本轮任务提交记录缺失")
        if submission.revision_id != state.revision_id:
            return denied("identity_inconsistent", "提交记录与任务的受审修订不一致")
        if actor.pk == revision.user_id:
            return denied("revision_creator", "受审修订创建者不得自审")
        if actor.pk == submission.submitted_by_id:
            return denied("review_submitter", "本次审核提交人不得自审")
    except (ObjectDoesNotExist, ValidationError, ValueError, TypeError):
        return denied("binding_invalid", "目标记录缺失或修订关联无效")
    return ApprovalEligibility(True, "allowed", "具备当前任务批准资格；尚未执行批准")
