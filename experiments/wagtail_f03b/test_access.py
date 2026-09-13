"""通过真实同步和角色组授权进行请求验证，不给访问用户直接权限。"""

from io import StringIO

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts import roles
from apps.accounts.models import User
from experiments.wagtail_f03b.test_profiles import snapshot, sync

PASSWORD = "f03b-synthetic-password"


class RoleAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", profile="wagtail-poc", stdout=StringIO())
        cls.users = {}
        for identity in roles.DEV_IDENTITIES:
            code = identity.role_code
            user = User.objects.create_user(
                username="f03b_" + code, password=PASSWORD, is_staff=identity.is_staff
            )
            user.groups.add(Group.objects.get(name=roles.SYSTEM_ROLE_BY_CODE[code].name))
            cls.users[code] = user
        cls.target = User.objects.create_user(username="f03b_target", password=PASSWORD)
        cls.target_group = Group.objects.create(name="f03b_target_group")

    def login(self, code):
        self.client = Client(enforce_csrf_checks=True)
        self.client.get("/cms/login/")
        user = self.users[code]
        self.assertFalse(user.user_permissions.exists())
        self.assertFalse(user.is_superuser)
        response = self.client.post(
            "/cms/login/",
            {
                "username": user.username,
                "password": PASSWORD,
                "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_employee_denied(self):
        self.login(roles.ROLE_EMPLOYEE)
        response = self.client.get("/cms/", follow=True)
        self.assertTemplateUsed(response, "wagtailadmin/login.html")
        self.assertEqual(len(response.redirect_chain), 1)

    def test_three_roles_enter_cms_via_group_only(self):
        for code in (roles.ROLE_EDITOR, roles.ROLE_REVIEWER, roles.ROLE_KNOWLEDGE_ADMIN):
            with self.subTest(role=code):
                self.login(code)
                self.assertEqual(self.client.get("/cms/").status_code, 200)
                self.assertEqual(self.client.get("/cms/account/").status_code, 200)

    def test_editor_reviewer_remain_nonstaff_and_admin_denied(self):
        for code in (roles.ROLE_EDITOR, roles.ROLE_REVIEWER):
            with self.subTest(role=code):
                self.login(code)
                self.assertFalse(User.objects.get(pk=self.users[code].pk).is_staff)
                response = self.client.get(reverse("admin:accounts_user_changelist"), follow=True)
                self.assertTemplateUsed(response, "admin/login.html")

    def test_role_membership_cannot_bypass_changed_account_status(self):
        for code in (roles.ROLE_EDITOR, roles.ROLE_REVIEWER, roles.ROLE_KNOWLEDGE_ADMIN):
            for fields in (
                {"is_active": False},
                {"account_status": "disabled"},
                {"account_status": "departed"},
            ):
                with self.subTest(role=code, fields=fields):
                    user = self.users[code]
                    User.objects.filter(pk=user.pk).update(is_active=True, account_status="active")
                    self.login(code)
                    self.assertEqual(self.client.get("/cms/").status_code, 200)
                    User.objects.filter(pk=user.pk).update(**fields)
                    for url in ("/cms/", "/cms/account/"):
                        response = self.client.get(url, follow=True)
                        self.assertTemplateUsed(response, "wagtailadmin/login.html")
                        self.assertFalse(response.wsgi_request.user.is_authenticated)
                    self.assertEqual(user.groups.get().name, roles.SYSTEM_ROLE_BY_CODE[code].name)

    def test_switch_to_default_revokes_cms_entry_for_existing_sessions(self):
        clients = []
        for code in (roles.ROLE_EDITOR, roles.ROLE_REVIEWER, roles.ROLE_KNOWLEDGE_ADMIN):
            self.login(code)
            clients.append(self.client)
        sync()
        for client in clients:
            self.assertTemplateUsed(client.get("/cms/", follow=True), "wagtailadmin/login.html")

    def test_admin_existing_read_only_permissions_preserved(self):
        self.login(roles.ROLE_KNOWLEDGE_ADMIN)
        for namespace in ("wagtailusers_users", "wagtailusers_groups"):
            self.assertEqual(self.client.get(reverse(namespace + ":index")).status_code, 200)
        for url in (
            reverse("admin:accounts_user_changelist"),
            reverse("admin:auth_group_changelist"),
            reverse("admin:accounts_user_change", args=[self.target.pk]),
            reverse("admin:auth_group_change", args=[self.target_group.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_editor_reviewer_cannot_list_users_or_groups(self):
        for code in (roles.ROLE_EDITOR, roles.ROLE_REVIEWER):
            self.login(code)
            for namespace in ("wagtailusers_users", "wagtailusers_groups"):
                self.assertRedirects(
                    self.client.get(reverse(namespace + ":index")),
                    "/cms/",
                    fetch_redirect_response=False,
                )

    def test_all_three_roles_cannot_write_users_groups_or_permissions(self):
        dangerous = Permission.objects.get(content_type__app_label="auth", codename="change_group")
        routes = [
            ("wagtailusers_users:add", [], {"username": "f03b_unwanted"}),
            (
                "wagtailusers_users:edit",
                [self.target.pk],
                {
                    "username": "f03b_escalated",
                    "is_superuser": "on",
                    "user_permissions": dangerous.pk,
                },
            ),
            ("wagtailusers_groups:add", [], {"name": "f03b_unwanted"}),
            (
                "wagtailusers_groups:edit",
                [self.target_group.pk],
                {"name": "f03b_escalated", "permissions": dangerous.pk},
            ),
        ]
        for code in (roles.ROLE_EDITOR, roles.ROLE_REVIEWER, roles.ROLE_KNOWLEDGE_ADMIN):
            self.login(code)
            before = snapshot()
            for route, args, data in routes:
                with self.subTest(role=code, route=route):
                    url = reverse(route, args=args)
                    self.assertRedirects(
                        self.client.get(url), "/cms/", fetch_redirect_response=False
                    )
                    response = self.client.post(
                        url, {**data, "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value}
                    )
                    self.assertRedirects(response, "/cms/", fetch_redirect_response=False)
                    self.assertEqual(snapshot(), before)
            # 管理员有 view 权限，Django Admin 只读 GET 可用，但 POST 仍必须拒绝。
            if code == roles.ROLE_KNOWLEDGE_ADMIN:
                for url in (
                    reverse("admin:accounts_user_change", args=[self.target.pk]),
                    reverse("admin:auth_group_change", args=[self.target_group.pk]),
                ):
                    response = self.client.post(
                        url,
                        {
                            "name": "f03b_escalated",
                            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
                        },
                    )
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(snapshot(), before)
