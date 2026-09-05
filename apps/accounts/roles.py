"""系统操作角色与本地开发身份的集中定义。

依据：PRD V1.1A 第 4.1 节"用户角色"与第 4.2 节"权限设计原则"——
系统操作角色使用 Django Group / Permission 实现，与内容受众范围
（accounts.UserGroup）严格分离，不得混用。

本模块是角色代码、中文名称、权限映射与本地模拟登录固定身份的唯一来源；
管理命令、表单、视图和测试统一引用本模块，避免在多个文件散落硬编码。
"""

from dataclasses import dataclass

ROLE_EMPLOYEE = "employee"
ROLE_EDITOR = "editor"
ROLE_REVIEWER = "reviewer"
ROLE_KNOWLEDGE_ADMIN = "knowledge_admin"


@dataclass(frozen=True)
class SystemRole:
    """一个系统操作角色：稳定代码、PRD 中文名称与完整 Django 权限集合。"""

    code: str
    name: str
    permissions: tuple[str, ...]


# 权限均为 Django 内置模型权限（app_label.codename）。
# 原则：默认不授予任何 delete 权限；普通员工不获得任何模型权限，
# 内容可见性由后续第 8 步受众 Selector 决定；编辑员、审核员、管理员
# 按最小权限分别覆盖草稿管理、审核记录与知识管理。
# 审核"批准 / 驳回 / 发布 / 下架"等状态机需要自定义操作权限，
# 待对应业务步骤实现时再补充定义，本步骤不提前添加。
SYSTEM_ROLES: tuple[SystemRole, ...] = (
    SystemRole(
        code=ROLE_EMPLOYEE,
        name="普通员工",
        permissions=(),
    ),
    SystemRole(
        code=ROLE_EDITOR,
        name="知识编辑员",
        permissions=(
            "knowledge.view_knowledgespace",
            "knowledge.view_category",
            "knowledge.add_article",
            "knowledge.change_article",
            "knowledge.view_article",
            "knowledge.add_articleversion",
            "knowledge.change_articleversion",
            "knowledge.view_articleversion",
        ),
    ),
    SystemRole(
        code=ROLE_REVIEWER,
        name="知识审核员",
        permissions=(
            "knowledge.view_knowledgespace",
            "knowledge.view_category",
            "knowledge.view_article",
            "knowledge.view_articleversion",
            "knowledge.add_reviewrecord",
            "knowledge.change_reviewrecord",
            "knowledge.view_reviewrecord",
        ),
    ),
    SystemRole(
        code=ROLE_KNOWLEDGE_ADMIN,
        name="知识库管理员",
        permissions=(
            "knowledge.add_knowledgespace",
            "knowledge.change_knowledgespace",
            "knowledge.view_knowledgespace",
            "knowledge.add_category",
            "knowledge.change_category",
            "knowledge.view_category",
            "knowledge.add_article",
            "knowledge.change_article",
            "knowledge.view_article",
            "knowledge.add_articleversion",
            "knowledge.change_articleversion",
            "knowledge.view_articleversion",
            "knowledge.add_articleaudience",
            "knowledge.change_articleaudience",
            "knowledge.view_articleaudience",
            "knowledge.add_reviewrecord",
            "knowledge.change_reviewrecord",
            "knowledge.view_reviewrecord",
            # 用户模型为自定义 accounts.User，其内置权限位于 accounts app 下
            "accounts.view_user",
            "accounts.change_user",
            "auth.view_group",
            "auth.change_group",
        ),
    ),
)

SYSTEM_ROLE_BY_CODE = {role.code: role for role in SYSTEM_ROLES}
SYSTEM_ROLE_BY_NAME = {role.name: role for role in SYSTEM_ROLES}


def has_real_identity(user) -> bool:
    """判断用户是否携带真实身份特征（可用密码、超级管理员、工号、邮箱或钉钉标识）。

    本地模拟身份必须不携带任何真实身份特征；开发用户命令与模拟登录视图共用此校验。
    """
    return (
        user.has_usable_password()
        or user.is_superuser
        or bool(user.employee_no)
        or bool(user.email)
        or bool(user.dingtalk_corp_id)
        or bool(user.dingtalk_user_id)
        or bool(user.dingtalk_union_id)
    )


@dataclass(frozen=True)
class DevIdentity:
    """本地模拟登录的一个固定开发身份。"""

    username: str
    display_name: str
    role_code: str
    is_staff: bool = False


# 固定开发身份白名单：用户名带 dev_ 前缀，与真实用户明确区分；
# 仅知识库管理员需要访问 Django Admin 后台，故只有其 is_staff=True。
DEV_IDENTITIES: tuple[DevIdentity, ...] = (
    DevIdentity("dev_employee", "本地模拟-普通员工", ROLE_EMPLOYEE),
    DevIdentity("dev_editor", "本地模拟-知识编辑员", ROLE_EDITOR),
    DevIdentity("dev_reviewer", "本地模拟-知识审核员", ROLE_REVIEWER),
    DevIdentity(
        "dev_knowledge_admin",
        "本地模拟-知识库管理员",
        ROLE_KNOWLEDGE_ADMIN,
        is_staff=True,
    ),
)

DEV_IDENTITY_BY_USERNAME = {identity.username: identity for identity in DEV_IDENTITIES}
