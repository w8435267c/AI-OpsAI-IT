"""知识库核心数据模型。

依据：PRD V1.1A 第 5 章“信息架构与知识体系”、第 8 章“数据模型与字段要求”
和第 9 章“业务规则与状态模型”，以及 docs/05-Database/knowledge_models_reference.py
候选参考模型与 docs/04-Architecture 的 App 职责边界。

本模块只建立数据结构与模型级校验：
- 知识编号只实现字段、格式校验和唯一性，编号生成服务后续实现；
- 发布、驳回、下架与版本切换事务由后续 Service 负责；
- 受众“拒绝优先”的匹配逻辑由后续 Selector 负责；
- 文章版本指针只能由 knowledge.services 或 workflow.services 修改。
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

KB_NO_VALIDATOR = RegexValidator(
    regex=r"^KB-\d{6}$",
    message=_("知识编号必须符合 KB-000001 格式。"),
)


class SpaceType(models.TextChoices):
    EMPLOYEE = "employee", _("员工知识空间")
    IT_INTERNAL = "it_internal", _("IT 内部知识空间")
    ADMIN = "admin", _("管理员空间")


class ArticleType(models.TextChoices):
    TROUBLESHOOTING = "troubleshooting", _("故障处理")
    GUIDE = "guide", _("操作指南")
    SOP = "sop", _("SOP")
    CASE = "case", _("运维案例")
    ANNOUNCEMENT = "announcement", _("通知公告")
    FAQ = "faq", _("FAQ")


class AudiencePolicy(models.TextChoices):
    ALL_EMPLOYEES = "all_employees", _("全员")
    RESTRICTED = "restricted", _("指定范围")
    IT_ONLY = "it_only", _("仅 IT")


class ArticleStatus(models.TextChoices):
    ACTIVE = "active", _("正常")
    OFFLINE = "offline", _("已下架")
    ARCHIVED = "archived", _("已归档")


class VersionStatus(models.TextChoices):
    DRAFT = "draft", _("草稿")
    IN_REVIEW = "in_review", _("待审核")
    REJECTED = "rejected", _("已驳回")
    PUBLISHED = "published", _("已发布")
    SUPERSEDED = "superseded", _("已替代")


class AudienceType(models.TextChoices):
    ALL_EMPLOYEES = "all_employees", _("全员")
    DEPARTMENT = "department", _("指定部门")
    USER_GROUP = "user_group", _("指定用户组")
    USER = "user", _("指定用户")
    IT_ONLY = "it_only", _("仅 IT")


class AudienceEffect(models.TextChoices):
    ALLOW = "allow", _("允许")
    DENY = "deny", _("拒绝")


class ReviewType(models.TextChoices):
    CONTENT_REVIEW = "content_review", _("发布审核")
    PERIODIC_REVIEW = "periodic_review", _("到期复审")
    EMERGENCY_REVIEW = "emergency_review", _("紧急审核")


class ReviewDecision(models.TextChoices):
    APPROVED = "approved", _("审核通过")
    REJECTED = "rejected", _("审核驳回")
    CONTINUE_VALID = "continue_valid", _("继续有效")
    REVISION_REQUIRED = "revision_required", _("需要修订")
    OFFLINE = "offline", _("立即下架")


class KnowledgeSpace(models.Model):
    """知识空间：定义知识的管理边界与默认受众策略。"""

    id = models.UUIDField(
        _("空间 ID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="知识空间主键，使用 UUID。",
    )
    code = models.SlugField(
        _("空间编码"),
        max_length=50,
        unique=True,
        db_comment="稳定的知识空间编码，用于程序识别。",
    )
    name = models.CharField(
        _("空间名称"),
        max_length=100,
        db_comment="知识空间的中文显示名称。",
    )
    description = models.TextField(
        _("说明"),
        blank=True,
        default="",
        db_comment="知识空间用途与内容边界说明。",
    )
    space_type = models.CharField(
        _("空间类型"),
        max_length=20,
        choices=SpaceType.choices,
        db_index=True,
        db_comment="空间类型：员工、IT 内部或管理员空间。",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("空间负责人"),
        on_delete=models.PROTECT,
        related_name="owned_knowledge_spaces",
        db_comment="负责该知识空间管理与内容质量的用户。",
    )
    default_audience_policy = models.CharField(
        _("默认受众策略"),
        max_length=20,
        choices=AudiencePolicy.choices,
        default=AudiencePolicy.RESTRICTED,
        db_comment="在文章未明确覆盖时使用的默认内容受众策略。",
    )
    is_active = models.BooleanField(
        _("是否启用"),
        default=True,
        db_index=True,
        db_comment="控制知识空间是否允许继续创建和展示内容。",
    )
    created_at = models.DateTimeField(
        _("创建时间"),
        auto_now_add=True,
        db_comment="知识空间首次创建时间。",
    )
    updated_at = models.DateTimeField(
        _("更新时间"),
        auto_now=True,
        db_comment="知识空间最后更新时间。",
    )

    class Meta:
        db_table = "kb_knowledge_space"
        db_table_comment = "知识空间，定义内容管理边界与默认受众策略。"
        verbose_name = _("知识空间")
        verbose_name_plural = _("知识空间")
        ordering = ("name",)
        indexes = [
            models.Index(
                fields=("space_type", "is_active"),
                name="kb_space_type_active_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Category(models.Model):
    """知识业务分类，支持父子层级。"""

    id = models.UUIDField(
        _("分类 ID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="知识分类主键，使用 UUID。",
    )
    space = models.ForeignKey(
        KnowledgeSpace,
        verbose_name=_("知识空间"),
        on_delete=models.PROTECT,
        related_name="categories",
        db_comment="分类所属知识空间。",
    )
    parent = models.ForeignKey(
        "self",
        verbose_name=_("上级分类"),
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
        db_comment="父级分类；空值表示一级分类。",
    )
    code = models.CharField(
        _("分类编码"),
        max_length=30,
        db_comment="不可随分类名称变化的稳定业务分类编码。",
    )
    name = models.CharField(
        _("分类名称"),
        max_length=100,
        db_comment="面向员工展示的业务分类名称。",
    )
    icon = models.CharField(
        _("图标"),
        max_length=100,
        blank=True,
        db_comment="前端使用的图标名称或受控资源标识。",
    )
    sort_order = models.PositiveIntegerField(
        _("排序值"),
        default=0,
        db_comment="同层级分类的显示顺序，数值越小越靠前。",
    )
    is_active = models.BooleanField(
        _("是否启用"),
        default=True,
        db_index=True,
        db_comment="控制分类是否可用于新建知识和前台导航。",
    )
    created_at = models.DateTimeField(
        _("创建时间"),
        auto_now_add=True,
        db_comment="分类首次创建时间。",
    )
    updated_at = models.DateTimeField(
        _("更新时间"),
        auto_now=True,
        db_comment="分类最后更新时间。",
    )

    class Meta:
        db_table = "kb_category"
        db_table_comment = "知识业务分类，支持父子层级和排序。"
        verbose_name = _("知识分类")
        verbose_name_plural = _("知识分类")
        ordering = ("sort_order", "name")
        indexes = [
            models.Index(
                fields=("space", "parent", "sort_order"),
                name="kb_cat_space_parent_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("space", "code"),
                name="kb_cat_space_code_uniq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.parent_id:
            if self.parent_id == self.id:
                raise ValidationError({"parent": _("分类不能将自身设为上级分类。")})
            if self.parent.space_id != self.space_id:
                raise ValidationError({"parent": _("上级分类必须属于同一知识空间。")})

    def __str__(self) -> str:
        return self.name


class Article(models.Model):
    """文章主记录：保存稳定身份、当前指针和生命周期状态。"""

    id = models.UUIDField(
        _("文章 ID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="文章主记录内部主键，使用 UUID，不直接暴露给员工。",
    )
    kb_no = models.CharField(
        _("知识编号"),
        max_length=9,
        unique=True,
        editable=False,
        validators=(KB_NO_VALIDATOR,),
        db_comment="全局唯一且不可变的知识编号，格式为 KB-000001。",
    )
    title = models.CharField(
        _("当前标题"),
        max_length=60,
        db_comment="当前对外使用的文章标题；发布新版本时由服务层同步。",
    )
    space = models.ForeignKey(
        KnowledgeSpace,
        verbose_name=_("知识空间"),
        on_delete=models.PROTECT,
        related_name="articles",
        db_comment="文章所属知识空间，决定内容管理边界。",
    )
    category = models.ForeignKey(
        Category,
        verbose_name=_("业务分类"),
        on_delete=models.PROTECT,
        related_name="articles",
        db_comment="文章当前所属的主要业务分类。",
    )
    article_type = models.CharField(
        _("文章类型"),
        max_length=20,
        choices=ArticleType.choices,
        db_index=True,
        db_comment="文章表达模板与用途类型。",
    )
    audience_policy = models.CharField(
        _("内容受众策略"),
        max_length=20,
        choices=AudiencePolicy.choices,
        default=AudiencePolicy.RESTRICTED,
        db_comment="文章受众策略摘要；具体允许和拒绝对象存入 kb_article_audience。",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("知识负责人"),
        on_delete=models.PROTECT,
        related_name="owned_articles",
        db_comment="负责知识准确性、更新和按期复审的用户。",
    )
    article_status = models.CharField(
        _("文章状态"),
        max_length=20,
        choices=ArticleStatus.choices,
        default=ArticleStatus.ACTIVE,
        db_index=True,
        db_comment="文章主状态：正常、已下架或已归档。",
    )
    effective_at = models.DateTimeField(
        _("生效时间"),
        null=True,
        blank=True,
        db_comment="文章计划生效时间；空值表示审核发布后立即生效。",
    )
    review_due_at = models.DateTimeField(
        _("复审截止时间"),
        db_index=True,
        db_comment="知识负责人应在该时间前完成复审。",
    )
    current_published_version = models.ForeignKey(
        "ArticleVersion",
        verbose_name=_("当前发布版本"),
        on_delete=models.PROTECT,
        related_name="published_pointer_articles",
        null=True,
        blank=True,
        db_comment="当前对员工展示的已发布版本；首版发布前允许为空。",
    )
    latest_working_version = models.ForeignKey(
        "ArticleVersion",
        verbose_name=_("最新工作版本"),
        on_delete=models.PROTECT,
        related_name="working_pointer_articles",
        null=True,
        blank=True,
        db_comment="最新草稿、待审核或已驳回版本；没有工作版本时为空。",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("创建人"),
        on_delete=models.PROTECT,
        related_name="created_articles",
        db_comment="首次创建文章主记录的用户。",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("最后修改人"),
        on_delete=models.PROTECT,
        related_name="updated_articles",
        db_comment="最后修改文章主记录的用户。",
    )
    created_at = models.DateTimeField(
        _("创建时间"),
        auto_now_add=True,
        db_comment="文章主记录首次创建时间。",
    )
    updated_at = models.DateTimeField(
        _("更新时间"),
        auto_now=True,
        db_comment="文章主记录最后更新时间。",
    )

    class Meta:
        db_table = "kb_article"
        db_table_comment = "知识文章主记录，保存稳定编号、生命周期状态和版本指针。"
        verbose_name = _("知识文章")
        verbose_name_plural = _("知识文章")
        ordering = ("-updated_at",)
        indexes = [
            models.Index(
                fields=("space", "article_status"),
                name="kb_art_space_status_idx",
            ),
            models.Index(
                fields=("category", "article_status"),
                name="kb_art_cat_status_idx",
            ),
            models.Index(
                fields=("owner", "review_due_at"),
                name="kb_art_owner_due_idx",
            ),
            models.Index(
                fields=("article_status", "effective_at"),
                name="kb_art_status_effect_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.category_id and self.space_id and self.category.space_id != self.space_id:
            errors["category"] = _("业务分类必须属于文章选择的知识空间。")

        if self.current_published_version_id:
            version = self.current_published_version
            if version.article_id != self.id:
                errors["current_published_version"] = _("当前发布版本必须属于本文章。")
            elif version.status != VersionStatus.PUBLISHED:
                errors["current_published_version"] = _("当前发布版本的状态必须为“已发布”。")

        if self.latest_working_version_id:
            version = self.latest_working_version
            allowed_statuses = {
                VersionStatus.DRAFT,
                VersionStatus.IN_REVIEW,
                VersionStatus.REJECTED,
            }
            if version.article_id != self.id:
                errors["latest_working_version"] = _("最新工作版本必须属于本文章。")
            elif version.status not in allowed_statuses:
                errors["latest_working_version"] = _("最新工作版本只能是草稿、待审核或已驳回状态。")

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.kb_no} {self.title}"


class ArticleVersion(models.Model):
    """文章版本：保存可审核、可追溯的完整内容快照。"""

    id = models.UUIDField(
        _("版本 ID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="文章版本内部主键，使用 UUID。",
    )
    article = models.ForeignKey(
        Article,
        verbose_name=_("所属文章"),
        on_delete=models.PROTECT,
        related_name="versions",
        db_comment="该版本所属的文章主记录。",
    )
    version_no = models.PositiveIntegerField(
        _("版本号"),
        db_comment="文章内从 1 开始递增的整数版本号。",
    )
    status = models.CharField(
        _("版本状态"),
        max_length=20,
        choices=VersionStatus.choices,
        default=VersionStatus.DRAFT,
        db_index=True,
        db_comment="版本状态：草稿、待审核、已驳回、已发布或已替代。",
    )
    title = models.CharField(
        _("版本标题"),
        max_length=60,
        db_comment="该版本保存的标题快照。",
    )
    summary = models.CharField(
        _("摘要"),
        max_length=500,
        db_comment="搜索结果和详情页使用的文章摘要。",
    )
    applicable_scope = models.JSONField(
        _("适用范围"),
        default=dict,
        blank=True,
        db_comment="结构化适用范围，例如系统、版本、设备、部门和网络环境。",
    )
    body = models.JSONField(
        _("结构化正文"),
        default=dict,
        blank=True,
        db_comment="由富文本编辑器生成的结构化正文 JSON，是版本内容的权威来源。",
    )
    body_plaintext = models.TextField(
        _("正文纯文本"),
        blank=True,
        db_comment="从结构化正文提取的纯文本，用于检索、差异比较和后续 RAG。",
    )
    change_summary = models.CharField(
        _("版本说明"),
        max_length=500,
        db_comment="作者说明本版本相对上一版本的主要修改。",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("版本创建人"),
        on_delete=models.PROTECT,
        related_name="created_article_versions",
        db_comment="创建该版本的用户，也是自审限制的作者依据。",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("提交审核人"),
        on_delete=models.PROTECT,
        related_name="submitted_article_versions",
        null=True,
        blank=True,
        db_comment="将该版本提交审核的用户；草稿阶段为空。",
    )
    submitted_at = models.DateTimeField(
        _("提交审核时间"),
        null=True,
        blank=True,
        db_comment="版本首次或最近一次提交审核的时间。",
    )
    published_at = models.DateTimeField(
        _("发布时间"),
        null=True,
        blank=True,
        db_comment="该版本审核通过并正式发布的时间。",
    )
    created_at = models.DateTimeField(
        _("创建时间"),
        auto_now_add=True,
        db_comment="版本记录创建时间。",
    )
    updated_at = models.DateTimeField(
        _("更新时间"),
        auto_now=True,
        db_comment="版本记录最后更新时间。",
    )

    class Meta:
        db_table = "kb_article_version"
        db_table_comment = "知识文章版本，保存正文、摘要、适用范围和审核状态快照。"
        verbose_name = _("文章版本")
        verbose_name_plural = _("文章版本")
        ordering = ("article_id", "-version_no")
        indexes = [
            models.Index(
                fields=("article", "status"),
                name="kb_ver_article_status_idx",
            ),
            models.Index(
                fields=("status", "submitted_at"),
                name="kb_ver_status_submit_idx",
            ),
            models.Index(
                fields=("created_by", "created_at"),
                name="kb_ver_creator_time_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("article", "version_no"),
                name="kb_ver_article_no_uniq",
            ),
            models.UniqueConstraint(
                fields=("article",),
                condition=Q(
                    status__in=(
                        VersionStatus.DRAFT,
                        VersionStatus.IN_REVIEW,
                        VersionStatus.REJECTED,
                    )
                ),
                name="kb_ver_working_uniq",
            ),
            models.UniqueConstraint(
                fields=("article",),
                condition=Q(status=VersionStatus.PUBLISHED),
                name="kb_ver_published_uniq",
            ),
            models.CheckConstraint(
                condition=Q(version_no__gt=0),
                name="kb_ver_no_positive_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=VersionStatus.DRAFT)
                    | (Q(submitted_by__isnull=False) & Q(submitted_at__isnull=False))
                ),
                name="kb_ver_submitted_ck",
            ),
            models.CheckConstraint(
                condition=(~Q(status=VersionStatus.PUBLISHED) | Q(published_at__isnull=False)),
                name="kb_ver_published_at_ck",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.status != VersionStatus.DRAFT:
            if not self.submitted_by_id:
                errors["submitted_by"] = _("非草稿版本必须记录提交审核人。")
            if not self.submitted_at:
                errors["submitted_at"] = _("非草稿版本必须记录提交审核时间。")

        if self.status == VersionStatus.PUBLISHED and not self.published_at:
            errors["published_at"] = _("已发布版本必须记录发布时间。")

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.article.kb_no} v{self.version_no}"


class ArticleAudience(models.Model):
    """文章内容受众：记录允许或显式拒绝的部门、用户组和用户。"""

    id = models.UUIDField(
        _("受众记录 ID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="文章受众关系主键，使用 UUID。",
    )
    article = models.ForeignKey(
        Article,
        verbose_name=_("文章"),
        on_delete=models.PROTECT,
        related_name="audience_rules",
        db_comment="受该受众规则控制的文章。",
    )
    audience_type = models.CharField(
        _("受众类型"),
        max_length=20,
        choices=AudienceType.choices,
        db_comment="全员、指定部门、指定用户组、指定用户或仅 IT。",
    )
    effect = models.CharField(
        _("规则效果"),
        max_length=10,
        choices=AudienceEffect.choices,
        default=AudienceEffect.ALLOW,
        db_comment="允许或显式拒绝；拒绝规则优先于允许规则。",
    )
    department = models.ForeignKey(
        "accounts.Department",
        verbose_name=_("指定部门"),
        on_delete=models.PROTECT,
        related_name="article_audience_rules",
        null=True,
        blank=True,
        db_comment="受众类型为指定部门时的部门对象。",
    )
    user_group = models.ForeignKey(
        "accounts.UserGroup",
        verbose_name=_("指定用户组"),
        on_delete=models.PROTECT,
        related_name="article_audience_rules",
        null=True,
        blank=True,
        db_comment="受众类型为指定用户组时的内容受众用户组。",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("指定用户"),
        on_delete=models.PROTECT,
        related_name="article_audience_rules",
        null=True,
        blank=True,
        db_comment="受众类型为指定用户时的平台用户。",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("规则创建人"),
        on_delete=models.PROTECT,
        related_name="created_article_audience_rules",
        db_comment="创建或配置该受众规则的用户。",
    )
    created_at = models.DateTimeField(
        _("创建时间"),
        auto_now_add=True,
        db_comment="受众规则创建时间。",
    )

    class Meta:
        db_table = "kb_article_audience"
        db_table_comment = "文章内容受众规则，系统操作角色不得写入本表。"
        verbose_name = _("文章受众规则")
        verbose_name_plural = _("文章受众规则")
        ordering = ("article_id", "audience_type", "effect")
        indexes = [
            models.Index(
                fields=("article", "audience_type", "effect"),
                name="kb_aud_article_type_idx",
            ),
            models.Index(
                fields=("audience_type", "department"),
                name="kb_aud_type_dept_idx",
            ),
            models.Index(
                fields=("audience_type", "user_group"),
                name="kb_aud_type_group_idx",
            ),
            models.Index(
                fields=("audience_type", "user"),
                name="kb_aud_type_user_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        Q(
                            audience_type__in=(
                                AudienceType.ALL_EMPLOYEES,
                                AudienceType.IT_ONLY,
                            ),
                            effect=AudienceEffect.ALLOW,
                            department__isnull=True,
                            user_group__isnull=True,
                            user__isnull=True,
                        )
                    )
                    | Q(
                        audience_type=AudienceType.DEPARTMENT,
                        department__isnull=False,
                        user_group__isnull=True,
                        user__isnull=True,
                    )
                    | Q(
                        audience_type=AudienceType.USER_GROUP,
                        department__isnull=True,
                        user_group__isnull=False,
                        user__isnull=True,
                    )
                    | Q(
                        audience_type=AudienceType.USER,
                        department__isnull=True,
                        user_group__isnull=True,
                        user__isnull=False,
                    )
                ),
                name="kb_aud_target_shape_ck",
            ),
            models.UniqueConstraint(
                fields=("article",),
                condition=Q(audience_type=AudienceType.ALL_EMPLOYEES),
                name="kb_aud_all_uniq",
            ),
            models.UniqueConstraint(
                fields=("article",),
                condition=Q(audience_type=AudienceType.IT_ONLY),
                name="kb_aud_it_uniq",
            ),
            models.UniqueConstraint(
                fields=("article", "department", "effect"),
                condition=Q(audience_type=AudienceType.DEPARTMENT),
                name="kb_aud_dept_uniq",
            ),
            models.UniqueConstraint(
                fields=("article", "user_group", "effect"),
                condition=Q(audience_type=AudienceType.USER_GROUP),
                name="kb_aud_group_uniq",
            ),
            models.UniqueConstraint(
                fields=("article", "user", "effect"),
                condition=Q(audience_type=AudienceType.USER),
                name="kb_aud_user_uniq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        target_fields = {
            AudienceType.DEPARTMENT: "department",
            AudienceType.USER_GROUP: "user_group",
            AudienceType.USER: "user",
        }
        selected_targets = {
            "department": self.department_id,
            "user_group": self.user_group_id,
            "user": self.user_id,
        }

        if self.audience_type in {
            AudienceType.ALL_EMPLOYEES,
            AudienceType.IT_ONLY,
        }:
            if any(selected_targets.values()):
                raise ValidationError(_("全员或仅 IT 规则不能指定部门、用户组或用户。"))
            if self.effect != AudienceEffect.ALLOW:
                raise ValidationError({"effect": _("全员或仅 IT 规则只能使用允许效果。")})
            return

        required_field = target_fields.get(self.audience_type)
        if not required_field:
            raise ValidationError({"audience_type": _("不支持的受众类型。")})

        errors: dict[str, str] = {}
        for field_name, field_value in selected_targets.items():
            if field_name == required_field and not field_value:
                errors[field_name] = _("当前受众类型必须指定对应对象。")
            elif field_name != required_field and field_value:
                errors[field_name] = _("当前受众类型不能填写该对象。")

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return (
            f"{self.article.kb_no} {self.get_audience_type_display()} {self.get_effect_display()}"
        )


class ReviewRecord(models.Model):
    """审核记录：记录发布审核、到期复审和紧急审核结论。"""

    id = models.UUIDField(
        _("审核记录 ID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="审核记录主键，使用 UUID。",
    )
    article_version = models.ForeignKey(
        ArticleVersion,
        verbose_name=_("文章版本"),
        on_delete=models.PROTECT,
        related_name="review_records",
        db_comment="本次审核或复审所针对的具体文章版本。",
    )
    review_type = models.CharField(
        _("审核类型"),
        max_length=20,
        choices=ReviewType.choices,
        default=ReviewType.CONTENT_REVIEW,
        db_comment="发布审核、到期复审或紧急审核。",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("审核人"),
        on_delete=models.PROTECT,
        related_name="article_review_records",
        db_comment="执行审核并对结论负责的用户。",
    )
    decision = models.CharField(
        _("审核结论"),
        max_length=20,
        choices=ReviewDecision.choices,
        db_comment="审核通过、驳回、继续有效、需要修订或立即下架。",
    )
    comment = models.TextField(
        _("审核意见"),
        blank=True,
        db_comment="审核意见；驳回、要求修订或下架时必须填写。",
    )
    reviewed_at = models.DateTimeField(
        _("审核时间"),
        auto_now_add=True,
        db_comment="审核结论形成时间。",
    )

    class Meta:
        db_table = "kb_review_record"
        db_table_comment = "知识版本审核与复审记录，保留审核人、结论、意见和时间。"
        verbose_name = _("审核记录")
        verbose_name_plural = _("审核记录")
        ordering = ("-reviewed_at",)
        indexes = [
            models.Index(
                fields=("article_version", "reviewed_at"),
                name="kb_review_version_time_idx",
            ),
            models.Index(
                fields=("reviewer", "reviewed_at"),
                name="kb_review_user_time_idx",
            ),
            models.Index(
                fields=("decision", "reviewed_at"),
                name="kb_review_decision_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~Q(
                        decision__in=(
                            ReviewDecision.REJECTED,
                            ReviewDecision.REVISION_REQUIRED,
                            ReviewDecision.OFFLINE,
                        )
                    )
                    | ~Q(comment="")
                ),
                name="kb_review_comment_ck",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if (
            self.article_version_id
            and self.reviewer_id
            and self.article_version.created_by_id == self.reviewer_id
        ):
            errors["reviewer"] = _("文章版本作者不能审核自己提交的版本。")

        decisions_requiring_comment = {
            ReviewDecision.REJECTED,
            ReviewDecision.REVISION_REQUIRED,
            ReviewDecision.OFFLINE,
        }
        if self.decision in decisions_requiring_comment and not self.comment.strip():
            errors["comment"] = _("驳回、要求修订或立即下架时必须填写审核意见。")

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return (
            f"{self.article_version.article.kb_no} "
            f"v{self.article_version.version_no} {self.get_decision_display()}"
        )
