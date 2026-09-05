"""本地模拟登录视图、开关保护与安全边界测试。"""

import importlib
import importlib.util
import os
from unittest import mock

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group as SystemGroup
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.forms import DevLoginForm
from apps.accounts.roles import DEV_IDENTITIES, ROLE_EDITOR, SYSTEM_ROLE_BY_CODE
from apps.knowledge.admin import ArticleAdmin
from apps.knowledge.models import Article

User = get_user_model()


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class DevLoginEnabledTests(TestCase):
    """开关开启时的模拟登录：白名单、CSRF、Session、切换与登出。"""

    @classmethod
    def setUpTestData(cls):
        call_command("create_dev_users")

    def setUp(self):
        self.client = Client()
        self.login_url = reverse("accounts:dev-login")
        self.logout_url = reverse("accounts:dev-logout")

    def test_get_renders_form(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "选择本地开发身份")
        self.assertIn("no-cache", response["Cache-Control"].lower())

    def test_form_only_offers_fixed_identities(self):
        form = DevLoginForm()
        self.assertEqual(
            [choice[0] for choice in form.fields["username"].choices],
            [identity.username for identity in DEV_IDENTITIES],
        )

    def test_get_does_not_change_login_state(self):
        self.client.get(self.login_url)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_post_logs_in_selected_user(self):
        user = User.objects.get(username="dev_reviewer")
        response = self.client.post(self.login_url, {"username": "dev_reviewer"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_switch_across_all_four_identities(self):
        for identity in DEV_IDENTITIES:
            user = User.objects.get(username=identity.username)
            response = self.client.post(self.login_url, {"username": identity.username})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_login_sets_correct_role(self):
        self.client.post(self.login_url, {"username": "dev_editor"})
        user = User.objects.get(username="dev_editor")
        group = SystemGroup.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        self.assertEqual(list(user.groups.all()), [group])

    def test_session_key_rotated_on_login(self):
        session = self.client.session
        session["probe"] = "x"
        session.save()
        old_key = session.session_key
        self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertIsNotNone(self.client.session.session_key)
        self.assertNotEqual(self.client.session.session_key, old_key)

    def test_arbitrary_username_rejected(self):
        User.objects.create_user(username="real_user", password="real-pass")
        response = self.client.post(self.login_url, {"username": "real_user"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_tampered_username_rejected(self):
        response = self.client.post(self.login_url, {"username": "dev_employee_evil"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_real_user_cannot_be_simulated(self):
        User.objects.create_user(username="real_worker", password="real-pass", employee_no="E-9")
        response = self.client.post(self.login_url, {"username": "real_worker"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_dev_user_with_real_identity_not_accepted(self):
        user = User.objects.get(username="dev_editor")
        user.set_password("real-pass")
        user.save()
        response = self.client.post(self.login_url, {"username": "dev_editor"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_disabled_account_refused(self):
        user = User.objects.get(username="dev_employee")
        user.account_status = "disabled"
        user.save()
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_departed_account_refused(self):
        user = User.objects.get(username="dev_employee")
        user.account_status = "departed"
        user.save()
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_refused(self):
        user = User.objects.get(username="dev_employee")
        user.is_active = False
        user.save()
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_group_refused(self):
        user = User.objects.get(username="dev_employee")
        user.groups.set([SystemGroup.objects.get(name="知识编辑员")])
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_extra_group_refused(self):
        user = User.objects.get(username="dev_employee")
        user.groups.add(SystemGroup.objects.create(name="多余组"))
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_direct_permission_refused(self):
        user = User.objects.get(username="dev_employee")
        perm = Permission.objects.get(content_type__app_label="knowledge", codename="view_article")
        user.user_permissions.add(perm)
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_staff_drift_refused(self):
        user = User.objects.get(username="dev_employee")
        user.is_staff = True
        user.save()
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_employee_no_refused(self):
        user = User.objects.get(username="dev_employee")
        user.employee_no = "E-1"
        user.save()
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_dingtalk_identity_refused(self):
        user = User.objects.get(username="dev_employee")
        user.dingtalk_user_id = "ding-fake-001"
        user.save()
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_display_name_drift_refused(self):
        user = User.objects.get(username="dev_employee")
        user.display_name = "被篡改的显示名称"
        user.save()
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_missing_dev_user_shows_safe_hint(self):
        User.objects.filter(username="dev_employee").delete()
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "create_dev_users")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_csrf_required(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(self.login_url, {"username": "dev_editor"})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", csrf_client.session)

    def test_unsafe_next_ignored(self):
        response = self.client.post(
            self.login_url,
            {"username": "dev_employee", "next": "http://evil.example.com/steal"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.login_url)

    def test_safe_next_followed(self):
        response = self.client.post(
            self.login_url, {"username": "dev_employee", "next": "/health/live"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/health/live")

    def test_page_shows_current_identity_and_role(self):
        self.client.post(self.login_url, {"username": "dev_reviewer"})
        response = self.client.get(self.login_url)
        self.assertContains(response, "dev_reviewer")
        self.assertContains(response, "本地模拟-知识审核员")
        self.assertContains(response, "知识审核员")

    def test_page_does_not_leak_other_users_or_secrets(self):
        User.objects.create_user(
            username="real_employee",
            password="real-pass",
            display_name="真实员工",
            dingtalk_user_id="ding-001",
        )
        self.client.post(self.login_url, {"username": "dev_employee"})
        response = self.client.get(self.login_url)
        self.assertNotContains(response, "real_employee")
        self.assertNotContains(response, "真实员工")
        self.assertNotContains(response, "ding-001")
        self.assertNotContains(response, "real-pass")

    def test_logout_post_clears_session(self):
        self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertIn("_auth_user_id", self.client.session)
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_get_405(self):
        response = self.client.get(self.logout_url)
        self.assertEqual(response.status_code, 405)

    def test_article_admin_add_still_disabled(self):
        user = User.objects.get(username="dev_knowledge_admin")
        request = RequestFactory().get("/admin/knowledge/article/add/")
        request.user = user
        model_admin = ArticleAdmin(Article, admin.site)
        self.assertFalse(model_admin.has_add_permission(request))
        self.client.force_login(user)
        response = self.client.get("/admin/knowledge/article/add/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Article.objects.count(), 0)

    def test_step8_audience_selector_not_implemented(self):
        self.assertIsNone(importlib.util.find_spec("apps.knowledge.selectors"))


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=False)
class DevLoginSwitchOffTests(TestCase):
    """开关关闭时所有模拟登录入口均返回 404。"""

    def setUp(self):
        self.client = Client()
        self.login_url = reverse("accounts:dev-login")
        self.logout_url = reverse("accounts:dev-logout")

    def test_login_get_404_when_switch_off(self):
        self.assertEqual(self.client.get(self.login_url).status_code, 404)

    def test_login_post_404_when_switch_off(self):
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 404)

    def test_logout_post_404_when_switch_off(self):
        self.assertEqual(self.client.post(self.logout_url).status_code, 404)


@override_settings(DEBUG=False, DEV_LOGIN_ENABLED=True)
class DevLoginDebugFalseTests(TestCase):
    """DEBUG=False 时即使开关开启，模拟登录入口也必须返回 404。"""

    def setUp(self):
        self.client = Client()
        self.login_url = reverse("accounts:dev-login")
        self.logout_url = reverse("accounts:dev-logout")

    def test_login_get_404_when_debug_false(self):
        self.assertEqual(self.client.get(self.login_url).status_code, 404)

    def test_login_post_404_when_debug_false(self):
        response = self.client.post(self.login_url, {"username": "dev_employee"})
        self.assertEqual(response.status_code, 404)

    def test_logout_post_404_when_debug_false(self):
        self.assertEqual(self.client.post(self.logout_url).status_code, 404)


class DevLoginSettingsModuleTests(SimpleTestCase):
    """各设置模块中 DEV_LOGIN_ENABLED 的默认值与生产硬关闭保护。"""

    _REQUIRED_ENV = {
        "DJANGO_SECRET_KEY": "test-secret",
        "DJANGO_ALLOWED_HOSTS": "example.com",
        "POSTGRES_DB": "db",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "password",
        "POSTGRES_HOST": "host",
        "POSTGRES_PORT": "5432",
    }

    def test_base_and_test_default_false(self):
        base = importlib.import_module("config.settings.base")
        self.assertIs(base.DEV_LOGIN_ENABLED, False)
        test_settings = importlib.import_module("config.settings.test")
        self.assertIs(test_settings.DEV_LOGIN_ENABLED, False)

    def test_development_reads_env_switch(self):
        dev = importlib.import_module("config.settings.development")
        with mock.patch.dict(os.environ, self._REQUIRED_ENV | {"DJANGO_DEV_LOGIN_ENABLED": "true"}):
            importlib.reload(dev)
            self.assertIs(dev.DEV_LOGIN_ENABLED, True)
        with mock.patch.dict(
            os.environ, self._REQUIRED_ENV | {"DJANGO_DEV_LOGIN_ENABLED": "false"}
        ):
            importlib.reload(dev)
            self.assertIs(dev.DEV_LOGIN_ENABLED, False)

    def test_development_defaults_off_when_unset(self):
        # 修复后：未设置环境变量时开发环境默认关闭模拟登录，
        # 必须显式开启（安全默认值，禁止为方便而默认开启）。
        dev = importlib.import_module("config.settings.development")
        with mock.patch.dict(os.environ, self._REQUIRED_ENV, clear=True):
            importlib.reload(dev)
            self.assertIs(dev.DEV_LOGIN_ENABLED, False)

    def test_development_strict_false_values(self):
        # 仅识别 1/true/yes/on（不区分大小写）；其余值一律视为关闭。
        dev = importlib.import_module("config.settings.development")
        for value in ("false", "0", "", "garbage", " False "):
            with mock.patch.dict(
                os.environ, self._REQUIRED_ENV | {"DJANGO_DEV_LOGIN_ENABLED": value}
            ):
                importlib.reload(dev)
                self.assertIs(dev.DEV_LOGIN_ENABLED, False, f"值 {value!r} 必须解析为关闭")

    def test_production_hard_disabled_even_with_env(self):
        prod = importlib.import_module("config.settings.production")
        with mock.patch.dict(os.environ, self._REQUIRED_ENV | {"DJANGO_DEV_LOGIN_ENABLED": "true"}):
            importlib.reload(prod)
            self.assertIs(prod.DEV_LOGIN_ENABLED, False)
