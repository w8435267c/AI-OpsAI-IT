"""不可变业务审计事实的数据模型。"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditEventType(models.TextChoices):
    """Task 13 首批正式审计事件类型。"""

    REVIEW_SUBMITTED = "review_submitted", _("提交审核")
    REVIEW_REJECTED = "review_rejected", _("审核驳回")
    REVIEW_APPROVED_PUBLISHED = "review_approved_published", _("审核通过并发布")


class AuditEvent(models.Model):
    """追加式业务审计事实；正式业务代码只创建，不更新或删除。"""

    id = models.UUIDField(
        _("审计事件 ID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="追加式业务审计事件主键，使用 UUID。",
    )
    event_type = models.CharField(
        _("事件类型"),
        max_length=64,
        choices=AuditEventType.choices,
        db_comment="稳定的业务事件类型；不得保存秘密或网络凭据。",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("操作者"),
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
        db_comment="触发事件的平台用户；系统事件允许为空。",
    )
    article = models.ForeignKey(
        "knowledge.Article",
        verbose_name=_("文章"),
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
        db_comment="事件关联的文章；非文章事件允许为空。",
    )
    article_version = models.ForeignKey(
        "knowledge.ArticleVersion",
        verbose_name=_("文章版本"),
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
        db_comment="事件关联的文章版本；非版本事件允许为空。",
    )
    metadata = models.JSONField(
        _("业务上下文"),
        default=dict,
        blank=True,
        db_comment="不含秘密、凭据和完整 HTTP 头的非敏感业务上下文。",
    )
    occurred_at = models.DateTimeField(
        _("发生时间"),
        auto_now_add=True,
        db_comment="业务审计事件首次持久化时间。",
    )

    class Meta:
        db_table = "audit_event"
        db_table_comment = "追加式业务审计事实；不承载业务状态机或通知投递。"
        verbose_name = _("审计事件")
        verbose_name_plural = _("审计事件")
        ordering = ("-occurred_at",)
        default_permissions = ("add", "view")
        indexes = [
            models.Index(
                fields=("event_type", "occurred_at"),
                name="audit_type_time_idx",
            ),
            models.Index(
                fields=("article", "occurred_at"),
                name="audit_article_time_idx",
            ),
            models.Index(
                fields=("article_version", "occurred_at"),
                name="audit_version_time_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.occurred_at}"
