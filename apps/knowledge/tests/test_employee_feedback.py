"""员工知识解决反馈的 HTTP、权限和持久化测试。"""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.knowledge.models import ArticleStatus, AudiencePolicy, FeedbackOutcome, FeedbackRecord
from apps.knowledge.tests.test_selectors import _mk_article, _mk_user, _publish


class EmployeeFeedbackTests(TestCase):
    def setUp(self):
        self.employee = _mk_user()
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.employee)
        self.article, self.version = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))

    def _feedback_url(self, article=None):
        article = article or self.article
        return reverse("knowledge:article_feedback", args=[article.kb_no])

    def _csrf_post(self, url, data):
        self.client.get(reverse("knowledge:article_detail", args=[self.article.kb_no]))
        return self.client.post(url, data, HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)

    def test_resolved_feedback_is_persisted_for_current_published_version(self):
        response = self._csrf_post(self._feedback_url(), {"outcome": FeedbackOutcome.RESOLVED})

        self.assertRedirects(
            response,
            reverse("knowledge:article_detail", args=[self.article.kb_no]),
            fetch_redirect_response=False,
        )
        record = FeedbackRecord.objects.get()
        self.assertEqual(record.article_id, self.article.pk)
        self.assertEqual(record.article_version_id, self.version.pk)
        self.assertEqual(record.user_id, self.employee.pk)
        self.assertEqual(record.outcome, FeedbackOutcome.RESOLVED)

    def test_feedback_redirect_preserves_search_query(self):
        url = f"{self._feedback_url()}?q=%E6%89%93%E5%8D%B0%E6%9C%BA"
        response = self._csrf_post(url, {"outcome": FeedbackOutcome.RESOLVED})

        detail_url = reverse("knowledge:article_detail", args=[self.article.kb_no])
        self.assertRedirects(
            response, f"{detail_url}?q=%E6%89%93%E5%8D%B0%E6%9C%BA", fetch_redirect_response=False
        )

    def test_unresolved_feedback_is_persisted_and_duplicate_is_idempotent(self):
        first = self._csrf_post(self._feedback_url(), {"outcome": FeedbackOutcome.UNRESOLVED})
        second = self._csrf_post(self._feedback_url(), {"outcome": FeedbackOutcome.UNRESOLVED})

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(FeedbackRecord.objects.count(), 1)
        self.assertEqual(FeedbackRecord.objects.get().outcome, FeedbackOutcome.UNRESOLVED)

    def test_anonymous_request_is_rejected_without_creating_feedback(self):
        client = Client()
        response = client.post(self._feedback_url(), {"outcome": FeedbackOutcome.RESOLVED})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(FeedbackRecord.objects.count(), 0)

    def test_csrf_is_required(self):
        response = self.client.post(self._feedback_url(), {"outcome": FeedbackOutcome.RESOLVED})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(FeedbackRecord.objects.count(), 0)

    def test_unreadable_and_offline_articles_do_not_accept_feedback(self):
        restricted, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        self.client.get(reverse("knowledge:article_detail", args=[self.article.kb_no]))
        self.article.article_status = ArticleStatus.OFFLINE
        self.article.save(update_fields=["article_status"])

        offline = self._csrf_post(self._feedback_url(), {"outcome": FeedbackOutcome.RESOLVED})
        hidden = self._csrf_post(
            self._feedback_url(restricted), {"outcome": FeedbackOutcome.RESOLVED}
        )

        self.assertEqual(offline.status_code, 404)
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(FeedbackRecord.objects.count(), 0)

    def test_detail_shows_feedback_controls_and_safe_unconfigured_entry_message(self):
        response = self.client.get(reverse("knowledge:article_detail", args=[self.article.kb_no]))

        self.assertContains(response, 'name="outcome"')
        self.assertContains(response, FeedbackOutcome.RESOLVED)
        self.assertContains(response, FeedbackOutcome.UNRESOLVED)
        self.assertContains(response, "IT 服务申请入口暂未配置")

    @override_settings(SERVICE_DESK_REQUEST_URL="https://service.example.test/01_ServiceRequest")
    def test_detail_uses_internal_controlled_service_entry_route(self):
        response = self.client.get(reverse("knowledge:article_detail", args=[self.article.kb_no]))

        self.assertContains(
            response,
            reverse("service_desk:request_entry", args=[self.article.kb_no]),
            html=False,
        )
