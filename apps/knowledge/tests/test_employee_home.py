"""Task 10B 正式员工首页的权限、数据、路由与模板契约测试。"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.staticfiles import finders
from django.test import Client, TestCase
from django.urls import resolve, reverse
from django.utils import timezone
from django.utils.html import escape

from apps.accounts.models import AccountStatus, Department
from apps.accounts.views import dev_login, dev_logout
from apps.core.views import live, ready
from apps.knowledge import views as knowledge_views
from apps.knowledge.models import (
    ArticleVersion,
    AudienceEffect,
    AudiencePolicy,
    AudienceType,
    VersionStatus,
)
from apps.knowledge.readers import employee_visible_articles
from apps.knowledge.tests.test_selectors import (
    _add_audience,
    _mk_article,
    _mk_category,
    _mk_space,
    _mk_user,
    _publish,
)


def _set_published_content(article, version, *, title, summary, published_at=None):
    effective_published_at = published_at if published_at is not None else version.published_at
    ArticleVersion.objects.filter(pk=version.pk).update(
        title=title,
        summary=summary,
        body_plaintext=f"{title} 正文",
        published_at=effective_published_at,
    )
    return article


class EmployeeHomeHttpTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = _mk_user()
        self.client.force_login(self.user)
        self.url = reverse("knowledge:home")

    def assert_private(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        return response

    def test_active_employee_gets_home_and_reader_is_the_article_source(self):
        article, version = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        _set_published_content(article, version, title="正式知识", summary="正式摘要")

        with patch(
            "apps.knowledge.views.employee_visible_articles",
            wraps=employee_visible_articles,
        ) as reader:
            self.assert_private(self.client.get(self.url), 200)

        self.assertEqual(reader.call_count, 2)
        self.assertTrue(all(call.args[0].pk == self.user.pk for call in reader.call_args_list))

    def test_anonymous_is_401_without_redirect_or_reader_query(self):
        self.client.logout()
        with patch("apps.knowledge.views.employee_visible_articles") as reader:
            response = self.assert_private(self.client.get(self.url), 401)
        reader.assert_not_called()
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
                with patch("apps.knowledge.views.employee_visible_articles") as reader:
                    response = self.assert_private(client.get(self.url), 401)
                reader.assert_not_called()
                self.assertNotIn("Location", response)

    def test_unsafe_methods_are_405_with_allow_even_when_csrf_checks_are_enabled(self):
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                with patch("apps.knowledge.views.employee_visible_articles") as reader:
                    response = self.assert_private(getattr(self.client, method)(self.url), 405)
                reader.assert_not_called()
                self.assertEqual(response["Allow"], "GET")


class EmployeeHomeDataTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _mk_user()
        self.client.force_login(self.user)
        self.url = reverse("knowledge:home")

    def test_home_shows_only_visible_published_snapshot_and_escapes_content(self):
        visible_category = _mk_category(
            _mk_space(name="员工公开空间"),
            name="员工可见分类",
            code="employee-visible",
        )
        article, published = _publish(
            _mk_article(
                policy=AudiencePolicy.ALL_EMPLOYEES,
                space=visible_category.space,
                category=visible_category,
            )
        )
        published_title = '<script>alert("published")</script>'
        published_summary = "<b>OpsAI</b> 正式摘要"
        _set_published_content(
            article,
            published,
            title=published_title,
            summary=published_summary,
        )
        working = ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status=VersionStatus.DRAFT,
            title="秘密工作标题",
            summary="秘密工作摘要",
            body_plaintext="秘密工作正文",
            change_summary="未提交草稿",
            created_by=article.owner,
        )
        article.latest_working_version = working
        article.save(update_fields=["latest_working_version"])

        hidden_category = _mk_category(
            _mk_space(name="绝密内部空间"),
            name="绝密内部分类",
            code="secret-internal-category",
        )
        hidden, hidden_version = _publish(
            _mk_article(
                policy=AudiencePolicy.RESTRICTED,
                space=hidden_category.space,
                category=hidden_category,
            )
        )
        _set_published_content(
            hidden,
            hidden_version,
            title="无权限秘密标题",
            summary="无权限秘密摘要",
        )

        other_department = Department.objects.create(name="其他部门")
        other_department_article, other_department_version = _publish(
            _mk_article(policy=AudiencePolicy.RESTRICTED)
        )
        _set_published_content(
            other_department_article,
            other_department_version,
            title="其他部门专属标题",
            summary="其他部门专属摘要",
        )
        _add_audience(
            other_department_article,
            AudienceType.DEPARTMENT,
            department=other_department,
        )

        denied, denied_version = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        _set_published_content(
            denied,
            denied_version,
            title="显式拒绝标题",
            summary="显式拒绝摘要",
        )
        _add_audience(
            denied,
            AudienceType.USER,
            AudienceEffect.DENY,
            user=self.user,
        )

        it_only, it_version = _publish(_mk_article(policy=AudiencePolicy.IT_ONLY))
        _set_published_content(
            it_only,
            it_version,
            title="仅IT标题",
            summary="仅IT摘要",
        )

        response = self.client.get(self.url)
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn(escape(published_title), html)
        self.assertIn(escape(published_summary), html)
        self.assertNotIn(published_title, html)
        self.assertNotIn(published_summary, html)
        self.assertNotIn("秘密工作", html)
        self.assertNotIn("无权限秘密", html)
        self.assertNotIn("其他部门专属", html)
        self.assertNotIn("绝密内部分类", html)
        self.assertNotIn("secret-internal-category", html)
        self.assertNotIn("绝密内部空间", html)
        self.assertNotIn("显式拒绝", html)
        self.assertNotIn("仅IT", html)
        self.assertNotIn("/categories/", html)
        self.assertNotIn("/kb/", html)

        recent = response.context["recent_articles"]
        self.assertEqual(
            recent,
            [
                {
                    "kb_no": article.kb_no,
                    "title": published_title,
                    "summary": published_summary,
                    "category_name": visible_category.name,
                    "published_at": published.published_at,
                }
            ],
        )
        self.assertEqual(
            response.context["categories"],
            [{"id": visible_category.pk, "name": visible_category.name}],
        )

    def test_category_navigation_deduplicates_and_excludes_inactive_category(self):
        active = _mk_category(
            _mk_space(),
            name="启用分类",
            code="active-home-category",
        )
        inactive = _mk_category(
            _mk_space(),
            name="停用分类",
            code="inactive-home-category",
            is_active=False,
        )
        for _ in range(2):
            _publish(
                _mk_article(
                    policy=AudiencePolicy.ALL_EMPLOYEES,
                    space=active.space,
                    category=active,
                )
            )
        _publish(
            _mk_article(
                policy=AudiencePolicy.ALL_EMPLOYEES,
                space=inactive.space,
                category=inactive,
            )
        )

        response = self.client.get(self.url)

        self.assertEqual(response.context["categories"], [{"id": active.pk, "name": active.name}])
        recent_category_names = {
            article["category_name"] for article in response.context["recent_articles"]
        }
        self.assertEqual(recent_category_names, {active.name, inactive.name})

    def test_recent_articles_are_limited_to_twelve_and_deterministically_ordered(self):
        base_time = timezone.now() - timedelta(days=2)
        expected_titles = []
        for index in range(13):
            article, version = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
            title = f"顺序知识-{index:02d}"
            _set_published_content(
                article,
                version,
                title=title,
                summary=f"摘要-{index:02d}",
                published_at=base_time + timedelta(minutes=index),
            )
            expected_titles.append(title)

        response = self.client.get(self.url)
        recent_titles = [item["title"] for item in response.context["recent_articles"]]

        self.assertEqual(len(recent_titles), 12)
        self.assertEqual(recent_titles, list(reversed(expected_titles[1:])))

    def test_empty_home_is_200_without_filtered_counts(self):
        response = self.client.get(self.url)
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "当前暂无可查看的知识。")
        self.assertEqual(response.context["recent_articles"], [])
        self.assertEqual(response.context["categories"], [])
        self.assertNotIn("过滤", html)
        self.assertNotIn("数据库共有", html)


class EmployeeHomeTemplateAndRouteTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _mk_user()
        self.client.force_login(self.user)

    def test_shared_template_structure_and_local_stylesheet(self):
        response = self.client.get(reverse("knowledge:home"))
        html = response.content.decode()

        self.assertContains(response, "<!doctype html>", html=False)
        self.assertIn('lang="zh-CN"', html)
        self.assertIn('name="viewport"', html)
        self.assertIn("OpsAI IT 故障问答知识库", html)
        self.assertIn("快速查找公司 IT 故障处理知识和操作指引", html)
        self.assertIn("<header", html)
        self.assertIn("<main", html)
        self.assertIn("<footer", html)
        self.assertIn("/static/css/opsai.css", html)
        self.assertIsNotNone(finders.find("css/opsai.css"))
        self.assertNotIn("bootstrap", html.lower())
        self.assertNotIn("htmx", html.lower())

    def test_existing_routes_still_resolve_to_their_original_views(self):
        self.assertIs(resolve("/").func, knowledge_views.employee_home)
        self.assertEqual(resolve("/").view_name, "knowledge:home")
        self.assertEqual(resolve("/admin/").namespace, "admin")
        self.assertIs(resolve("/health/live").func, live)
        self.assertIs(resolve("/health/ready").func, ready)
        self.assertIs(resolve("/dev/login/").func, dev_login)
        self.assertIs(resolve("/dev/logout/").func, dev_logout)
