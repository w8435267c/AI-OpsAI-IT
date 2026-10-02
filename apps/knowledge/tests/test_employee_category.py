"""Task 10C 正式员工分类页的权限、分页、模板与查询契约测试。"""

from datetime import timedelta
from uuid import uuid4

from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone
from django.utils.html import escape

from apps.accounts.models import AccountStatus, Department
from apps.knowledge import views as knowledge_views
from apps.knowledge.models import (
    ArticleStatus,
    ArticleVersion,
    AudienceEffect,
    AudiencePolicy,
    AudienceType,
    VersionStatus,
)
from apps.knowledge.tests.test_employee_home import _set_published_content
from apps.knowledge.tests.test_selectors import (
    _add_audience,
    _mk_article,
    _mk_category,
    _mk_space,
    _mk_user,
    _publish,
)


class EmployeeCategoryBase(TestCase):
    def setUp(self):
        self.user = _mk_user()
        self.space = _mk_space(name="员工知识空间")
        self.category = _mk_category(
            self.space,
            name="员工常见问题",
            code="employee-faq",
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.url = reverse("knowledge:category_detail", args=[self.category.pk])

    def assert_private(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        return response

    def publish_visible(
        self,
        *,
        category=None,
        title="正式知识",
        summary="正式摘要",
        published_at=None,
    ):
        category = category or self.category
        article, version = _publish(
            _mk_article(
                policy=AudiencePolicy.ALL_EMPLOYEES,
                space=category.space,
                category=category,
            ),
            published_at=published_at,
        )
        _set_published_content(
            article,
            version,
            title=title,
            summary=summary,
            published_at=published_at,
        )
        return article, version


class EmployeeCategoryHttpTests(EmployeeCategoryBase):
    def test_active_employee_gets_valid_empty_category(self):
        response = self.assert_private(self.client.get(self.url), 200)

        self.assertContains(response, "当前分类暂无可查看的知识。")
        self.assertEqual(response.context["articles"], [])

    def test_anonymous_is_401_without_redirect(self):
        self.client.logout()

        response = self.assert_private(self.client.get(self.url), 401)

        self.assertNotIn("Location", response)

    def test_inactive_disabled_and_departed_accounts_are_401(self):
        cases = (
            {"is_active": False},
            {"account_status": AccountStatus.DISABLED},
            {"account_status": AccountStatus.DEPARTED},
        )
        for fields in cases:
            with self.subTest(fields=fields):
                user = _mk_user()
                client = Client(enforce_csrf_checks=True)
                client.force_login(user)
                type(user).objects.filter(pk=user.pk).update(**fields)

                response = self.assert_private(client.get(self.url), 401)

                self.assertNotIn("Location", response)

    def test_unsafe_methods_are_405_with_allow_get(self):
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = self.assert_private(getattr(self.client, method)(self.url), 405)
                self.assertEqual(response["Allow"], "GET")

    def test_missing_inactive_category_and_inactive_space_are_private_404(self):
        missing_url = reverse("knowledge:category_detail", args=[uuid4()])
        self.assert_private(self.client.get(missing_url), 404)

        inactive_category = _mk_category(
            self.space,
            code="inactive-category",
            is_active=False,
        )
        inactive_category_url = reverse(
            "knowledge:category_detail",
            args=[inactive_category.pk],
        )
        self.assert_private(self.client.get(inactive_category_url), 404)

        inactive_space = _mk_space(name="停用空间", is_active=False)
        category_in_inactive_space = _mk_category(
            inactive_space,
            code="category-in-inactive-space",
        )
        inactive_space_url = reverse(
            "knowledge:category_detail",
            args=[category_in_inactive_space.pk],
        )
        self.assert_private(self.client.get(inactive_space_url), 404)

    def test_category_route_uses_uuid_converter_and_expected_view(self):
        match = resolve(self.url)

        self.assertEqual(match.view_name, "knowledge:category_detail")
        self.assertIs(match.func, knowledge_views.employee_category_detail)
        self.assertEqual(match.kwargs, {"category_id": self.category.pk})


class EmployeeCategoryDataTests(EmployeeCategoryBase):
    def test_only_visible_formal_snapshot_is_rendered_and_html_is_escaped(self):
        self.category.name = '<script>alert("category")</script>'
        self.category.save(update_fields=["name"])
        published_title = "<b>test</b>"
        published_summary = "<img src=x onerror=alert(1)>"
        visible, published = self.publish_visible(
            title=published_title,
            summary=published_summary,
        )
        working = ArticleVersion.objects.create(
            article=visible,
            version_no=2,
            status=VersionStatus.DRAFT,
            title="完全不同草稿标题",
            summary="完全不同草稿摘要",
            body_plaintext="完全不同草稿正文",
            change_summary="未提交草稿",
            created_by=visible.owner,
        )
        visible.latest_working_version = working
        visible.save(update_fields=["latest_working_version"])

        denied, denied_version = self.publish_visible(
            title="显式拒绝标题",
            summary="显式拒绝摘要",
        )
        _add_audience(
            denied,
            AudienceType.USER,
            AudienceEffect.DENY,
            user=self.user,
        )

        other_department = Department.objects.create(name="其他部门")
        department_article, department_version = _publish(
            _mk_article(
                policy=AudiencePolicy.RESTRICTED,
                space=self.space,
                category=self.category,
            )
        )
        _set_published_content(
            department_article,
            department_version,
            title="其他部门标题",
            summary="其他部门摘要",
        )
        _add_audience(
            department_article,
            AudienceType.DEPARTMENT,
            department=other_department,
        )

        unpublished = _mk_article(
            policy=AudiencePolicy.ALL_EMPLOYEES,
            space=self.space,
            category=self.category,
        )
        unpublished.title = "没有正式版本的标题"
        unpublished.save(update_fields=["title"])
        offline, offline_version = _publish(
            _mk_article(
                policy=AudiencePolicy.ALL_EMPLOYEES,
                space=self.space,
                category=self.category,
                article_status=ArticleStatus.OFFLINE,
            )
        )
        _set_published_content(
            offline,
            offline_version,
            title="已下架标题",
            summary="已下架摘要",
        )

        response = self.assert_private(self.client.get(self.url), 200)
        html = response.content.decode()

        self.assertIn(escape(self.category.name), html)
        self.assertNotIn(self.category.name, html)
        self.assertIn(escape(published_title), html)
        self.assertIn(escape(published_summary), html)
        self.assertNotIn(published_title, html)
        self.assertNotIn(published_summary, html)
        self.assertNotIn("完全不同草稿", html)
        self.assertNotIn("显式拒绝", html)
        self.assertNotIn("其他部门", html)
        self.assertNotIn("没有正式版本", html)
        self.assertNotIn("已下架", html)
        self.assertNotIn(str(visible.pk), html)
        self.assertNotIn(str(denied.pk), html)
        self.assertNotIn(str(department_article.pk), html)
        self.assertNotIn(str(unpublished.pk), html)
        self.assertNotIn(str(offline.pk), html)
        self.assertIn(
            f'href="{reverse("knowledge:article_detail", args=[visible.kb_no])}"',
            html,
        )
        self.assertNotIn(denied.kb_no, html)
        self.assertNotIn(department_article.kb_no, html)
        self.assertNotIn(unpublished.kb_no, html)
        self.assertNotIn(offline.kb_no, html)
        self.assertEqual(
            response.context["articles"],
            [
                {
                    "kb_no": visible.kb_no,
                    "title": published_title,
                    "summary": published_summary,
                    "published_at": published.published_at,
                }
            ],
        )

    def test_pagination_is_after_visibility_filter_and_handles_invalid_pages(self):
        base_time = timezone.now() - timedelta(days=2)
        titles = []
        for index in range(21):
            title = f"分页知识-{index:02d}"
            self.publish_visible(
                title=title,
                summary=f"摘要-{index:02d}",
                published_at=base_time + timedelta(minutes=index),
            )
            titles.append(title)

        for index in range(25):
            hidden, _ = _publish(
                _mk_article(
                    policy=AudiencePolicy.RESTRICTED,
                    space=self.space,
                    category=self.category,
                )
            )
            _set_published_content(
                hidden,
                hidden.current_published_version,
                title=f"不可见分页知识-{index:02d}",
                summary="不可见摘要",
            )

        first = self.client.get(self.url)
        second = self.client.get(self.url, {"page": "2"})
        text_page = self.client.get(self.url, {"page": "abc"})
        negative = self.client.get(self.url, {"page": "-1"})
        overflow = self.client.get(self.url, {"page": "999999"})

        self.assertEqual(first.context["pagination"]["count"], 21)
        self.assertEqual(first.context["pagination"]["num_pages"], 2)
        self.assertEqual(first.context["pagination"]["number"], 1)
        self.assertEqual(
            [article["title"] for article in first.context["articles"]],
            list(reversed(titles[1:])),
        )
        self.assertEqual(second.context["pagination"]["number"], 2)
        self.assertEqual(
            [article["title"] for article in second.context["articles"]],
            [titles[0]],
        )
        self.assertEqual(text_page.context["pagination"]["number"], 1)
        self.assertEqual(negative.context["pagination"]["number"], 2)
        self.assertEqual(overflow.context["pagination"]["number"], 2)
        self.assertNotContains(first, "不可见分页知识")
        self.assertNotContains(second, "不可见分页知识")

    def test_parent_category_does_not_include_descendant_articles(self):
        child = _mk_category(
            self.space,
            parent=self.category,
            name="子分类",
            code="child-category",
        )
        self.publish_visible(category=child, title="子分类专属知识")

        response = self.client.get(self.url)

        self.assertEqual(response.context["articles"], [])
        self.assertContains(response, "当前分类暂无可查看的知识。")
        self.assertNotContains(response, "子分类专属知识")


class EmployeeCategoryQueryTests(EmployeeCategoryBase):
    def test_query_count_is_constant_for_three_and_twenty_three_articles(self):
        small_category = _mk_category(
            self.space,
            name="小分类",
            code="small-category",
        )
        large_category = _mk_category(
            self.space,
            name="大分类",
            code="large-category",
        )
        for _ in range(3):
            self.publish_visible(category=small_category)
        for _ in range(23):
            self.publish_visible(category=large_category)

        small_count = self.request_query_count(small_category)
        large_count = self.request_query_count(large_category)

        self.assertEqual(small_count, large_count)
        self.assertEqual(large_count, 5)

    def request_query_count(self, category):
        url = reverse("knowledge:category_detail", args=[category.pk])
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(queries.captured_queries)
