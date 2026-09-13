"""真实 Client 请求覆盖账号门槛、入口区分及未授权写入。"""

from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase
from django.urls import reverse
from wagtail.users.models import UserProfile

from apps.accounts.models import Department, User, UserDepartment

PASSWORD = "F03A-synthetic-password-only"


class AccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="f03a_operator", password=PASSWORD)
        cls.access = Permission.objects.get(
            content_type__app_label="wagtailadmin", codename="access_admin"
        )
        cls.user.user_permissions.add(cls.access)
        cls.target = User.objects.create_user(username="f03a_target", password=PASSWORD)
        cls.group = Group.objects.create(name="f03a_fixture_group")

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def post(self, url, data=None):
        payload = dict(data or {})
        payload["csrfmiddlewaretoken"] = self.client.cookies["csrftoken"].value
        return self.client.post(url, payload)

    def login(self, user=None, password=PASSWORD):
        user = user or self.user
        response = self.client.get("/cms/login/")
        self.assertEqual(response.status_code, 200)
        return self.post("/cms/login/", {"username": user.username, "password": password})

    def allowed_login(self):
        self.assertRedirects(self.login(), "/cms/", fetch_redirect_response=False)
        self.assertIn(SESSION_KEY, self.client.session)
        self.assertEqual(self.client.get("/cms/").status_code, 200)
        self.assertEqual(self.client.get("/cms/account/").status_code, 200)

    def denied_entry(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/cms/login/?next="))
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        final = self.client.get(url, follow=True)
        self.assertEqual(final.status_code, 200)
        self.assertEqual(len(final.redirect_chain), 1)
        self.assertTemplateUsed(final, "wagtailadmin/login.html")

    def assert_bad_login(self, fields, *, superuser=False):
        User.objects.filter(pk=self.user.pk).update(
            is_active=True, account_status="active", is_superuser=superuser, is_staff=superuser
        )
        User.objects.filter(pk=self.user.pk).update(**fields)
        self.client = Client(enforce_csrf_checks=True)
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.denied_entry("/cms/")
        self.denied_entry("/cms/account/")

    def revoke(self, fields, *, superuser=False):
        User.objects.filter(pk=self.user.pk).update(
            is_active=True, account_status="active", is_superuser=superuser, is_staff=superuser
        )
        self.client = Client(enforce_csrf_checks=True)
        self.allowed_login()
        # 保留原 Client / cookie，仅更新数据库，证明下一请求重新核对用户状态。
        User.objects.filter(pk=self.user.pk).update(**fields)
        self.denied_entry("/cms/")
        self.denied_entry("/cms/account/")
        admin_response = self.client.get("/admin/")
        self.assertEqual(admin_response.status_code, 302)
        self.assertTrue(admin_response.url.startswith("/admin/login/"))

    def test_user_model_is_existing_accounts_user(self):
        self.assertIs(get_user_model(), User)
        self.assertEqual(User._meta.db_table, "accounts_user")

    def test_existing_migrations_and_foreign_keys(self):
        executor = MigrationExecutor(connection)
        self.assertFalse(executor.migration_plan(executor.loader.graph.leaf_nodes()))
        self.assertIn(
            ("accounts", "0002_department_userdepartment_usergroup_and_more"),
            executor.loader.applied_migrations,
        )
        self.assertNotIn("auth_user", connection.introspection.table_names())
        department = Department.objects.create(name="F03A 合成部门")
        relation = UserDepartment.objects.create(user=self.user, department=department)
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.assertEqual(relation.user.pk, self.user.pk)
        self.assertEqual(profile.user.pk, self.user.pk)
        self.assertIs(UserProfile._meta.get_field("user").remote_field.model, User)
        connection.check_constraints()

    def test_anonymous_redirects_without_loop(self):
        self.denied_entry("/cms/")
        self.denied_entry("/cms/account/")

    def test_login_post_accepts_normal_nonstaff(self):
        self.allowed_login()
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_wrong_password_rejected(self):
        response = self.login(password="incorrect-synthetic-password")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_login_requires_csrf(self):
        response = self.client.post(
            "/cms/login/", {"username": self.user.username, "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_normal_without_access_cannot_enter(self):
        response = self.login(self.target)
        self.assertEqual(response.status_code, 302)
        for url in ("/cms/", "/cms/account/"):
            final = self.client.get(url, follow=True)
            self.assertEqual(final.status_code, 200)
            self.assertEqual(len(final.redirect_chain), 1)
            self.assertTemplateUsed(final, "wagtailadmin/login.html")

    def test_staff_without_access_cannot_enter(self):
        User.objects.filter(pk=self.target.pk).update(is_staff=True)
        self.login(self.target)
        response = self.client.get("/cms/", follow=True)
        self.assertTemplateUsed(response, "wagtailadmin/login.html")
        self.assertEqual(len(response.redirect_chain), 1)
        # 同一账号有 Django Admin 入口资格；证明 staff 与 Wagtail access_admin 分离。
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_nonstaff_with_access_cannot_enter_django_admin(self):
        self.allowed_login()
        response = self.client.get(reverse("admin:accounts_user_changelist"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/login.html")
        self.assertEqual(len(response.redirect_chain), 1)

    def test_inactive_login_rejected(self):
        self.assert_bad_login({"is_active": False})

    def test_disabled_login_rejected(self):
        self.assert_bad_login({"account_status": "disabled"})

    def test_departed_login_rejected(self):
        self.assert_bad_login({"account_status": "departed"})

    def test_inactive_existing_session_rejected(self):
        self.revoke({"is_active": False})

    def test_disabled_existing_session_rejected(self):
        self.revoke({"account_status": "disabled"})

    def test_departed_existing_session_rejected(self):
        self.revoke({"account_status": "departed"})

    def test_invalid_superuser_login_rejected(self):
        for fields in (
            {"is_active": False},
            {"account_status": "disabled"},
            {"account_status": "departed"},
        ):
            with self.subTest(fields=fields):
                self.assert_bad_login(fields, superuser=True)

    def test_invalid_superuser_session_rejected(self):
        for fields in (
            {"is_active": False},
            {"account_status": "disabled"},
            {"account_status": "departed"},
        ):
            with self.subTest(fields=fields):
                self.revoke(fields, superuser=True)

    def test_access_permission_revoked_from_existing_session(self):
        self.allowed_login()
        self.user.user_permissions.clear()
        for url in ("/cms/", "/cms/account/"):
            response = self.client.get(url, follow=True)
            self.assertTemplateUsed(response, "wagtailadmin/login.html")
            self.assertEqual(len(response.redirect_chain), 1)

    def test_access_only_cannot_manage_users_or_groups_by_url(self):
        self.allowed_login()
        for name, args in [
            ("wagtailusers_users:index", []),
            ("wagtailusers_users:add", []),
            ("wagtailusers_users:edit", [self.target.pk]),
            ("wagtailusers_groups:index", []),
            ("wagtailusers_groups:add", []),
            ("wagtailusers_groups:edit", [self.group.pk]),
        ]:
            with self.subTest(route=name):
                response = self.client.get(reverse(name, args=args))
                self.assertRedirects(response, "/cms/", fetch_redirect_response=False)

    def test_unauthorized_post_cannot_change_user_or_group_permissions(self):
        self.allowed_login()
        before_user = User.objects.values().get(pk=self.target.pk)
        before_group = Group.objects.values().get(pk=self.group.pk)
        before_permissions = list(Permission.objects.order_by("pk").values())
        before_count = User.objects.count(), Group.objects.count()
        for name, args, payload in [
            (
                "wagtailusers_users:edit",
                [self.target.pk],
                {
                    "username": "f03a_escalated",
                    "is_superuser": "on",
                    "user_permissions": self.access.pk,
                },
            ),
            (
                "wagtailusers_groups:edit",
                [self.group.pk],
                {"name": "f03a_escalated", "permissions": self.access.pk},
            ),
            ("wagtailusers_users:add", [], {"username": "f03a_unauthorized_new"}),
            ("wagtailusers_groups:add", [], {"name": "f03a_unauthorized_new"}),
        ]:
            with self.subTest(route=name):
                response = self.post(reverse(name, args=args), payload)
                # 使用有效 CSRF；明确是权限拒绝，不是 403 CSRF 或 404 路由错误。
                self.assertRedirects(response, "/cms/", fetch_redirect_response=False)
        self.assertEqual(User.objects.values().get(pk=self.target.pk), before_user)
        self.assertEqual(Group.objects.values().get(pk=self.group.pk), before_group)
        self.assertFalse(self.target.user_permissions.exists())
        self.assertFalse(self.target.groups.exists())
        self.assertFalse(self.group.permissions.exists())
        self.assertEqual(list(Permission.objects.order_by("pk").values()), before_permissions)
        self.assertEqual((User.objects.count(), Group.objects.count()), before_count)

    def test_logout_removes_session_and_blocks_access(self):
        self.allowed_login()
        response = self.post("/cms/logout/")
        self.assertRedirects(response, "/cms/login/", fetch_redirect_response=False)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.denied_entry("/cms/")
        self.denied_entry("/cms/account/")
