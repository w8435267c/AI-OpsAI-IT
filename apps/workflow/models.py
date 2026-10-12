"""工作流事务消息与幂等记录的数据模型。"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class WorkflowEventType(models.TextChoices):
    """Task 13 首批可投递业务事件。"""

    REVIEW_SUBMITTED = "review_submitted", _("提交审核")
    REVIEW_REJECTED = "review_rejected", _("审核驳回")
    REVIEW_APPROVED_PUBLISHED = "review_approved_published", _("审核通过并发布")


class WorkflowOutboxStatus(models.TextChoices):
    PENDING = "pending", _("待处理")
    SENT = "sent", _("已发送")
    FAILED = "failed", _("发送失败")


class WorkflowOutboxEvent(models.Model):
    """业务事务内写入、由未来 Dispatcher 异步处理的事务消息。"""

    id = models.UUIDField(
        _("Outbox 事件 ID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="工作流事务消息主键，使用 UUID。",
    )
    event_type = models.CharField(
        _("事件类型"),
        max_length=64,
        choices=WorkflowEventType.choices,
        db_comment="等待外部处理的稳定业务事件类型。",
    )
    dedupe_key = models.CharField(
        _("去重键"),
        max_length=255,
        unique=True,
        db_comment="由未来业务 Service 生成的确定性事件去重键。",
    )
    payload = models.JSONField(
        _("业务载荷"),
        default=dict,
        blank=True,
        db_comment="不含密码、令牌、Cookie、Authorization 或数据库 DSN 的业务引用。",
    )
    status = models.CharField(
        _("投递状态"),
        max_length=16,
        choices=WorkflowOutboxStatus.choices,
        default=WorkflowOutboxStatus.PENDING,
        db_comment="事务消息的最小投递状态。",
    )
    attempt_count = models.PositiveIntegerField(
        _("尝试次数"),
        default=0,
        db_comment="Dispatcher 已执行的投递尝试次数。",
    )
    available_at = models.DateTimeField(
        _("可处理时间"),
        default=timezone.now,
        db_comment="消息可被未来 Dispatcher 选取的最早时间。",
    )
    last_error = models.TextField(
        _("最近错误"),
        blank=True,
        default="",
        db_comment="脱敏后的最近错误摘要，不保存完整异常堆栈或秘密。",
    )
    sent_at = models.DateTimeField(
        _("发送时间"),
        null=True,
        blank=True,
        db_comment="消息成功发送时间；未发送时为空。",
    )
    created_at = models.DateTimeField(
        _("创建时间"),
        auto_now_add=True,
        db_comment="事务消息首次创建时间。",
    )
    updated_at = models.DateTimeField(
        _("更新时间"),
        auto_now=True,
        db_comment="事务消息最后更新时间。",
    )

    class Meta:
        db_table = "workflow_outbox_event"
        db_table_comment = "工作流事务内持久化、等待未来外部投递的 Outbox 消息。"
        verbose_name = _("工作流 Outbox 事件")
        verbose_name_plural = _("工作流 Outbox 事件")
        ordering = ("available_at", "created_at")
        indexes = [
            models.Index(
                fields=("status", "available_at"),
                name="wf_out_status_avail_idx",
            ),
            models.Index(
                fields=("event_type", "created_at"),
                name="wf_out_type_created_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=WorkflowOutboxStatus.values),
                name="wf_out_status_valid_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=WorkflowOutboxStatus.PENDING) | Q(sent_at__isnull=True),
                name="wf_out_pending_unsent_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=WorkflowOutboxStatus.SENT) | Q(sent_at__isnull=False),
                name="wf_out_sent_time_ck",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.status == WorkflowOutboxStatus.PENDING and self.sent_at is not None:
            errors["sent_at"] = _("待处理消息不能填写发送时间。")
        if self.status == WorkflowOutboxStatus.SENT and self.sent_at is None:
            errors["sent_at"] = _("已发送消息必须填写发送时间。")
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.event_type} [{self.status}] {self.dedupe_key}"


class IdempotencyOperation(models.TextChoices):
    SUBMIT = "submit", _("提交审核")
    REJECT = "reject", _("审核驳回")
    APPROVE_PUBLISH = "approve_publish", _("审核通过并发布")


class IdempotencyStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", _("处理中")
    COMPLETED = "completed", _("已完成")


class WorkflowIdempotencyRecord(models.Model):
    """未来 Task 13 Service 的请求幂等占位与安全重放结果。"""

    id = models.UUIDField(
        _("幂等记录 ID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="工作流幂等记录主键，使用 UUID。",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("操作者"),
        on_delete=models.PROTECT,
        related_name="workflow_idempotency_records",
        db_comment="发起幂等业务操作的平台用户。",
    )
    operation = models.CharField(
        _("操作"),
        max_length=32,
        choices=IdempotencyOperation.choices,
        db_comment="Task 13 受控幂等业务操作。",
    )
    key = models.CharField(
        _("幂等键"),
        max_length=128,
        db_comment="调用方提供的非秘密 Idempotency-Key。",
    )
    request_fingerprint = models.CharField(
        _("请求指纹"),
        max_length=64,
        validators=[
            RegexValidator(
                regex=r"^[0-9a-f]{64}$",
                message=_("请求指纹必须是 64 位小写 SHA-256 十六进制字符串。"),
            )
        ],
        db_comment="目标与关键请求参数生成的稳定 SHA-256 十六进制摘要。",
    )
    status = models.CharField(
        _("幂等状态"),
        max_length=16,
        choices=IdempotencyStatus.choices,
        default=IdempotencyStatus.IN_PROGRESS,
        db_comment="幂等操作的最小处理状态。",
    )
    result_code = models.CharField(
        _("结果代码"),
        max_length=64,
        blank=True,
        default="",
        db_comment="完成后用于安全重放的业务结果代码。",
    )
    result_payload = models.JSONField(
        _("结果载荷"),
        default=dict,
        blank=True,
        db_comment="不含秘密、Cookie 或令牌的安全重放结果。",
    )
    created_at = models.DateTimeField(
        _("创建时间"),
        auto_now_add=True,
        db_comment="幂等记录首次创建时间。",
    )
    updated_at = models.DateTimeField(
        _("更新时间"),
        auto_now=True,
        db_comment="幂等记录最后更新时间。",
    )

    class Meta:
        db_table = "workflow_idempotency_record"
        db_table_comment = "工作流重复请求控制与安全结果重放记录。"
        verbose_name = _("工作流幂等记录")
        verbose_name_plural = _("工作流幂等记录")
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("status", "created_at"),
                name="wf_idem_status_created_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("actor", "operation", "key"),
                name="wf_idem_actor_op_key_uniq",
            ),
            models.CheckConstraint(
                condition=Q(operation__in=IdempotencyOperation.values),
                name="wf_idem_op_valid_ck",
            ),
            models.CheckConstraint(
                condition=Q(status__in=IdempotencyStatus.values),
                name="wf_idem_status_valid_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=IdempotencyStatus.COMPLETED) | ~Q(result_code=""),
                name="wf_idem_completed_result_ck",
            ),
        ]

    def clean(self):
        super().clean()
        if self.status == IdempotencyStatus.COMPLETED and not self.result_code.strip():
            raise ValidationError({"result_code": _("已完成的幂等记录必须填写结果代码。")})

    def __str__(self) -> str:
        return f"{self.actor_id} {self.operation} {self.key}"
