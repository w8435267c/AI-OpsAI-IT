"""账号与组织数据模型。

依据：PRD V1.1A 第 4.2 节“权限设计原则”与第 8 章“数据模型与字段要求”，
以及 docs/04-Architecture 中的 App 职责边界。

系统操作角色继续使用 Django Group / Permission；
本模块的 UserGroup 只表示“知识内容受众用户组”，不得混用。
"""

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class AccountStatus(models.TextChoices):
    ACTIVE = "active", _("正常")
    DISABLED = "disabled", _("已禁用")
    DEPARTED = "departed", _("已离职")


class User(AbstractUser):
    """平台用户，在 Django 认证字段基础上补充钉钉身份与员工信息。"""

    dingtalk_corp_id = models.CharField(
        _("钉钉企业标识"),
        max_length=64,
        null=True,
        blank=True,
        db_comment="钉钉企业 corpId；未同步钉钉身份的用户为空。",
    )
    dingtalk_user_id = models.CharField(
        _("钉钉员工标识"),
        max_length=128,
        null=True,
        blank=True,
        db_comment="企业内钉钉员工标识，与钉钉企业标识组合构成唯一映射。",
    )
    dingtalk_union_id = models.CharField(
        _("钉钉跨应用标识"),
        max_length=128,
        null=True,
        blank=True,
        db_comment="钉钉跨应用人员标识，按授权能力保存，不作为主映射依据。",
    )
    employee_no = models.CharField(
        _("员工编号"),
        max_length=64,
        null=True,
        blank=True,
        db_comment="公司员工编号；允许为空，由同步或后台维护更新。",
    )
    display_name = models.CharField(
        _("显示姓名"),
        max_length=128,
        blank=True,
        default="",
        db_comment="员工真实姓名，来自钉钉通讯录或管理员维护。",
    )
    account_status = models.CharField(
        _("账号状态"),
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
        db_comment="平台账号状态：正常、已禁用或已离职。",
    )
    last_sync_at = models.DateTimeField(
        _("最近同步时间"),
        null=True,
        blank=True,
        db_comment="最近一次从钉钉同步该用户信息的时间。",
    )

    class Meta:
        db_table = "accounts_user"
        db_table_comment = "平台用户，保存钉钉身份映射、员工信息与账号状态。"
        verbose_name = "用户"
        verbose_name_plural = "用户"
        indexes = [
            models.Index(fields=["account_status"], name="accounts_user_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["dingtalk_corp_id", "dingtalk_user_id"],
                condition=Q(dingtalk_corp_id__isnull=False, dingtalk_user_id__isnull=False),
                name="accounts_user_dingtalk_uniq",
            ),
            models.UniqueConstraint(
                fields=["employee_no"],
                condition=Q(employee_no__isnull=False),
                name="accounts_user_empno_uniq",
            ),
        ]

    def __str__(self):
        return self.display_name or self.username


class Department(models.Model):
    """组织部门，支持父子层级，数据来自钉钉通讯录同步或后台维护。"""

    dingtalk_dept_id = models.CharField(
        _("钉钉部门标识"),
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_comment="钉钉通讯录中的部门唯一标识；手工维护且未同步的部门可为空。",
    )
    name = models.CharField(
        _("部门名称"),
        max_length=128,
        db_comment="部门显示名称。",
    )
    parent = models.ForeignKey(
        "self",
        verbose_name=_("父部门"),
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
        db_comment="上级部门；空值表示顶级部门。",
    )
    is_active = models.BooleanField(
        _("启用状态"),
        default=True,
        db_comment="停用后不再参与内容受众匹配与后台选择。",
    )
    last_sync_at = models.DateTimeField(
        _("最近同步时间"),
        null=True,
        blank=True,
        db_comment="最近一次从钉钉同步该部门的时间。",
    )
    created_at = models.DateTimeField(
        _("创建时间"),
        auto_now_add=True,
        db_comment="部门创建时间。",
    )
    updated_at = models.DateTimeField(
        _("更新时间"),
        auto_now=True,
        db_comment="部门最后更新时间。",
    )

    class Meta:
        db_table = "accounts_department"
        db_table_comment = "组织部门，支持父子层级，参与内容受众范围匹配。"
        verbose_name = _("部门")
        verbose_name_plural = _("部门")

    def __str__(self):
        return self.name


class UserDepartment(models.Model):
    """用户与部门的多对多关系；同一用户与同一部门仅一条记录，每用户最多一个主部门。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("用户"),
        on_delete=models.PROTECT,
        related_name="department_memberships",
        db_comment="所属用户。",
    )
    department = models.ForeignKey(
        Department,
        verbose_name=_("部门"),
        on_delete=models.PROTECT,
        related_name="user_memberships",
        db_comment="用户所属部门。",
    )
    is_primary = models.BooleanField(
        _("是否主部门"),
        default=False,
        db_comment="标记该部门是否为用户主部门；每个用户最多一个主部门。",
    )
    effective_at = models.DateTimeField(
        _("生效时间"),
        null=True,
        blank=True,
        db_comment="关系生效时间；空值表示自建立起生效。",
    )
    expired_at = models.DateTimeField(
        _("失效时间"),
        null=True,
        blank=True,
        db_comment="关系失效时间；空值表示当前仍有效。",
    )
    created_at = models.DateTimeField(
        _("创建时间"),
        auto_now_add=True,
        db_comment="关系创建时间。",
    )

    class Meta:
        db_table = "accounts_user_department"
        db_table_comment = (
            "用户与部门的多对多关系；同一用户与同一部门仅一条记录，每用户最多一个主部门。"
        )
        verbose_name = _("用户部门关系")
        verbose_name_plural = _("用户部门关系")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "department"],
                name="accounts_ud_user_dept_uniq",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(is_primary=True),
                name="accounts_ud_primary_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.user}@{self.department}"


class UserGroup(models.Model):
    """知识内容受众用户组，仅用于内容可见范围；系统操作角色仍使用 Django Group。"""

    name = models.CharField(
        _("用户组名称"),
        max_length=128,
        unique=True,
        db_comment="内容受众用户组显示名称。",
    )
    description = models.TextField(
        _("说明"),
        blank=True,
        default="",
        db_comment="用户组用途与成员范围说明。",
    )
    is_active = models.BooleanField(
        _("启用状态"),
        default=True,
        db_comment="停用后不再参与内容受众匹配与后台选择。",
    )
    created_at = models.DateTimeField(
        _("创建时间"),
        auto_now_add=True,
        db_comment="用户组创建时间。",
    )
    updated_at = models.DateTimeField(
        _("更新时间"),
        auto_now=True,
        db_comment="用户组最后更新时间。",
    )

    class Meta:
        db_table = "accounts_user_group"
        db_table_comment = (
            "知识内容受众用户组，仅用于内容可见范围；系统操作角色仍使用 Django Group。"
        )
        verbose_name = _("内容用户组")
        verbose_name_plural = _("内容用户组")

    def __str__(self):
        return self.name


class UserGroupMembership(models.Model):
    """用户与内容用户组的成员关系；同一用户与同一用户组仅一条记录。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("用户"),
        on_delete=models.PROTECT,
        related_name="user_group_memberships",
        db_comment="用户组成员。",
    )
    user_group = models.ForeignKey(
        UserGroup,
        verbose_name=_("内容用户组"),
        on_delete=models.PROTECT,
        related_name="memberships",
        db_comment="用户所属的内容用户组。",
    )
    created_at = models.DateTimeField(
        _("加入时间"),
        auto_now_add=True,
        db_comment="成员加入时间。",
    )

    class Meta:
        db_table = "accounts_user_group_membership"
        db_table_comment = "用户与内容用户组的成员关系；同一用户与同一用户组仅一条记录。"
        verbose_name = _("用户组成员关系")
        verbose_name_plural = _("用户组成员关系")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "user_group"],
                name="accounts_ugm_user_group_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.user}@{self.user_group}"
