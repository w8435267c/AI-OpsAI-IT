"""Django Admin 权限边界保护测试：UserAdmin 与 GroupAdmin 的第二层防护。

核心断言：只有 is_superuser=True 的超级管理员可以新增、修改、删除用户
或系统操作角色 Group；非超级管理员（即使直接持有 accounts.change_user /
auth.change_group）也必须被拒绝——直接 POST 同样被拦截，而非仅隐藏控件。
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group as SystemGroup
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from apps.accounts.admin import UserAdmin
from apps.accounts.tests.admin_helpers import build_change_post_data

User = get_user_model()


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class UserAdminProtectionTests(TestCase):
    """UserAdmin：知识库管理员只读，超级管理员不受影响。"""

    @classmethod
    def setUpTestData(cls):
        call_command("create_dev_users")
        cls.admin_user = User.objects.get(username="dev_knowledge_admin")
        cls.victim = User.objects.create_user(
            username="real_victim", password="victim-original-pass"
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin_user)

    def _change_url(self, user):
        return f"/admin/accounts/user/{user.pk}/change/"

    def test_admin_can_view_user_readonly(self):
        response = self.client.get(self._change_url(self.victim))
        self.assertEqual(response.status_code, 200)

    def test_admin_cannot_promote_self(self):
        response = self.client.post(self._change_url(self.admin_user), {"is_superuser": "on"})
        self.assertEqual(response.status_code, 403)
        self.admin_user.refresh_from_db()
        self.assertFalse(self.admin_user.is_superuser)

    def test_admin_cannot_promote_other(self):
        response = self.client.post(self._change_url(self.victim), {"is_superuser": "on"})
        self.assertEqual(response.status_code, 403)
        self.victim.refresh_from_db()
        self.assertFalse(self.victim.is_superuser)

    def test_admin_cannot_add_direct_permissions(self):
        perm = Permission.objects.get(
            content_type__app_label="knowledge", codename="delete_article"
        )
        response = self.client.post(self._change_url(self.victim), {"user_permissions": [perm.pk]})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.victim.user_permissions.filter(pk=perm.pk).exists())

    def test_admin_cannot_change_groups(self):
        group = SystemGroup.objects.get(name="知识库管理员")
        response = self.client.post(self._change_url(self.victim), {"groups": [group.pk]})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.victim.groups.filter(pk=group.pk).exists())

    def test_admin_cannot_set_password(self):
        url = f"/admin/accounts/user/{self.victim.pk}/password/"
        self.assertEqual(self.client.get(url).status_code, 403)
        response = self.client.post(url, {"password1": "Hacked2026Pw", "password2": "Hacked2026Pw"})
        self.assertEqual(response.status_code, 403)
        self.victim.refresh_from_db()
        self.assertTrue(self.victim.check_password("victim-original-pass"))

    def test_admin_cannot_edit_dingtalk_or_org_fields(self):
        response = self.client.post(
            self._change_url(self.victim),
            {
                "dingtalk_user_id": "fake-dt",
                "dingtalk_corp_id": "fake-corp",
                "employee_no": "E-9999",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.victim.refresh_from_db()
        self.assertIsNone(self.victim.dingtalk_user_id)
        self.assertIsNone(self.victim.dingtalk_corp_id)
        self.assertIsNone(self.victim.employee_no)

    def test_admin_cannot_add_or_delete_user(self):
        self.assertEqual(self.client.get("/admin/accounts/user/add/").status_code, 403)
        response = self.client.post(
            f"/admin/accounts/user/{self.victim.pk}/delete/", {"post": "yes"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.victim.pk).exists())

    def test_granted_change_user_still_blocked(self):
        # 人为直接授予 accounts.change_user（模拟配置漂移），
        # 第二层防护（is_superuser 硬条件）仍必须拦截直接 POST。
        perm = Permission.objects.get(content_type__app_label="accounts", codename="change_user")
        self.admin_user.user_permissions.add(perm)
        response = self.client.post(self._change_url(self.victim), {"is_superuser": "on"})
        self.assertEqual(response.status_code, 403)
        self.victim.refresh_from_db()
        self.assertFalse(self.victim.is_superuser)

    def test_superuser_management_intact(self):
        superuser = User.objects.create_superuser(username="ops_root", password="RootPw2026")
        client = Client()
        client.force_login(superuser)
        data = build_change_post_data(
            UserAdmin(User, admin.site), superuser, self.victim, display_name="后台维护的新名字"
        )
        response = client.post(self._change_url(self.victim), data)
        self.assertEqual(response.status_code, 302)
        self.victim.refresh_from_db()
        self.assertEqual(self.victim.display_name, "后台维护的新名字")


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class GroupAdminProtectionTests(TestCase):
    """GroupAdmin：非超级管理员只读，超级管理员管理能力保留。"""

    @classmethod
    def setUpTestData(cls):
        call_command("create_dev_users")
        cls.admin_user = User.objects.get(username="dev_knowledge_admin")

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin_user)

    def test_admin_can_view_groups_readonly(self):
        response = self.client.get("/admin/auth/group/")
        self.assertEqual(response.status_code, 200)
        group = SystemGroup.objects.get(name="知识编辑员")
        response = self.client.get(f"/admin/auth/group/{group.pk}/change/")
        self.assertEqual(response.status_code, 200)

    def test_admin_cannot_add_permissions(self):
        group = SystemGroup.objects.get(name="知识库管理员")
        perm = Permission.objects.get(
            content_type__app_label="knowledge", codename="delete_article"
        )
        response = self.client.post(
            f"/admin/auth/group/{group.pk}/change/",
            {"name": group.name, "permissions": [perm.pk]},
        )
        self.assertEqual(response.status_code, 403)
        group.refresh_from_db()
        self.assertFalse(group.permissions.filter(pk=perm.pk).exists())

    def test_admin_cannot_add_delete_group_permission(self):
        group = SystemGroup.objects.get(name="知识库管理员")
        perm = Permission.objects.get(content_type__app_label="auth", codename="delete_group")
        response = self.client.post(
            f"/admin/auth/group/{group.pk}/change/",
            {"name": group.name, "permissions": [perm.pk]},
        )
        self.assertEqual(response.status_code, 403)
        group.refresh_from_db()
        self.assertFalse(group.permissions.filter(pk=perm.pk).exists())

    def test_admin_cannot_modify_manual_group(self):
        manual = SystemGroup.objects.create(name="人工维护组")
        perm = Permission.objects.get(content_type__app_label="knowledge", codename="view_article")
        response = self.client.post(
            f"/admin/auth/group/{manual.pk}/change/",
            {"name": "人工维护组", "permissions": [perm.pk]},
        )
        self.assertEqual(response.status_code, 403)
        manual.refresh_from_db()
        self.assertFalse(manual.permissions.exists())

    def test_admin_cannot_rename_system_group(self):
        group = SystemGroup.objects.get(name="普通员工")
        response = self.client.post(
            f"/admin/auth/group/{group.pk}/change/",
            {"name": "普通员工已改名", "permissions": []},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(SystemGroup.objects.filter(name="普通员工已改名").exists())

    def test_admin_cannot_delete_group(self):
        group = SystemGroup.objects.get(name="普通员工")
        response = self.client.post(f"/admin/auth/group/{group.pk}/delete/", {"post": "yes"})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(SystemGroup.objects.filter(pk=group.pk).exists())

    def test_granted_change_group_still_blocked(self):
        # 人为直接授予 auth.change_group（模拟配置漂移），第二层防护仍必须拦截。
        perm = Permission.objects.get(content_type__app_label="auth", codename="change_group")
        self.admin_user.user_permissions.add(perm)
        group = SystemGroup.objects.get(name="知识编辑员")
        del_perm = Permission.objects.get(
            content_type__app_label="knowledge", codename="delete_article"
        )
        response = self.client.post(
            f"/admin/auth/group/{group.pk}/change/",
            {"name": group.name, "permissions": [del_perm.pk]},
        )
        self.assertEqual(response.status_code, 403)
        group.refresh_from_db()
        self.assertFalse(group.permissions.filter(pk=del_perm.pk).exists())

    def test_superuser_group_management_intact(self):
        superuser = User.objects.create_superuser(username="ops_root", password="RootPw2026")
        client = Client()
        client.force_login(superuser)
        group = SystemGroup.objects.get(name="知识编辑员")
        perm = Permission.objects.get(content_type__app_label="knowledge", codename="view_article")
        before = list(group.permissions.values_list("pk", flat=True))
        response = client.post(
            f"/admin/auth/group/{group.pk}/change/",
            {"name": "知识编辑员", "permissions": before + [perm.pk]},
        )
        self.assertEqual(response.status_code, 302)
        group.refresh_from_db()
        self.assertIn(perm, group.permissions.all())

    def test_superuser_can_delete_temporary_group(self):
        superuser = User.objects.create_superuser(username="ops_root", password="RootPw2026")
        client = Client()
        client.force_login(superuser)
        temp = SystemGroup.objects.create(name="临时测试组")
        response = client.post(f"/admin/auth/group/{temp.pk}/delete/", {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SystemGroup.objects.filter(pk=temp.pk).exists())
