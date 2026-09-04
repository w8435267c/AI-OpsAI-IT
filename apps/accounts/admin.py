"""账号与组织后台注册入口。"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

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
