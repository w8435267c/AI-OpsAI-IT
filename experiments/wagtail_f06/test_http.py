"""真实会话请求；只复用详情测试夹具，不继承或重复收集其测试。"""

from unittest.mock import patch
from uuid import uuid4

from django.contrib.sessions.models import Session
from django.db import connection
from django.middleware.csrf import get_token
from django.test import Client, RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import Resolver404, resolve, reverse

from apps.accounts.models import User
from apps.knowledge.models import Article, ArticleAudience
from apps.knowledge.tests.test_selectors import _add_audience, _mk_article, _mk_user
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.tests import legacy_snapshot
from experiments.wagtail_f05a.models import TaskSubmission
from experiments.wagtail_f05a.services import submit
from experiments.wagtail_f05a.tests import snapshot
from experiments.wagtail_f05b.services import approve_review

from . import test_readers as fixtures


class DetailHTTPTests(TestCase):
    def setUp(self):
        fixtures.DetailTests.setUp(self)
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse("f06_article_detail", args=[self.article.pk])
        self.login(self.employee)

    def login(self, user):
        user.set_password("synthetic-f06-http")
        user.save(update_fields=["password"])
        self.assertTrue(self.client.login(username=user.username, password="synthetic-f06-http"))

    def request(self, method="get", url=None, **kwargs):
        before = (snapshot(), legacy_snapshot(), list(Session.objects.order_by("pk").values()))
        with CaptureQueriesContext(connection) as queries:
            response = getattr(self.client, method)(url or self.url, **kwargs)
        self.assertEqual(
            (snapshot(), legacy_snapshot(), list(Session.objects.order_by("pk").values())), before
        )
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries))
        self.assertEqual(response["Cache-Control"], "private, no-store")
        return response

    def test_employee_without_admin_rights_gets_whitelisted_json(self):
        self.assertFalse(self.employee.is_staff)
        self.assertFalse(self.employee.has_perm("wagtailadmin.access_admin"))
        response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(
            response.json(),
            {
                "article_id": str(self.article.pk),
                "content_id": self.content.pk,
                "revision_id": self.revision.pk,
                "title": "正式标题",
                "summary": "正式摘要",
                "body": "正式正文",
            },
        )

    def test_anonymous_fixed_401_without_reader_or_content_queries(self):
        self.client.logout()
        with patch("experiments.wagtail_f06.views.get_employee_article_detail") as reader:
            with self.assertNumQueries(0):
                response = self.client.get(self.url)
            other = self.request(url=reverse("f06_article_detail", args=[uuid4()]))
            reader.assert_not_called()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.content, other.content)
        self.assertEqual(response.json(), {"error": "authentication_required"})
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_denied_missing_unpublished_and_evidence_missing_share_404(self):
        missing = self.request(url=reverse("f06_article_detail", args=[uuid4()]))
        Article.objects.filter(pk=self.article.pk).update(audience_policy="restricted")
        denied = self.request()
        Article.objects.filter(pk=self.article.pk).update(audience_policy="all_employees")
        TaskSubmission.objects.filter(pk=self.approved.pk).delete()
        no_evidence = self.request()
        other = _mk_article(policy="all_employees")
        KnowledgeContent.objects.create(article=other, title="未发布标题", body="不应泄露")
        unpublished = self.request(url=reverse("f06_article_detail", args=[other.pk]))
        for response in (missing, denied, no_evidence, unpublished):
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.content, missing.content)
            self.assertEqual(response.json(), {"error": "not_found"})

    def test_published_v2_and_draft_v3_return_only_v2_json_text(self):
        obj = KnowledgeContent.objects.get(pk=self.content.pk)
        obj.title, obj.summary, obj.body = "V2 标题", "V2 摘要", '<script>"文本"</script>\n正文'
        revision = obj.save_revision(user=self.creator)
        state = submit(obj.pk, revision.pk, self.submitter)
        approve_review(state.current_task_state_id, self.reviewer)
        fixtures.DetailTests.draft(self)
        response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "V2 标题")
        self.assertEqual(response.json()["summary"], "V2 摘要")
        self.assertEqual(response.json()["body"], '<script>"文本"</script>\n正文')
        self.assertEqual(response.json()["revision_id"], revision.pk)
        self.assertNotIn("秘密草稿", response.content.decode())
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_session_account_disabled_or_departed_is_401(self):
        for fields in (
            {"is_active": False},
            {"account_status": "disabled"},
            {"account_status": "departed"},
        ):
            with self.subTest(fields=fields):
                self.assertEqual(self.request().status_code, 200)
                User.objects.filter(pk=self.employee.pk).update(**fields)
                with patch("experiments.wagtail_f06.views.get_employee_article_detail") as reader:
                    response = self.request()
                    reader.assert_not_called()
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json(), {"error": "authentication_required"})
                User.objects.filter(pk=self.employee.pk).update(
                    is_active=True, account_status="active"
                )

    def test_audience_revocation_and_offline_apply_next_request(self):
        Article.objects.filter(pk=self.article.pk).update(audience_policy="restricted")
        rule = _add_audience(self.article, "user", user=self.employee)
        self.assertEqual(self.request().status_code, 200)
        ArticleAudience.objects.filter(pk=rule.pk).delete()
        self.assertEqual(self.request().status_code, 404)
        Article.objects.filter(pk=self.article.pk).update(audience_policy="all_employees")
        self.assertEqual(self.request().status_code, 200)
        Article.objects.filter(pk=self.article.pk).update(article_status="offline")
        self.assertEqual(self.request().status_code, 404)

    def test_superuser_has_no_employee_audience_bypass(self):
        self.login(_mk_user(is_staff=True, is_superuser=True))
        Article.objects.filter(pk=self.article.pk).update(audience_policy="restricted")
        self.assertEqual(self.request().json(), {"error": "not_found"})
        self.assertEqual(self.request().status_code, 404)

    def test_invalid_uuid_and_non_get_are_read_only(self):
        response = self.request(url="/experiments/f06/articles/not-a-uuid/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "not_found"})
        # 实际 CSRF 中间件仍有效；无令牌先返回 403，同样禁止缓存和写入。
        self.assertEqual(self.request("post").status_code, 403)
        request = RequestFactory().get("/")
        token = get_token(request)
        self.client.cookies["csrftoken"] = request.META["CSRF_COOKIE"]
        for method in ("post", "put", "patch", "delete", "options", "head"):
            with self.subTest(method=method):
                response = self.request(method, HTTP_X_CSRFTOKEN=token)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "GET")

    def test_route_only_registered_in_f06_configuration(self):
        self.assertEqual(resolve(self.url).url_name, "f06_article_detail")
        with override_settings(ROOT_URLCONF="experiments.wagtail_f05a.urls"):
            with self.assertRaises(Resolver404):
                resolve(self.url)
