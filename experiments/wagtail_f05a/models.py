"""Wagtail 任务子类，复用 TaskState，不建立平行审核表。"""

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from wagtail.models.workflows import AbstractGroupApprovalTask

from .policy import valid_account


class RejectOnlyTask(AbstractGroupApprovalTask):
    class Meta:
        verbose_name = "实验仅驳回任务"

    def allowed_reviewer(self, user):
        return (
            valid_account(user)
            and self.active
            and self.groups.filter(id__in=user.groups.all()).exists()
        )

    def get_actions(self, obj, user):
        return [("reject", "驳回", True)] if self.allowed_reviewer(user) else []

    def on_action(self, task_state, user, action_name, **kwargs):
        if action_name != "reject" or not self.allowed_reviewer(user):
            raise PermissionDenied("仅授权审核员可以驳回；批准未开放")
        return super().on_action(task_state, user, action_name, **kwargs)

    def user_can_access_editor(self, obj, user):
        return False

    def locked_for_user(self, obj, user):
        return True


class TaskSubmission(models.Model):
    """每轮任务的提交身份；没有独立审核状态，不回填历史缺失身份。"""

    task_state = models.OneToOneField(
        "wagtailcore.TaskState",
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="submission_identity",
    )
    revision = models.ForeignKey("wagtailcore.Revision", on_delete=models.PROTECT)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
