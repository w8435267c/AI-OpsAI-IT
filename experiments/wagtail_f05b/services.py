"""只支持单步骤顺序批准；外层事务保证异常回滚，不保证并发安全。"""

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import connection, transaction
from wagtail.actions.publish_revision import PublishRevisionAction
from wagtail.models import TaskState, WorkflowState

from apps.accounts.models import User
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.versions import checked_revision
from experiments.wagtail_f05a.models import TaskSubmission
from experiments.wagtail_f05a.policy import valid_account

from .eligibility import check_approval_eligibility

FINISH_ACTION = "experiments.wagtail_f05b.finish.publish_reviewed"


class ApprovalRejected(PermissionDenied):
    def __init__(self, code, reason):
        self.code = code
        super().__init__(reason)


@dataclass(frozen=True)
class _ApprovalContext:
    task_id: int
    revision_id: int
    actor_id: object
    submission: dict
    revision_content: dict


class _ReviewedPublishAction(PublishRevisionAction):
    """本次动作按审核资格授权，不给审核员授予通用 publish 权限。"""

    def __init__(self, revision, user, workflow_state, context):
        super().__init__(revision, user=user)
        self.workflow_state = workflow_state
        self.context = context

    def check(self, skip_permission_checks=False):
        ctx = self.context
        state = TaskState.objects.select_related("workflow_state", "task").get(pk=ctx.task_id)
        actor = User.objects.get(pk=ctx.actor_id)
        submission = TaskSubmission.objects.filter(task_state_id=state.pk).values().get()
        obj = KnowledgeContent.objects.get(pk=state.workflow_state.object_id)
        revision = checked_revision(obj, state.revision_id)
        if (
            skip_permission_checks
            or settings.WAGTAIL_FINISH_WORKFLOW_ACTION != FINISH_ACTION
            or not connection.in_atomic_block
            or not valid_account(actor)
            or self.user.pk != actor.pk
            or state.status != TaskState.STATUS_APPROVED
            or state.finished_by_id != actor.pk
            or state.workflow_state_id != self.workflow_state.pk
            or state.workflow_state.status != WorkflowState.STATUS_APPROVED
            or state.workflow_state.current_task_state_id != state.pk
            or not state.task.specific.allowed_reviewer(actor)
            or submission != ctx.submission
            or submission["revision_id"] != revision.pk
            or actor.pk in (revision.user_id, submission["submitted_by_id"])
            or not revision.user_id
            or revision.pk != ctx.revision_id
            or self.revision.pk != revision.pk
            or revision.content != ctx.revision_content
            or obj.latest_revision_id != revision.pk
        ):
            raise ApprovalRejected("completion_invalid", "批准完成记录或发布授权不一致")


def _publish_reviewed(workflow_state, user):
    # 仅 service 创建的这一对象带一次性上下文；无进程全局开关或永久权限跳过。
    ctx = getattr(workflow_state, "_f05b_approval_context", None)
    if ctx is None or user is None or user.pk != ctx.actor_id:
        raise ApprovalRejected("service_required", "必须通过本轮批准服务完成工作流")
    del workflow_state._f05b_approval_context
    revision = TaskState.objects.get(pk=ctx.task_id).revision
    _ReviewedPublishAction(revision, user, workflow_state, ctx).execute()


@transaction.atomic
def approve_review(task_state_id, actor):
    """唯一输入是任务和服务端认证用户；返回已批准的 TaskState。"""
    if settings.WAGTAIL_FINISH_WORKFLOW_ACTION != FINISH_ACTION:
        raise ApprovalRejected("configuration_disabled", "当前配置未开放批准服务")
    try:
        state = TaskState.objects.select_related("workflow_state").get(pk=task_state_id)
        workflow_state = state.workflow_state
        result = check_approval_eligibility(
            content_id=workflow_state.object_id, task_state_id=state.pk, user=actor
        )
        if not result.allowed:
            raise ApprovalRejected(result.code, result.reason)
        actor = User.objects.get(pk=actor.pk)
        if list(workflow_state.workflow.tasks.filter(active=True).values_list("pk", flat=True)) != [
            state.task_id
        ]:
            raise ApprovalRejected("workflow_unsupported", "仅支持一个审核任务的工作流")
        obj = KnowledgeContent.objects.get(pk=workflow_state.object_id)
        revision = checked_revision(obj, state.revision_id)
        if revision.as_object().go_live_at is not None:
            raise ApprovalRejected("scheduled_revision", "本轮只支持即时发布")
        ctx = _ApprovalContext(
            state.pk,
            revision.pk,
            actor.pk,
            TaskSubmission.objects.filter(task_state_id=state.pk).values().get(),
            revision.content,
        )
        workflow_state._f05b_approval_context = ctx
        try:
            # 原生 approve -> update -> finish -> F05B 回调，发布只发生一次。
            state.approve(user=actor)
        finally:
            if hasattr(workflow_state, "_f05b_approval_context"):
                del workflow_state._f05b_approval_context
        state.refresh_from_db()
        workflow_state.refresh_from_db()
        obj.refresh_from_db()
        if (
            state.status != TaskState.STATUS_APPROVED
            or workflow_state.status != WorkflowState.STATUS_APPROVED
            or not obj.live
            or obj.live_revision_id != ctx.revision_id
        ):
            raise ApprovalRejected("completion_invalid", "批准未完成或正式修订不一致")
        return state
    except (ObjectDoesNotExist, ValidationError, ValueError, TypeError) as exc:
        raise ApprovalRejected("binding_invalid", "任务或关联记录缺失、不一致") from exc
