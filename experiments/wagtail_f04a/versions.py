"""仅供实验程序调用；不是员工阅读接口或正式审核服务。"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from wagtail.models import Revision

from .models import KnowledgeContent


def checked_revision(content, revision_id):
    revision = Revision.objects.get(pk=revision_id)
    if (
        revision.content_type_id != content.get_content_type().pk
        or revision.base_content_type_id != content.get_base_content_type().pk
        or revision.object_id != str(content.pk)
    ):
        raise ValidationError("修订不属于目标内容")
    # 模型适配同时验证 JSON 中不可变的主键及文章关联。
    content.with_content_json(revision.content)
    return revision


def read_live(content_id):
    content = KnowledgeContent.objects.get(pk=content_id)
    if not content.live or not content.live_revision_id:
        return None
    revision = checked_revision(content, content.live_revision_id)
    obj = content.with_content_json(revision.content)
    return {"title": obj.title, "summary": obj.summary, "body": obj.body}


@transaction.atomic
def restore_draft(content_id, revision_id, user):
    content = KnowledgeContent.objects.get(pk=content_id)
    revision = checked_revision(content, revision_id)
    restored = content.with_content_json(revision.content)
    return restored.save_revision(user=user, previous_revision=revision)


@transaction.atomic
def publish_for_test(content_id, revision_id, user):
    # 上游 user=None 会跳过权限检查；此受支持入口要求真实、正常的合成用户。
    if user is None or not user.pk:
        raise PermissionDenied("必须提供测试发布者")
    user = type(user).objects.get(pk=user.pk)
    if not user.is_active or user.account_status != "active":
        raise PermissionDenied("账号状态不允许发布")
    content = KnowledgeContent.objects.get(pk=content_id)
    revision = checked_revision(content, revision_id)
    revision.publish(user=user)
