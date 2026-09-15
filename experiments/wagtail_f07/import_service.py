"""单篇双修订顺序幂等导入；不审核、不发布，不提供并发保证。"""

from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.db.models import Q
from wagtail.models import Revision

from apps.accounts.models import User
from apps.knowledge.models import Article, ArticleVersion, ReviewRecord
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.versions import checked_revision
from experiments.wagtail_f05a.policy import valid_account

from .conversion import FORMAT, ConversionError, _dump, convert_version
from .models import ImportedVersionSource
from .source_codec import deserialize_source, serialize_source


class ImportRejected(ValueError):
    pass


@dataclass(frozen=True)
class ImportResult:
    content_id: int
    revision_ids: tuple[int, int]


@transaction.atomic
def import_article(article_id, actor):
    """仅供受控实验调用；输入文章 ID 和实际导入人，不接收客户端版本归属。"""
    if not isinstance(actor, User) or not actor.pk or actor._state.adding:
        raise ImportRejected("需要已保存的导入操作人")
    importer = User.objects.filter(pk=actor.pk).first()
    if not valid_account(importer):
        raise ImportRejected("导入操作人账号无效")
    if not isinstance(article_id, (UUID, str)):
        raise ImportRejected("需要文章 UUID")
    try:
        article_id = UUID(str(article_id))
    except ValueError as exc:
        raise ImportRejected("文章 UUID 无效") from exc
    article = Article.objects.filter(pk=article_id).first()
    if article is None:
        raise ImportRejected("文章不存在")
    versions = {v["id"]: v for v in ArticleVersion.objects.filter(article_id=article.pk).values()}
    p = versions.get(article.current_published_version_id)
    d = versions.get(article.latest_working_version_id)
    if (
        len(versions) != 2
        or p is None
        or d is None
        or p["status"] != "published"
        or d["status"] != "draft"
        or d["version_no"] <= p["version_no"]
    ):
        raise ImportRejected("源版本或旧指针冲突：必须是本篇旧正式版和较新草稿，且不能有额外版本")
    if article.category.space_id != article.space_id:
        raise ImportRejected("文章分类与空间不一致")
    plans = []
    for version in (p, d):
        reviews = list(
            ReviewRecord.objects.filter(article_version_id=version["id"]).order_by("pk").values()
        )
        converted = convert_version(version, reviews)
        plans.append((version["id"], converted, serialize_source(converted)))
    existing = KnowledgeContent.objects.filter(article_id=article.pk).first()
    mappings = list(
        ImportedVersionSource.objects.filter(
            Q(source_version__article_id=article.pk) | Q(content__article_id=article.pk)
        )
    )
    if existing is not None or mappings:
        return _existing_import(existing, mappings, plans)
    content = KnowledgeContent.objects.create(article=article, **plans[0][1]["content"])
    revisions = []
    for source_id, converted, encoded in plans:
        for field, value in converted["content"].items():
            setattr(content, field, value)
        content.save()
        revision = content.save_revision(user=importer, log_action=True)
        ImportedVersionSource.objects.create(
            source_version_id=source_id,
            content=content,
            revision=revision,
            conversion_format=FORMAT,
            source_data=encoded,
            imported_by=importer,
        )
        revisions.append(revision.pk)
    return ImportResult(content.pk, tuple(revisions))


def _existing_import(content, mappings, plans):
    """只证明原映射仍匹配；不检查/重置后来编辑的最新草稿或发布状态。"""
    if content is None or len(mappings) != 2:
        raise ImportRejected("导入冲突：目标或两条来源映射不完整")
    by_source = {row.source_version_id: row for row in mappings}
    if set(by_source) != {plan[0] for plan in plans}:
        raise ImportRejected("导入冲突：旧版本与来源映射不一致")
    revisions = []
    for source_id, converted, encoded in plans:
        row = by_source[source_id]
        if row.content_id != content.pk or row.conversion_format != FORMAT:
            raise ImportRejected("导入冲突：来源关联或转换格式不一致")
        try:
            stored = serialize_source(deserialize_source(row.source_data))
        except ConversionError as exc:
            raise ImportRejected("导入冲突：来源快照损坏") from exc
        # 规范 JSON 比较保留数值类型差异，覆盖全部源字段及审核信息。
        if _dump(stored) != _dump(encoded):
            raise ImportRejected("导入冲突：源数据已改变或快照不一致")
        revision = Revision.objects.filter(pk=row.revision_id).first()
        if revision is None or not isinstance(revision.content, dict):
            raise ImportRejected("导入冲突：修订缺失或快照异常")
        try:
            checked_revision(content, revision.pk)
        except (ObjectDoesNotExist, ValidationError) as exc:
            raise ImportRejected("导入冲突：修订身份或文章关联不一致") from exc
        if revision.user_id != row.imported_by_id or any(
            revision.content.get(k) != v for k, v in converted["content"].items()
        ):
            raise ImportRejected("导入冲突：历史修订内容或导入身份不一致")
        revisions.append(revision.pk)
    return ImportResult(content.pk, tuple(revisions))
