"""正式员工用户名密码登录的安全边界测试。"""

import importlib
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import AccountStatus
from apps.dingtalk.authentication import map_verified_identity
from apps.dingtalk.providers import VerifiedDingTalkIdentity
from apps.knowledge.models import AudiencePolicy
from apps.knowledge.tests.test_selectors import _mk_article, _publish

User = get_user_model()


@override_settings(LOCAL_LOGIN_MAX_FAILURES=2, LOCAL_LOGIN_THROTTLE_SECONDS=60)
class EmployeeLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.login_url = reverse("employee-login")
        self.logout_url = reverse("employee-logout")
        self.user = User.objects.create_user(
            username="pilot_employee",
            password="safe-test-password",
            employee_no="PILOT-001",
        )

    def tearDown(self):
        cache.clear()

    def _login(self, **data):
        payload = {"username": "pilot_employee", "password": "safe-test-password"}
        payload.update(data)
        return self.client.post(self.login_url, payload)

    def test_valid_password_creates_session_and_rotates_session_key(self):
        self.assertNotEqual(self.user.password, "safe-test-password")
        self.assertTrue(self.user.check_password("safe-test-password"))

        session = self.client.session
        session["pre_login_probe"] = "present"
        session.save()
        old_key = session.session_key

        response = self._login(next="/health/live")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/health/live")
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
        self.assertNotEqual(self.client.session.session_key, old_key)

    def test_public_registration_is_not_available(self):
        self.assertEqual(self.client.get("/accounts/register/").status_code, 404)

    def test_invalid_password_is_rejected_without_session(self):
        response = self._login(password="wrong-password")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotContains(response, "safe-test-password")

    def test_disabled_departed_and_inactive_accounts_are_rejected(self):
        for changes in (
            {"account_status": AccountStatus.DISABLED},
            {"account_status": AccountStatus.DEPARTED},
            {"is_active": False},
        ):
            with self.subTest(changes=changes):
                cache.clear()
                User.objects.filter(pk=self.user.pk).update(**changes)
                response = self._login()
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("_auth_user_id", self.client.session)
                User.objects.filter(pk=self.user.pk).update(
                    account_status=AccountStatus.ACTIVE,
                    is_active=True,
                )

    def test_logout_is_post_only_and_clears_session(self):
        self._login()
        self.assertIn("_auth_user_id", self.client.session)

        self.assertEqual(self.client.get(self.logout_url).status_code, 405)
        response = self.client.post(self.logout_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.login_url)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_control_is_only_visible_to_authenticated_employee(self):
        anonymous_response = self.client.get(self.login_url)
        self.assertNotContains(anonymous_response, "退出登录")

        self._login()
        authenticated_response = self.client.get(reverse("knowledge:home"))

        self.assertContains(authenticated_response, "退出登录")
        self.assertContains(authenticated_response, 'method="post"', html=False)
        self.assertContains(authenticated_response, f'action="{self.logout_url}"', html=False)
        self.assertContains(authenticated_response, "csrfmiddlewaretoken")

    def test_csrf_is_required(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(
            self.login_url,
            {"username": "pilot_employee", "password": "safe-test-password"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", csrf_client.session)

    def test_external_next_is_ignored(self):
        response = self._login(next="https://evil.example/steal")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("knowledge:home"))

    def test_failed_login_is_rate_limited_without_exposing_account_state(self):
        self.assertEqual(self._login(password="wrong-one").status_code, 200)
        self.assertEqual(self._login(password="wrong-two").status_code, 200)

        response = self._login()

        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logged_in_employee_retains_existing_audience_filtering(self):
        allowed_article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        restricted_article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        self._login()

        self.assertEqual(self.client.get(reverse("knowledge:home")).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("knowledge:article_detail", args=[allowed_article.kb_no])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("knowledge:article_detail", args=[restricted_article.kb_no])
            ).status_code,
            404,
        )

    def test_employee_login_does_not_grant_admin_access(self):
        self._login()

        response = self.client.get("/admin/")

        self.assertIn(response.status_code, (302, 403))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_dingtalk_identity_mapping_still_uses_existing_employee(self):
        self.user.dingtalk_corp_id = "corp-pilot"
        self.user.dingtalk_user_id = "ding-pilot"
        self.user.save(update_fields=["dingtalk_corp_id", "dingtalk_user_id"])

        mapped = map_verified_identity(
            VerifiedDingTalkIdentity(corp_id="corp-pilot", user_id="ding-pilot")
        )

        self.assertEqual(mapped.pk, self.user.pk)


class ProductionLoginSettingsTests(TestCase):
    _REQUIRED_ENV = {
        "DJANGO_SECRET_KEY": "test-secret",
        "DJANGO_ALLOWED_HOSTS": "example.com",
        "POSTGRES_DB": "db",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "password",
        "POSTGRES_HOST": "host",
        "POSTGRES_PORT": "5432",
    }

    def test_production_keeps_dev_login_disabled_and_secure_session_cookies(self):
        production = importlib.import_module("config.settings.production")
        with mock.patch.dict(os.environ, self._REQUIRED_ENV | {"DJANGO_DEV_LOGIN_ENABLED": "true"}):
            importlib.reload(production)

        self.assertFalse(production.DEV_LOGIN_ENABLED)
        self.assertTrue(production.SESSION_COOKIE_SECURE)
        self.assertTrue(production.CSRF_COOKIE_SECURE)
