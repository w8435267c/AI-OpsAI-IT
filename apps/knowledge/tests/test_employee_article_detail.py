"""Task 10D 正式员工知识详情页的安全读取与模板契约测试。"""

from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone
from django.utils.html import escape

from apps.accounts.models import AccountStatus
from apps.knowledge import views as knowledge_views
from apps.knowledge.models import (
    Article,
    ArticleStatus,
    ArticleVersion,
    AudienceEffect,
    AudiencePolicy,
    AudienceType,
    VersionStatus,
)
from apps.knowledge.readers import EmployeeArticleDetail, get_employee_article_detail
from apps.knowledge.tests.test_selectors import (
    _add_audience,
    _mk_article,
    _mk_category,
    _mk_space,
    _mk_user,
    _publish,
)


def _set_detail_content(
    version,
    *,
    title="正式标题",
    summary="正式摘要",
    body_text="正式正文",
    body=None,
    applicable_scope=None,
):
    fields = {
        "title": title,
        "summary": summary,
        "body_plaintext": body_text,
    }
    if body is not None:
        fields["body"] = body
    if applicable_scope is not None:
        fields["applicable_scope"] = applicable_scope
    ArticleVersion.objects.filter(pk=version.pk).update(**fields)
    version.refresh_from_db()
    return version


class EmployeeArticleDetailBase(TestCase):
    def setUp(self):
        self.user = _mk_user()
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def publish_visible(self, **article_fields):
        article, version = _publish(
            _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES, **article_fields)
        )
        _set_detail_content(version)
        return article, version

    def assert_private(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        return response


class EmployeeArticleDetailSuccessTests(EmployeeArticleDetailBase):
    def test_visible_formal_detail_uses_reader_dto_and_employee_identity(self):
        space = _mk_space(name="员工知识空间")
        category = _mk_category(space, name="网络故障", code="network-fault")
        article, version = self.publish_visible(space=space, category=category)
        published_at = timezone.now() - timedelta(hours=2)
        ArticleVersion.objects.filter(pk=version.pk).update(
            title="VPN 无法连接处理",
            summary="按步骤检查企业 VPN。",
            body_plaintext="第一步：检查网络。\n第二步：重新连接。",
            applicable_scope={"network": "内网", "systems": ["Windows 11"]},
            published_at=published_at,
        )
        url = reverse("knowledge:article_detail", args=[article.kb_no])

        with patch(
            "apps.knowledge.views.get_employee_article_detail",
            wraps=get_employee_article_detail,
        ) as reader:
            response = self.assert_private(self.client.get(url), 200)

        reader.assert_called_once()
        self.assertEqual(reader.call_args.args[0].pk, self.user.pk)
        self.assertEqual(reader.call_args.args[1], article.kb_no)
        self.assertIsInstance(response.context["detail"], EmployeeArticleDetail)
        self.assertContains(response, article.kb_no)
        self.assertContains(response, "VPN 无法连接处理")
        self.assertContains(response, "按步骤检查企业 VPN。")
        self.assertContains(response, "第一步：检查网络。")
        self.assertContains(response, category.name)
        self.assertContains(response, space.name)
        self.assertContains(
            response,
            timezone.localtime(published_at).strftime("%Y-%m-%d %H:%M"),
        )
        self.assertContains(response, "Windows 11")
        self.assertContains(response, "内网")
        self.assertContains(
            response,
            f'href="{reverse("knowledge:category_detail", args=[category.pk])}"',
            html=False,
        )
        self.assertContains(
            response,
            f'href="{reverse("knowledge:home")}"',
            html=False,
        )
        self.assertNotContains(response, str(article.pk))
        self.assertNotContains(response, space.code)

    def test_published_version_isolated_from_latest_working_version(self):
        article, published = self.publish_visible()
        _set_detail_content(
            published,
            title="正式版本 A 标题",
            summary="正式版本 A 摘要",
            body_text="正式版本 A 正文",
        )
        working = ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status=VersionStatus.DRAFT,
            title="秘密草稿 B 标题",
            summary="秘密草稿 B 摘要",
            body={"secret": "秘密结构化正文"},
            body_plaintext="秘密草稿 B 正文",
            change_summary="未提交草稿",
            created_by=article.owner,
        )
        article.latest_working_version = working
        article.save(update_fields=["latest_working_version"])

        response = self.assert_private(
            self.client.get(reverse("knowledge:article_detail", args=[article.kb_no])),
            200,
        )

        self.assertContains(response, "正式版本 A 标题")
        self.assertContains(response, "正式版本 A 摘要")
        self.assertContains(response, "正式版本 A 正文")
        self.assertNotContains(response, "秘密草稿 B")
        self.assertNotContains(response, "秘密结构化正文")

    def test_html_shaped_text_is_escaped_but_preserved_as_text(self):
        article, version = self.publish_visible()
        title = '<script>alert("title")</script>'
        summary = "<b>summary</b>"
        body_text = '<img src=x onerror=alert(1)>\n<script>alert("body")</script>'
        scope = {"hint": "<em>scope</em>"}
        _set_detail_content(
            version,
            title=title,
            summary=summary,
            body_text=body_text,
            applicable_scope=scope,
        )

        response = self.client.get(reverse("knowledge:article_detail", args=[article.kb_no]))
        html = response.content.decode()

        self.assertIn(escape(title), html)
        self.assertIn(escape(summary), html)
        self.assertIn(escape(body_text), html)
        self.assertIn(escape("<em>scope</em>"), html)
        self.assertNotIn(title, html)
        self.assertNotIn(summary, html)
        self.assertNotIn(body_text, html)
        self.assertNotIn("<em>scope</em>", html)

    def test_empty_body_text_is_200_and_never_falls_back_to_body_json(self):
        article, version = self.publish_visible()
        _set_detail_content(
            version,
            body={"paragraph": "不得展示的结构化正文秘密"},
            body_text="",
        )

        response = self.assert_private(
            self.client.get(reverse("knowledge:article_detail", args=[article.kb_no])),
            200,
        )

        self.assertContains(response, "暂无正文内容。")
        self.assertNotContains(response, "不得展示的结构化正文秘密")


class EmployeeArticleDetailNotFoundTests(EmployeeArticleDetailBase):
    def test_missing_unauthorized_and_non_formal_states_share_one_private_404(self):
        secret_space = _mk_space(name="机密空间", code="secret-detail-space")
        secret_category = _mk_category(
            secret_space,
            name="机密分类",
            code="secret-detail-category",
        )
        unauthorized, unauthorized_version = _publish(
            _mk_article(
                policy=AudiencePolicy.RESTRICTED,
                space=secret_space,
                category=secret_category,
            )
        )
        _set_detail_content(
            unauthorized_version,
            title="无权限秘密标题",
            summary="无权限秘密摘要",
            body_text="无权限秘密正文",
        )

        denied, denied_version = self.publish_visible()
        _set_detail_content(
            denied_version,
            title="DENY 秘密标题",
            summary="DENY 秘密摘要",
            body_text="DENY 秘密正文",
        )
        _add_audience(denied, AudienceType.USER, AudienceEffect.DENY, user=self.user)

        no_pointer = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)

        draft_pointer = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        draft = ArticleVersion.objects.create(
            article=draft_pointer,
            version_no=1,
            status=VersionStatus.DRAFT,
            title="非正式指针秘密标题",
            summary="非正式指针秘密摘要",
            body_plaintext="非正式指针秘密正文",
            change_summary="草稿",
            created_by=draft_pointer.owner,
        )
        Article.objects.filter(pk=draft_pointer.pk).update(current_published_version=draft)

        cross_pointer = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        other, other_version = self.publish_visible()
        Article.objects.filter(pk=cross_pointer.pk).update(current_published_version=other_version)

        offline, _ = self.publish_visible(article_status=ArticleStatus.OFFLINE)
        archived, _ = self.publish_visible(article_status=ArticleStatus.ARCHIVED)
        future, _ = self.publish_visible(effective_at=timezone.now() + timedelta(days=1))

        missing = self.assert_private(
            self.client.get(reverse("knowledge:article_detail", args=["KB-不存在"])),
            404,
        )
        expected_body = missing.content
        cases = (
            unauthorized,
            denied,
            no_pointer,
            draft_pointer,
            cross_pointer,
            offline,
            archived,
            future,
        )
        for article in cases:
            with self.subTest(kb_no=article.kb_no):
                response = self.assert_private(
                    self.client.get(reverse("knowledge:article_detail", args=[article.kb_no])),
                    404,
                )
                self.assertEqual(response.content, expected_body)

        body = expected_body.decode()
        self.assertEqual(body, "未找到可查看的知识。")
        for secret in (
            "无权限秘密标题",
            "无权限秘密摘要",
            "无权限秘密正文",
            "DENY 秘密标题",
            "DENY 秘密摘要",
            "DENY 秘密正文",
            secret_category.name,
            secret_space.name,
        ):
            self.assertNotIn(secret, body)


class EmployeeArticleDetailHttpTests(EmployeeArticleDetailBase):
    def test_anonymous_inactive_disabled_and_departed_are_private_401(self):
        article, _ = self.publish_visible()
        url = reverse("knowledge:article_detail", args=[article.kb_no])

        self.client.logout()
        cases = [("anonymous", self.client)]
        for fields in (
            {"is_active": False},
            {"account_status": AccountStatus.DISABLED},
            {"account_status": AccountStatus.DEPARTED},
        ):
            user = _mk_user()
            client = Client(enforce_csrf_checks=True)
            client.force_login(user)
            type(user).objects.filter(pk=user.pk).update(**fields)
            cases.append((str(fields), client))

        with patch("apps.knowledge.views.get_employee_article_detail") as reader:
            for label, client in cases:
                with self.subTest(case=label):
                    response = self.assert_private(client.get(url), 401)
                    self.assertNotIn("Location", response)
                    self.assertNotContains(response, "正式标题", status_code=401)
            reader.assert_not_called()

    def test_unsafe_methods_are_private_405_with_allow_get_and_no_reader_call(self):
        article, _ = self.publish_visible()
        url = reverse("knowledge:article_detail", args=[article.kb_no])

        with patch("apps.knowledge.views.get_employee_article_detail") as reader:
            for method in ("post", "put", "patch", "delete"):
                with self.subTest(method=method):
                    response = self.assert_private(getattr(self.client, method)(url), 405)
                    self.assertEqual(response["Allow"], "GET")
            reader.assert_not_called()


class EmployeeArticleDetailRouteAndQueryTests(EmployeeArticleDetailBase):
    def test_route_uses_kb_number_and_existing_routes_still_resolve(self):
        article, _ = self.publish_visible()
        detail_url = reverse("knowledge:article_detail", args=[article.kb_no])
        detail_match = resolve(detail_url)

        self.assertEqual(detail_url, f"/kb/{article.kb_no}/")
        self.assertEqual(detail_match.view_name, "knowledge:article_detail")
        self.assertIs(detail_match.func, knowledge_views.employee_article_detail)
        self.assertEqual(detail_match.kwargs, {"kb_no": article.kb_no})
        self.assertIs(resolve("/").func, knowledge_views.employee_home)
        self.assertIs(
            resolve(reverse("knowledge:category_detail", args=[article.category_id])).func,
            knowledge_views.employee_category_detail,
        )
        self.assertEqual(resolve("/admin/").namespace, "admin")
        self.assertEqual(resolve("/health/live").url_name, "health-live")
        self.assertEqual(resolve("/health/ready").url_name, "health-ready")
        self.assertEqual(resolve("/dev/login/").url_name, "dev-login")

    def test_normal_detail_request_uses_three_queries_without_n_plus_one(self):
        article, _ = self.publish_visible()
        url = reverse("knowledge:article_detail", args=[article.kb_no])

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(queries.captured_queries), 3)
