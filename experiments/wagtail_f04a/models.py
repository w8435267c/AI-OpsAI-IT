"""候选内容模型；保护仅覆盖实例保存/修订接口，不覆盖任意 SQL。"""

from django.core.exceptions import ValidationError
from django.db import models
from wagtail.models import DraftStateMixin, RevisionMixin, WorkflowMixin


class KnowledgeContent(WorkflowMixin, DraftStateMixin, RevisionMixin, models.Model):
    id = models.BigAutoField("内容内部 ID", primary_key=True)
    article = models.OneToOneField(
        "knowledge.Article",
        verbose_name="文章",
        on_delete=models.PROTECT,
        related_name="f04a_content",
        editable=False,
    )
    title = models.CharField("标题", max_length=255)
    summary = models.TextField("摘要", blank=True)
    body = models.TextField("正文")
    # 上游默认 True；新对象在本实验必须明确为草稿。
    live = models.BooleanField("已发布", default=False, editable=False)

    class Meta:
        verbose_name = "实验知识内容"
        permissions = [
            ("publish_knowledgecontent", "发布实验知识内容"),
            ("submit_knowledgecontent", "提交实验内容审核"),
        ]

    def __str__(self):
        return self.title

    @classmethod
    def from_db(cls, db, field_names, values):
        obj = super().from_db(db, field_names, values)
        obj._identity_pk = obj.pk
        return obj

    def _check_identity(self):
        original = getattr(self, "_identity_pk", self.pk)
        if original != self.pk:
            raise ValidationError("内容主键不可修改")
        if original is not None:
            persisted = type(self).objects.filter(pk=original).first()
            if persisted is not None and persisted.article_id != self.article_id:
                raise ValidationError("内容不可改绑文章")

    def save(self, *args, **kwargs):
        self._check_identity()
        result = super().save(*args, **kwargs)
        self._identity_pk = self.pk
        return result

    def save_revision(self, *args, **kwargs):
        self._check_identity()
        if kwargs.get("overwrite_revision") is not None:
            raise ValidationError("实验仅允许追加修订")
        return super().save_revision(*args, **kwargs)

    def with_content_json(self, content):
        self._check_identity()
        if str(content.get("pk")) != str(self.pk):
            raise ValidationError("修订主键不匹配")
        if str(content.get("article")) != str(self.article_id):
            raise ValidationError("修订不可改绑文章")
        obj = super().with_content_json(content)
        obj._identity_pk = self.pk
        return obj
