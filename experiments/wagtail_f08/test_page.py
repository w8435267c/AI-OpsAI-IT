"""F08D-1 员工普通文本详情页：正式快照、统一拒绝、缓存与自动转义。"""

from unittest.mock import patch
from uuid import uuid4

from django.test import Client, TestCase, override_settings
from django.urls import Resolver404, resolve, reverse
from django.utils.html import escape

from apps.accounts.models import User
from apps.knowledge.models import Article
from apps.knowledge.tests.test_selectors import _mk_article
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f05a.services import submit
from experiments.wagtail_f05b.services import approve_review
from experiments.wagtail_f06 import test_readers as fixtures
from experiments.wagtail_f06.readers import get_employee_article_detail


class PlaintextArticlePageTests(TestCase):
    def setUp(self):
        fixtures.DetailTests.setUp(self)
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse("f08_article_detail", args=[self.article.pk])
        self.login(self.employee)

    def login(self, user):
        user.set_password("synthetic-f08-page")
        user.save(update_fields=["password"])
        self.assertTrue(self.client.login(username=user.username, password="synthetic-f08-page"))

    def assert_private(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        return response

    def test_approved_plaintext_and_later_draft_render_live_snapshot_escaped(self):
        title = '正式 <b>标题</b> {"kind": "text"}'
        summary = '摘要 <img src=x onerror="alert(1)">'
        body = '第一行\n  第二行 <script>alert("x")</script>\n{"looks": "json"}'
        content = KnowledgeContent.objects.get(pk=self.content.pk)
        content.title, content.summary, content.body = title, summary, body
        revision = content.save_revision(user=self.creator)
        state = submit(content.pk, revision.pk, self.submitter)
        approve_review(state.current_task_state_id, self.reviewer)

        with patch(
            "experiments.wagtail_f08.views.get_employee_article_detail",
            wraps=get_employee_article_detail,
        ) as reader:
            response = self.assert_private(self.client.get(self.url), 200)
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(reader.call_args.args[0].pk, self.employee.pk)
        self.assertEqual(reader.call_args.args[1], str(self.article.pk))
        self.assertFalse(self.employee.is_staff)
        self.assertFalse(self.employee.has_perm("wagtailadmin.access_admin"))
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        html = response.content.decode()
        self.assertIn(escape(title), html)
        self.assertIn(escape(summary), html)
        self.assertIn(f'<div class="article-body">{escape(body)}</div>', html)
        self.assertIn("white-space: pre-wrap", html)
        self.assertNotIn("<b>标题</b>", html)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)

        content.refresh_from_db()
        content.title = "秘密草稿标题"
        content.summary = "秘密草稿摘要"
        content.body = "秘密草稿正文"
        draft = content.save_revision(user=self.creator)
        self.assertNotEqual(draft.pk, revision.pk)
        response = self.assert_private(self.client.get(self.url), 200)
        html = response.content.decode()
        self.assertIn(escape(title), html)
        self.assertIn(escape(summary), html)
        self.assertIn(escape(body), html)
        self.assertNotIn("秘密草稿", html)

    def test_denied_missing_and_unpublished_share_404_without_leak(self):
        missing = self.assert_private(
            self.client.get(reverse("f08_article_detail", args=[uuid4()])), 404
        )
        Article.objects.filter(pk=self.article.pk).update(audience_policy="restricted")
        denied = self.assert_private(self.client.get(self.url), 404)
        Article.objects.filter(pk=self.article.pk).update(audience_policy="all_employees")

        unpublished_article = _mk_article(policy="all_employees")
        KnowledgeContent.objects.create(
            article=unpublished_article,
            title="不可泄露标题",
            summary="不可泄露摘要",
            body="不可泄露正文<script>",
        )
        unpublished = self.assert_private(
            self.client.get(reverse("f08_article_detail", args=[unpublished_article.pk])), 404
        )
        for response in (missing, denied, unpublished):
            self.assertEqual(response.content, missing.content)
            text = response.content.decode()
            self.assertEqual(text, "未找到。")
            self.assertNotIn("正式", text)
            self.assertNotIn("不可泄露", text)

    def test_anonymous_and_invalid_session_accounts_share_401(self):
        self.client.logout()
        with patch("experiments.wagtail_f08.views.get_employee_article_detail") as reader:
            anonymous = self.assert_private(self.client.get(self.url), 401)
            reader.assert_not_called()
        self.assertEqual(anonymous.content.decode(), "需要登录。")

        for fields in (
            {"is_active": False},
            {"account_status": "disabled"},
            {"account_status": "departed"},
        ):
            with self.subTest(fields=fields):
                User.objects.filter(pk=self.employee.pk).update(
                    is_active=True, account_status="active"
                )
                self.client = Client(enforce_csrf_checks=True)
                self.login(self.employee)
                User.objects.filter(pk=self.employee.pk).update(**fields)
                with patch("experiments.wagtail_f08.views.get_employee_article_detail") as reader:
                    response = self.assert_private(self.client.get(self.url), 401)
                    reader.assert_not_called()
                self.assertEqual(response.content, anonymous.content)

    def test_non_get_methods_are_405_and_private_without_csrf_exception(self):
        for method in ("post", "put", "patch", "delete", "options", "head"):
            with self.subTest(method=method):
                response = self.assert_private(getattr(self.client, method)(self.url), 405)
                self.assertEqual(response["Allow"], "GET")

    def test_route_is_f08_only_and_f06_json_behavior_is_preserved(self):
        self.assertEqual(resolve(self.url).url_name, "f08_article_detail")
        with override_settings(ROOT_URLCONF="experiments.wagtail_f06.urls"):
            with self.assertRaises(Resolver404):
                resolve(self.url)

        response = self.assert_private(
            self.client.get(reverse("f06_article_detail", args=[self.article.pk])), 200
        )
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["revision_id"], self.revision.pk)
        self.assertEqual(response.json()["body"], "正式正文")
