"""最小实验来源映射；不是审核状态机或永久批准凭证。"""

from django.conf import settings
from django.db import models


class ImportedVersionSource(models.Model):
    source_version = models.OneToOneField("knowledge.ArticleVersion", on_delete=models.PROTECT)
    content = models.ForeignKey("fusion_f04a.KnowledgeContent", on_delete=models.PROTECT)
    revision = models.OneToOneField("wagtailcore.Revision", on_delete=models.PROTECT)
    conversion_format = models.CharField(max_length=64)
    source_data = models.JSONField()
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    imported_at = models.DateTimeField(auto_now_add=True)
