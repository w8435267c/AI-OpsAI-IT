"""统一 IT 服务入口的访问控制和安全跳转测试。"""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.knowledge.models import AudiencePolicy
from apps.knowledge.tests.test_selectors import _mk_article, _mk_user, _publish


class ServiceDeskRequestEntryTests(TestCase):
    def setUp(self):
        self.employee = _mk_user()
        self.client = Client()
        self.client.force_login(self.employee)
        self.article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))

    def _url(self, article=None):
        article = article or self.article
        return reverse("service_desk:request_entry", args=[article.kb_no])

    @override_settings(SERVICE_DESK_REQUEST_URL="https://service.example.test/01_ServiceRequest")
    def test_visible_employee_is_redirected_only_to_controlled_configured_url(self):
        response = self.client.get(self._url())

        self.assertRedirects(
            response,
            "https://service.example.test/01_ServiceRequest",
            fetch_redirect_response=False,
        )

    def test_missing_or_invalid_config_fails_closed_with_friendly_message(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "IT 服务申请入口暂未配置", status_code=503)

        with self.settings(SERVICE_DESK_REQUEST_URL="javascript:alert(1)"):
            response = self.client.get(self._url())
        self.assertEqual(response.status_code, 503)

    @override_settings(SERVICE_DESK_REQUEST_URL="https://service.example.test/01_ServiceRequest")
    def test_anonymous_and_unreadable_article_are_rejected(self):
        anonymous = Client()
        self.assertEqual(anonymous.get(self._url()).status_code, 401)

        restricted, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        self.assertEqual(self.client.get(self._url(restricted)).status_code, 404)
