"""Task 9A：组织关系与内容用户组的 Admin 维护权限。"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.admin import (
    DepartmentAdmin,
    UserDepartmentAdmin,
    UserGroupAdmin,
    UserGroupMembershipAdmin,
)
from apps.accounts.models import (
    AccountStatus,
    Department,
    UserDepartment,
    UserGroup,
    UserGroupMembership,
)
from apps.accounts.tests.admin_helpers import build_change_post_data

User = get_user_model()


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class OrganizationAdminMaintenanceTests(TestCase):
    """知识库管理员可维护组织与内容组，但不能硬删除或越权。"""

    @classmethod
    def setUpTestData(cls):
        call_command("create_dev_users")
        cls.admin_user = User.objects.get(username="dev_knowledge_admin")
        cls.target = User.objects.create_user(username="org-target")
        cls.other_target = User.objects.create_user(username="org-target-2")
        cls.department = Department.objects.create(name="运维部")
        cls.user_department = UserDepartment.objects.create(
            user=cls.target, department=cls.department
        )
        cls.user_group = UserGroup.objects.create(name="一线支持")
        cls.membership = UserGroupMembership.objects.create(
            user=cls.target, user_group=cls.user_group
        )
        cls.unprivileged_staff = User.objects.create_user(
            username="unprivileged-staff", is_staff=True
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin_user)

    @staticmethod
    def _add_url(model):
        return reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_add")

    @staticmethod
    def _change_url(obj):
        return reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk])

    @staticmethod
    def _delete_url(obj):
        return reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_delete", args=[obj.pk])

    @staticmethod
    def _changelist_url(model):
        return reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")

    def test_knowledge_admin_can_open_all_maintenance_models(self):
        for model in (Department, UserDepartment, UserGroup, UserGroupMembership):
            with self.subTest(model=model.__name__):
                self.assertEqual(self.client.get(self._changelist_url(model)).status_code, 200)
                self.assertEqual(self.client.get(self._add_url(model)).status_code, 200)

    def test_unprivileged_staff_cannot_use_direct_urls(self):
        self.client.force_login(self.unprivileged_staff)
        for obj in (
            self.department,
            self.user_department,
            self.user_group,
            self.membership,
        ):
            with self.subTest(model=type(obj).__name__):
                self.assertEqual(self.client.get(self._change_url(obj)).status_code, 403)
                self.assertEqual(self.client.post(self._change_url(obj), {}).status_code, 403)

    def test_disabled_knowledge_admin_cannot_use_role_bypass(self):
        self.admin_user.account_status = AccountStatus.DISABLED
        self.admin_user.save(update_fields=["account_status"])
        self.assertEqual(self.client.get(self._add_url(Department)).status_code, 403)

    def test_knowledge_admin_can_add_department_without_sync_identity(self):
        response = self.client.post(
            self._add_url(Department),
            {
                "name": "安全运营部",
                "parent": "",
                "is_active": "on",
                "dingtalk_dept_id": "forged-sync-id",
            },
        )
        self.assertEqual(response.status_code, 302)
        department = Department.objects.get(name="安全运营部")
        self.assertIsNone(department.dingtalk_dept_id)

    def test_knowledge_admin_can_add_user_department(self):
        department = Department.objects.create(name="平台部")
        response = self.client.post(
            self._add_url(UserDepartment),
            {
                "user": self.other_target.pk,
                "department": department.pk,
                "is_primary": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            UserDepartment.objects.filter(
                user=self.other_target, department=department, is_primary=True
            ).exists()
        )

    def test_knowledge_admin_can_add_content_group_and_membership(self):
        response = self.client.post(
            self._add_url(UserGroup),
            {"name": "安全响应组", "description": "内部受众", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 302)
        group = UserGroup.objects.get(name="安全响应组")
        response = self.client.post(
            self._add_url(UserGroupMembership),
            {"user": self.other_target.pk, "user_group": group.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            UserGroupMembership.objects.filter(user=self.other_target, user_group=group).exists()
        )

    def test_knowledge_admin_can_change_allowed_fields(self):
        cases = (
            (
                DepartmentAdmin(Department, admin.site),
                self.department,
                {"name": "运维保障部", "dingtalk_dept_id": "forged-change"},
            ),
            (
                UserDepartmentAdmin(UserDepartment, admin.site),
                self.user_department,
                {"is_primary": True},
            ),
            (
                UserGroupAdmin(UserGroup, admin.site),
                self.user_group,
                {"description": "更新后的说明"},
            ),
            (
                UserGroupMembershipAdmin(UserGroupMembership, admin.site),
                self.membership,
                {"user": self.other_target.pk},
            ),
        )
        for model_admin, obj, overrides in cases:
            with self.subTest(model=type(obj).__name__):
                data = build_change_post_data(model_admin, self.admin_user, obj, **overrides)
                response = self.client.post(self._change_url(obj), data)
                self.assertEqual(response.status_code, 302)
        self.department.refresh_from_db()
        self.user_department.refresh_from_db()
        self.user_group.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertEqual(self.department.name, "运维保障部")
        self.assertIsNone(self.department.dingtalk_dept_id)
        self.assertTrue(self.user_department.is_primary)
        self.assertEqual(self.user_group.description, "更新后的说明")
        self.assertEqual(self.membership.user, self.other_target)

    def test_department_cycle_rejected_without_partial_change(self):
        child = Department.objects.create(name="运维子部门", parent=self.department)
        model_admin = DepartmentAdmin(Department, admin.site)
        data = build_change_post_data(
            model_admin,
            self.admin_user,
            self.department,
            name="不得保存的循环部门",
            parent=child.pk,
        )
        response = self.client.post(self._change_url(self.department), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("循环", str(response.context["adminform"].form.errors))
        self.department.refresh_from_db()
        self.assertIsNone(self.department.parent_id)
        self.assertEqual(self.department.name, "运维部")

    def test_knowledge_admin_cannot_hard_delete_maintenance_objects(self):
        for obj in (
            self.department,
            self.user_department,
            self.user_group,
            self.membership,
        ):
            with self.subTest(model=type(obj).__name__):
                response = self.client.post(self._delete_url(obj), {"post": "yes"})
                self.assertEqual(response.status_code, 403)
                self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())
