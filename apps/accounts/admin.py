"""账号与组织后台注册入口。"""

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group

from .forms import DepartmentAdminForm
from .models import (
    AccountStatus,
    Department,
    User,
    UserDepartment,
    UserGroup,
    UserGroupMembership,
)
from .roles import ROLE_KNOWLEDGE_ADMIN, SYSTEM_ROLE_BY_CODE


def _is_active_knowledge_admin(user):
    """知识管理员维护入口的第二层角色与账号状态检查。"""
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.account_status == AccountStatus.ACTIVE
        and user.groups.filter(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name).exists()
    )


class KnowledgeMaintenanceAdminMixin:
    """允许现有知识管理员维护组织对象，不隐式授予硬删除能力。"""

    @staticmethod
    def _eligible(user):
        return (
            user.is_authenticated
            and user.is_active
            and user.is_staff
            and user.account_status == AccountStatus.ACTIVE
        )

    def has_view_permission(self, request, obj=None):
        if not self._eligible(request.user):
            return False
        return super().has_view_permission(request, obj) or _is_active_knowledge_admin(request.user)

    def has_add_permission(self, request):
        if not self._eligible(request.user):
            return False
        return super().has_add_permission(request) or _is_active_knowledge_admin(request.user)

    def has_change_permission(self, request, obj=None):
        if not self._eligible(request.user):
            return False
        return super().has_change_permission(request, obj) or _is_active_knowledge_admin(
            request.user
        )

    def has_delete_permission(self, request, obj=None):
        if not self._eligible(request.user):
            return False
        # 知识管理员角色不获得 delete；只有已有显式 delete 权限的其他受控身份
        # （默认仅超级管理员）仍按 Django 权限体系处理。
        return super().has_delete_permission(request, obj)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "display_name", "employee_no", "account_status", "is_active")
    list_filter = ("account_status", "is_staff", "is_active")
    search_fields = ("username", "display_name", "employee_no", "dingtalk_user_id")
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "组织与钉钉信息",
            {
                "fields": (
                    "dingtalk_corp_id",
                    "dingtalk_user_id",
                    "dingtalk_union_id",
                    "employee_no",
                    "display_name",
                    "account_status",
                    "last_sync_at",
                ),
            },
        ),
    )

    # 第二层防护：即使某用户因配置漂移持有 accounts.change_user，
    # 也只有真正的超级管理员（is_superuser=True）可以在 Admin 中
    # 新增、修改或删除用户；仅持有 accounts.view_user 的角色
    # （如知识库管理员）只能只读查看。查看能力保持默认实现不变。
    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# 保护系统操作角色 Group：注销 Django 内置 GroupAdmin（其 change_group
# 权限过于宽泛，允许任意增减权限、重命名甚至删除系统角色组），
# 重新注册受保护实现 —— 非超级管理员只读，超级管理员保留管理能力。
# 只读能力仍由 auth.view_group 控制，知识库管理员可正常查看。
try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin):
    """系统操作角色后台：超级管理员专用；非超级管理员只能只读查看。"""

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Department)
class DepartmentAdmin(KnowledgeMaintenanceAdminMixin, admin.ModelAdmin):
    form = DepartmentAdminForm
    list_display = ("name", "dingtalk_dept_id", "parent", "is_active", "last_sync_at")
    list_filter = ("is_active",)
    search_fields = ("name", "dingtalk_dept_id")
    readonly_fields = ("dingtalk_dept_id", "last_sync_at", "created_at", "updated_at")


@admin.register(UserDepartment)
class UserDepartmentAdmin(KnowledgeMaintenanceAdminMixin, admin.ModelAdmin):
    list_display = ("user", "department", "is_primary", "effective_at", "expired_at")
    list_filter = ("is_primary", "department")
    search_fields = (
        "user__username",
        "user__display_name",
        "user__employee_no",
        "department__name",
    )
    autocomplete_fields = ("user", "department")
    readonly_fields = ("created_at",)


@admin.register(UserGroup)
class UserGroupAdmin(KnowledgeMaintenanceAdminMixin, admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(UserGroupMembership)
class UserGroupMembershipAdmin(KnowledgeMaintenanceAdminMixin, admin.ModelAdmin):
    list_display = ("user", "user_group", "created_at")
    list_filter = ("user_group",)
    search_fields = (
        "user__username",
        "user__display_name",
        "user__employee_no",
        "user_group__name",
    )
    autocomplete_fields = ("user", "user_group")
    readonly_fields = ("created_at",)
