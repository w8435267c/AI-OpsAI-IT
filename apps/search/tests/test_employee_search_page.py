"""Task 11B 员工搜索入口、结果页与分页安全契约测试。"""

from datetime import timedelta
from urllib.parse import urlencode

from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone
from django.utils.html import escape

from apps.accounts.models import AccountStatus
from apps.knowledge.models import (
    ArticleVersion,
    AudienceEffect,
    AudiencePolicy,
    AudienceType,
    VersionStatus,
)
from apps.knowledge.tests.test_selectors import (
    _add_audience,
    _mk_article,
    _mk_category,
    _mk_space,
    _mk_user,
)
from apps.search import views as search_views
from apps.search.tests.test_employee_search_reader import (
    SEARCH_TERM,
    _make_visible_article,
)


class EmployeeSearchPageBase(TestCase):
    def setUp(self):
        self.user = _mk_user()
        self.space = _mk_space(owner=self.user)
        self.category = _mk_category(
            self.space,
            name="电脑故障",
            code="search-computer-issues",
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.url = reverse("search:results")

    def assert_private(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        return response

    def publish_visible(
        self,
        *,
        title="正式知识",
        summary="正式摘要",
        body_plaintext="正式正文",
        published_at=None,
    ):
        return _make_visible_article(
            title=title,
            summary=summary,
            body_plaintext=body_plaintext,
            published_at=published_at,
            space=self.space,
            category=self.category,
            owner=self.user,
        )


class EmployeeSearchHttpTests(EmployeeSearchPageBase):
    def test_active_employee_gets_search_page_and_route_is_named(self):
        response = self.assert_private(self.client.get(self.url), 200)

        self.assertEqual(self.url, "/search/")
        match = resolve(self.url)
        self.assertEqual(match.view_name, "search:results")
        self.assertIs(match.func, search_views.employee_search_results)
        self.assertContains(response, "请输入关键词开始搜索。")

    def test_anonymous_inactive_disabled_and_departed_accounts_are_401(self):
        clients = [Client(enforce_csrf_checks=True)]
        for fields in (
            {"is_active": False},
            {"account_status": AccountStatus.DISABLED},
            {"account_status": AccountStatus.DEPARTED},
        ):
            user = _mk_user(**fields)
            client = Client(enforce_csrf_checks=True)
            client.force_login(user)
            clients.append(client)

        for client in clients:
            with self.subTest(client=client):
                response = self.assert_private(client.get(self.url), 401)
                self.assertNotIn("Location", response)

    def test_unsafe_methods_are_405_with_allow_get(self):
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = self.assert_private(getattr(self.client, method)(self.url), 405)
                self.assertEqual(response["Allow"], "GET")


class EmployeeSearchResultTests(EmployeeSearchPageBase):
    def test_title_summary_and_body_matches_render_safe_formal_fields(self):
        title_article, _ = self.publish_visible(title="网络故障排查")
        summary_article, _ = self.publish_visible(summary="网络故障摘要")
        body_article, _ = self.publish_visible(body_plaintext="网络故障正文")

        response = self.assert_private(self.client.get(self.url, {"q": SEARCH_TERM}), 200)
        articles = response.context["articles"]

        self.assertEqual(
            {article["kb_no"] for article in articles},
            {title_article.kb_no, summary_article.kb_no, body_article.kb_no},
        )
        self.assertEqual(response.context["pagination"]["count"], 3)
        for article in articles:
            self.assertEqual(article["category_name"], self.category.name)

    def test_empty_whitespace_and_zero_result_messages_do_not_show_all_articles(self):
        article, _ = self.publish_visible(title="不应在空查询展示")
        for query in (None, "", "   "):
            with self.subTest(query=query):
                params = {} if query is None else {"q": query}
                response = self.assert_private(self.client.get(self.url, params), 200)
                html = response.content.decode()
                self.assertContains(response, "请输入关键词开始搜索。")
                self.assertEqual(response.context["articles"], [])
                self.assertEqual(response.context["pagination"]["count"], 0)
                self.assertNotIn(article.kb_no, html)

        response = self.assert_private(
            self.client.get(self.url, {"q": "完全不存在的关键词"}),
            200,
        )
        self.assertContains(response, "未找到可查看的相关知识。")
        self.assertContains(response, "尝试更换关键词。")
        self.assertNotContains(response, "无权限")

    def test_deny_is_excluded_from_results_count_and_html(self):
        allowed, _ = self.publish_visible(title=SEARCH_TERM)
        denied, _ = self.publish_visible(title=SEARCH_TERM)
        _add_audience(
            denied,
            AudienceType.USER,
            AudienceEffect.DENY,
            user=self.user,
        )

        response = self.client.get(self.url, {"q": SEARCH_TERM})
        html = response.content.decode()

        self.assertEqual(response.context["pagination"]["count"], 1)
        self.assertEqual(
            [article["kb_no"] for article in response.context["articles"]], [allowed.kb_no]
        )
        self.assertIn(allowed.kb_no, html)
        self.assertNotIn(denied.kb_no, html)
        self.assertNotIn(str(denied.pk), html)

    def test_draft_only_and_unpublished_keywords_do_not_leak(self):
        article, _ = self.publish_visible(title="电脑无法上网怎么办")
        secret = "超级管理员绝密网络命令"
        draft = ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status=VersionStatus.DRAFT,
            title=secret,
            summary=secret,
            body_plaintext=secret,
            change_summary="内部草稿",
            created_by=self.user,
        )
        type(article).objects.filter(pk=article.pk).update(latest_working_version=draft)
        unpublished = _mk_article(
            policy=AudiencePolicy.ALL_EMPLOYEES,
            space=self.space,
            category=self.category,
            owner=self.user,
        )

        response = self.client.get(self.url, {"q": secret})
        html = response.content.decode()

        self.assertEqual(response.context["pagination"]["count"], 0)
        self.assertEqual(response.context["articles"], [])
        self.assertNotIn(article.kb_no, html)
        self.assertNotIn(unpublished.kb_no, html)
        self.assertNotIn(secret, html.replace(escape(secret), ""))
        self.assertNotContains(response, "无权限")

    def test_query_and_formal_content_are_autoescaped_without_uuid_leak(self):
        query = '"><script>alert(1)</script>'
        title = '<b>网络故障标题</b><script>alert("title")</script>'
        summary = '<img src=x onerror=alert("summary")>'
        article, _ = self.publish_visible(
            title=title,
            summary=summary,
            body_plaintext=f"正文包含 {query}",
        )

        response = self.client.get(self.url, {"q": query})
        html = response.content.decode()

        self.assertIn(escape(query), html)
        self.assertNotIn(query, html)
        self.assertIn(escape(title), html)
        self.assertIn(escape(summary), html)
        self.assertNotIn(title, html)
        self.assertNotIn(summary, html)
        self.assertNotIn(str(article.pk), html)
        self.assertNotIn("<mark", html)

    def test_result_link_uses_kb_number_and_existing_detail_reauthorizes(self):
        article, _ = self.publish_visible(title=SEARCH_TERM)
        detail_url = reverse("knowledge:article_detail", args=[article.kb_no])

        response = self.client.get(self.url, {"q": SEARCH_TERM})

        self.assertIn(f'href="{detail_url}"', response.content.decode())
        detail_response = self.assert_private(self.client.get(detail_url), 200)
        self.assertContains(detail_response, SEARCH_TERM)


class EmployeeSearchPaginationTests(EmployeeSearchPageBase):
    def test_pagination_uses_only_visible_results_and_preserves_query(self):
        for index in range(21):
            self.publish_visible(
                title=f"{SEARCH_TERM}-{index:02d}",
                published_at=timezone.now() + timedelta(minutes=index),
            )
        denied_articles = []
        for index in range(30):
            denied, _ = self.publish_visible(title=f"{SEARCH_TERM}-隐藏-{index:02d}")
            _add_audience(
                denied,
                AudienceType.USER,
                AudienceEffect.DENY,
                user=self.user,
            )
            denied_articles.append(denied)

        first = self.assert_private(self.client.get(self.url, {"q": SEARCH_TERM}), 200)
        second = self.assert_private(
            self.client.get(self.url, {"q": SEARCH_TERM, "page": "2"}),
            200,
        )

        self.assertEqual(first.context["pagination"]["count"], 21)
        self.assertEqual(first.context["pagination"]["num_pages"], 2)
        self.assertEqual(len(first.context["articles"]), 20)
        self.assertEqual(second.context["pagination"]["number"], 2)
        self.assertEqual(len(second.context["articles"]), 1)
        query_string = urlencode({"q": SEARCH_TERM})
        self.assertIn(f"?{query_string}&amp;page=2", first.content.decode())
        combined_html = first.content.decode() + second.content.decode()
        for article in denied_articles:
            self.assertNotIn(article.kb_no, combined_html)

    def test_invalid_overflow_and_negative_pages_follow_get_page_contract(self):
        for index in range(21):
            self.publish_visible(title=f"{SEARCH_TERM}-{index:02d}")

        text_page = self.client.get(self.url, {"q": SEARCH_TERM, "page": "abc"})
        overflow = self.client.get(self.url, {"q": SEARCH_TERM, "page": "999999"})
        negative = self.client.get(self.url, {"q": SEARCH_TERM, "page": "-1"})

        self.assertEqual(text_page.context["pagination"]["number"], 1)
        self.assertEqual(overflow.context["pagination"]["number"], 2)
        self.assertEqual(negative.context["pagination"]["number"], 2)


class EmployeeSearchHomeAndQueryTests(EmployeeSearchPageBase):
    def test_home_has_get_search_form_without_breaking_existing_content(self):
        article, _ = self.publish_visible(title="首页正式知识")
        home = self.assert_private(self.client.get(reverse("knowledge:home")), 200)
        html = home.content.decode()

        self.assertIn('method="get"', html)
        self.assertIn(f'action="{self.url}"', html)
        self.assertIn('name="q"', html)
        self.assertIn("请输入故障现象或关键词，例如：无法上网", html)
        self.assertIn(self.category.name, html)
        self.assertIn(article.kb_no, html)

    def test_search_query_count_is_constant_for_three_and_twenty_three_results(self):
        for _ in range(3):
            self.publish_visible(title=SEARCH_TERM)
        small_count = self.request_query_count()

        for _ in range(20):
            self.publish_visible(title=SEARCH_TERM)
        large_count = self.request_query_count()

        self.assertEqual(small_count, large_count)
        self.assertEqual(large_count, 4)

    def request_query_count(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url, {"q": SEARCH_TERM})
        self.assertEqual(response.status_code, 200)
        return len(queries.captured_queries)
