"""顺序请求下的审核契约；atomic 不代表并发安全。"""

from django.core.exceptions import PermissionDenied
from django.db import transaction
from wagtail.models import TaskState, WorkflowState

from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.versions import checked_revision

from .body_rules import require_revision_body
from .models import RejectOnlyTask, TaskSubmission
from .policy import valid_account


class Conflict(Exception):
    pass


def require_submitter(user):
    if not valid_account(user) or not user.has_perms(
        [
            "wagtailadmin.access_admin",
            "fusion_f04a.change_knowledgecontent",
            "fusion_f04a.submit_knowledgecontent",
        ]
    ):
        raise PermissionDenied("缺少有效编辑及提交资格")


def active_state(obj):
    return obj.workflow_states.filter(
        status__in=[WorkflowState.STATUS_IN_PROGRESS, WorkflowState.STATUS_NEEDS_CHANGES]
    ).first()


@transaction.atomic
def submit(content_id, revision_id, user):
    require_submitter(user)
    obj = KnowledgeContent.objects.get(pk=content_id)
    revision = checked_revision(obj, revision_id)
    if (
        obj.latest_revision_id != revision.pk
        or obj.live_revision_id == revision.pk
        or not obj.has_unpublished_changes
    ):
        raise Conflict("只能提交当前未发布草稿")
    # 共用正文规则在任务、工作流或提交记录写入前执行；首次提交与驳回后重提同一路径。
    require_revision_body(revision)
    workflow = obj.get_workflow()
    if workflow is None:
        raise Conflict("未配置有效工作流")
    tasks = list(workflow.tasks.filter(active=True).specific())
    if len(tasks) != 1 or not isinstance(tasks[0], RejectOnlyTask):
        raise Conflict("仅支持一个仅驳回任务")
    state = active_state(obj)
    if state and state.status == WorkflowState.STATUS_IN_PROGRESS:
        raise Conflict("已经有进行中的审核")
    if state:
        if state.current_task_state.revision_id == revision.pk:
            raise Conflict("驳回后请先保存新草稿")
        if state.workflow_id != workflow.pk:
            raise Conflict("工作流配置发生变化")
        state.resume(user=user)
        state.refresh_from_db()
    else:
        state = workflow.start(obj, user=user)
    if state.current_task_state.revision_id != revision.pk:
        raise Conflict("任务未绑定指定修订")
    # user 来自调用方的服务端认证上下文，与原生任务创建处于同一个 atomic。
    # create + OneToOne 唯一键：重提新增任务记录，绝不更新旧任务的身份。
    TaskSubmission.objects.create(
        task_state=state.current_task_state, revision=revision, submitted_by=user
    )
    return state


@transaction.atomic
def reject(content_id, task_state_id, user, comment=""):
    if not valid_account(user) or not user.has_perm("wagtailadmin.access_admin"):
        raise PermissionDenied("账号无后台资格")
    obj = KnowledgeContent.objects.get(pk=content_id)
    state = active_state(obj)
    if (
        not state
        or state.status != WorkflowState.STATUS_IN_PROGRESS
        or state.current_task_state_id != task_state_id
    ):
        raise Conflict("不是本对象当前进行中的任务")
    task_state = TaskState.objects.get(pk=task_state_id)
    task = task_state.task.specific
    if not isinstance(task, RejectOnlyTask) or not task.allowed_reviewer(user):
        raise PermissionDenied("无驳回资格")
    if task_state.status != TaskState.STATUS_IN_PROGRESS:
        raise Conflict("任务已结束")
    checked_revision(obj, task_state.revision_id)
    task.on_action(task_state, user, "reject", comment=comment)
    return task_state
