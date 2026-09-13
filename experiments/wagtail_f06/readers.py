"""实验员工详情：业务受众与历史批准证据均通过才返回正式快照。"""

from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from wagtail.models import TaskState, WorkflowState

from apps.accounts.models import User
from apps.knowledge.models import Article
from apps.knowledge.selectors import _audience_eligible_articles
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.versions import checked_revision
from experiments.wagtail_f05a.models import RejectOnlyTask, TaskSubmission


@dataclass(frozen=True)
class EmployeeArticleDetail:
    article_id: UUID
    content_id: int
    revision_id: int
    title: str
    summary: str
    body: str


def get_employee_article_detail(user, article_id):
    """只读内部入口；无权、未发布、证据异常均返回 None，无旧内容回退。

    user 来自服务端认证上下文；重读当前账号。返回白名单值，不返回 ORM/JSON。
    多次查询不提供并发一致性保证，历史证据尚不具备永久保留保证。
    """
    if (
        not isinstance(user, User)
        or not user.is_authenticated
        or not user.pk
        or user._state.adding
        or not isinstance(article_id, (UUID, str))
    ):
        return None
    try:
        article_id = UUID(str(article_id))
    except ValueError:
        return None
    actor = User.objects.filter(pk=user.pk).first()
    article = _audience_eligible_articles(actor, base=Article.objects.filter(pk=article_id)).first()
    if article is None:
        return None
    content = KnowledgeContent.objects.filter(article_id=article.pk, live=True).first()
    if content is None or not content.live_revision_id:
        return None
    try:
        data = content.live_revision.content
    except ObjectDoesNotExist:
        return None
    if not isinstance(data, dict) or not all(
        isinstance(data.get(field), str) for field in ("title", "summary", "body")
    ):
        return None
    try:
        revision = checked_revision(content, content.live_revision_id)
    except (ObjectDoesNotExist, ValidationError, ValueError, TypeError):
        return None
    data = revision.content
    if not isinstance(data, dict) or not all(
        isinstance(data.get(field), str) for field in ("title", "summary", "body")
    ):
        return None
    # 只查该正式修订的历史批准记录；不检查最新修订、当前工作流或审核员当前权限。
    states = list(
        TaskState.objects.filter(
            revision_id=revision.pk, status=TaskState.STATUS_APPROVED
        ).select_related("workflow_state", "task")[:2]
    )
    if len(states) != 1:
        return None
    state = states[0]
    workflow = state.workflow_state
    submission = TaskSubmission.objects.filter(task_state_id=state.pk).first()
    if (
        workflow.status != WorkflowState.STATUS_APPROVED
        or workflow.current_task_state_id != state.pk
        or workflow.content_type_id != content.get_content_type().pk
        or workflow.base_content_type_id != content.get_base_content_type().pk
        or workflow.object_id != str(content.pk)
        or not isinstance(state.task.specific, RejectOnlyTask)
        or state.finished_at is None
        or not state.finished_by_id
        or not revision.user_id
        or submission is None
        or submission.revision_id != revision.pk
        or not submission.submitted_by_id
        or state.finished_by_id in (revision.user_id, submission.submitted_by_id)
    ):
        return None
    identities = {revision.user_id, submission.submitted_by_id, state.finished_by_id}
    if User.objects.filter(pk__in=identities).count() != len(identities):
        return None
    return EmployeeArticleDetail(
        article.pk, content.pk, revision.pk, data["title"], data["summary"], data["body"]
    )
