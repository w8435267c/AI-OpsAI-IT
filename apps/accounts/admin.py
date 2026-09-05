"""账号与组织后台注册入口。"""

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group

from .models import Department, User, UserDepartment, UserGroup, UserGroupMembership


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
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "dingtalk_dept_id", "parent", "is_active", "last_sync_at")
    list_filter = ("is_active",)
    search_fields = ("name", "dingtalk_dept_id")


@admin.register(UserDepartment)
class UserDepartmentAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "is_primary", "effective_at", "expired_at")
    list_filter = ("is_primary", "department")
    search_fields = (
        "user__username",
        "user__display_name",
        "user__employee_no",
        "department__name",
    )
    autocomplete_fields = ("user", "department")


@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(UserGroupMembership)
class UserGroupMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "user_group", "created_at")
    list_filter = ("user_group",)
    search_fields = (
        "user__username",
        "user__display_name",
        "user__employee_no",
        "user_group__name",
    )
    autocomplete_fields = ("user", "user_group")
