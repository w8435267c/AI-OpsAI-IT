"""钉钉 H5 离线 SSO HTTP 边界测试；不含任何真实 API 或凭据。"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.dingtalk.providers import (
    DingTalkIdentityProviderError,
    UnavailableDingTalkIdentityProvider,
    VerifiedDingTalkIdentity,
    get_identity_provider,
)
from apps.knowledge.models import AudiencePolicy
from apps.knowledge.tests.test_selectors import _mk_article, _publish

User = get_user_model()


class FakeVerifiedIdentityProvider:
    """只在测试注入，不由设置或 HTTP 参数启用。"""

    def __init__(self, identity, *, expected_code="test-code"):
        self.identity = identity
        self.expected_code = expected_code
        self.calls = []

    def verify_authorization_code(self, authorization_code):
        self.calls.append(authorization_code)
        if authorization_code != self.expected_code:
            raise DingTalkIdentityProviderError("identity verification failed")
        return self.identity


class DingTalkSsoViewTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.user = User.objects.create_user(
            username="sso-employee",
            dingtalk_corp_id="corp-001",
            dingtalk_user_id="user-001",
        )
        self.start_url = reverse("dingtalk:sso-start")
        self.complete_url = reverse("dingtalk:sso-complete")

    def _start(self, next_url="/"):
        response = self.client.get(self.start_url, {"next": next_url})
        self.assertEqual(response.status_code, 200)
        return response.json()["state"]

    def _complete(self, provider, *, state=None, code="test-code"):
        return self.client.post(
            self.complete_url,
            {"state": state or self._start(), "code": code},
        )

    def test_explicitly_injected_verified_identity_logs_in_existing_employee(self):
        session = self.client.session
        session["session_fixation_probe"] = "before-login"
        session.save()
        old_session_key = session.session_key
        provider = FakeVerifiedIdentityProvider(
            VerifiedDingTalkIdentity(corp_id="corp-001", user_id="user-001")
        )
        with patch("apps.dingtalk.views.get_identity_provider", return_value=provider):
            response = self._complete(provider, state=self._start("/search/?q=network"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/search/?q=network")
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
        self.assertEqual(provider.calls, ["test-code"])
        self.assertEqual(list(self.user.groups.all()), [])
        self.assertNotEqual(self.client.session.session_key, old_session_key)

    def test_state_and_code_are_one_time_and_expiry_fail_closed(self):
        provider = FakeVerifiedIdentityProvider(
            VerifiedDingTalkIdentity(corp_id="corp-001", user_id="user-001")
        )
        state = self._start()
        with patch("apps.dingtalk.views.get_identity_provider", return_value=provider):
            self.assertEqual(self._complete(provider, state=state).status_code, 302)
            self.assertEqual(self._complete(provider, state=state).status_code, 403)
        self.assertEqual(provider.calls, ["test-code"])

        state = self._start()
        session = self.client.session
        flow = session["dingtalk_sso_flow"]
        flow["issued_at"] = 0
        session["dingtalk_sso_flow"] = flow
        session.save()
        with patch("apps.dingtalk.views.get_identity_provider", return_value=provider):
            self.assertEqual(self._complete(provider, state=state).status_code, 403)

    def test_forged_identity_parameters_and_external_redirect_never_log_in(self):
        response = self.client.post(
            self.complete_url,
            {
                "state": "forged",
                "code": "anything",
                "corpId": "corp-001",
                "userId": "user-001",
                "next": "https://evil.example/steal",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)

        provider = FakeVerifiedIdentityProvider(
            VerifiedDingTalkIdentity(corp_id="corp-001", user_id="user-001")
        )
        with patch("apps.dingtalk.views.get_identity_provider", return_value=provider):
            response = self._complete(provider, state=self._start("https://evil.example/steal"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_unverified_or_unknown_identity_never_creates_a_session_or_account(self):
        provider = FakeVerifiedIdentityProvider(
            VerifiedDingTalkIdentity(corp_id="corp-001", user_id="missing")
        )
        before = User.objects.count()
        with patch("apps.dingtalk.views.get_identity_provider", return_value=provider):
            response = self._complete(provider, state=self._start())
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(User.objects.count(), before)

    def test_unverified_code_never_creates_a_session(self):
        provider = FakeVerifiedIdentityProvider(
            VerifiedDingTalkIdentity(corp_id="corp-001", user_id="user-001")
        )
        with patch("apps.dingtalk.views.get_identity_provider", return_value=provider):
            response = self._complete(provider, state=self._start(), code="invalid-code")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_completion_requires_csrf_protection(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.get(self.start_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", csrf_client.cookies)
        response = csrf_client.post(
            self.complete_url,
            {"state": response.json()["state"], "code": "test-code"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", csrf_client.session)

    def test_unconfigured_provider_fails_closed_in_production_style_settings(self):
        with override_settings(DEBUG=False):
            self.assertIsInstance(get_identity_provider(), UnavailableDingTalkIdentityProvider)
        response = self._complete(UnavailableDingTalkIdentityProvider())
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_existing_dev_login_contract_remains_separate(self):
        self.assertEqual(self.client.get(reverse("accounts:dev-login")).status_code, 404)

    def test_anonymous_employee_page_is_rejected_and_sso_preserves_existing_audience_checks(self):
        home_url = reverse("knowledge:home")
        self.assertEqual(self.client.get(home_url).status_code, 401)

        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        provider = FakeVerifiedIdentityProvider(
            VerifiedDingTalkIdentity(corp_id="corp-001", user_id="user-001")
        )
        with patch("apps.dingtalk.views.get_identity_provider", return_value=provider):
            self.assertEqual(self._complete(provider, state=self._start()).status_code, 302)
        self.assertEqual(self.client.get(home_url).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("knowledge:article_detail", args=[article.kb_no])).status_code,
            200,
        )

        # 没有已发布版本的文章不能因 SSO 登录而可见。
        draft = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        self.assertEqual(
            self.client.get(reverse("knowledge:article_detail", args=[draft.kb_no])).status_code,
            404,
        )
