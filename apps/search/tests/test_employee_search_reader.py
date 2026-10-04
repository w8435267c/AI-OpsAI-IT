"""Task 11A 员工安全搜索 Reader 契约测试。"""

from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.db.models import QuerySet
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.safestring import SafeData

from apps.accounts.models import AccountStatus, User
from apps.knowledge.models import (
    Article,
    ArticleStatus,
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
    _publish,
)
from apps.search.readers import search_employee_articles

SEARCH_TERM = "网络故障"


def _set_published_content(
    version,
    *,
    title="正式知识",
    summary="正式摘要",
    body_plaintext="正式正文",
    published_at=None,
):
    published_at = published_at or timezone.now()
    ArticleVersion.objects.filter(pk=version.pk).update(
        title=title,
        summary=summary,
        body_plaintext=body_plaintext,
        published_at=published_at,
    )
    version.refresh_from_db()
    return version


def _make_visible_article(
    *,
    title="正式知识",
    summary="正式摘要",
    body_plaintext="正式正文",
    published_at=None,
    **article_kwargs,
):
    article, version = _publish(
        _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES, **article_kwargs),
        published_at=published_at,
    )
    _set_published_content(
        version,
        title=title,
        summary=summary,
        body_plaintext=body_plaintext,
        published_at=published_at,
    )
    return article, version


class EmployeeSearchMatchingTests(TestCase):
    def setUp(self):
        self.user = _mk_user()

    def test_title_summary_and_body_matches_use_or_semantics(self):
        title_article, _ = _make_visible_article(title="VPN 网络故障排查")
        summary_article, _ = _make_visible_article(summary="处理网络故障的摘要")
        body_article, _ = _make_visible_article(body_plaintext="网络故障处理步骤")
        _make_visible_article(
            title="打印机处理",
            summary="打印机摘要",
            body_plaintext="打印机正文",
        )

        result = search_employee_articles(self.user, "  网络故障  ")

        self.assertIsInstance(result, QuerySet)
        self.assertEqual(
            set(result.values_list("pk", flat=True)),
            {title_article.pk, summary_article.pk, body_article.pk},
        )

    def test_ascii_matching_is_case_insensitive_and_chinese_substrings_work(self):
        article, _ = _make_visible_article(title="VPN 电脑无法上网怎么办")

        self.assertEqual(list(search_employee_articles(self.user, "vpn")), [article])
        self.assertEqual(list(search_employee_articles(self.user, "无法上网")), [article])

    def test_none_empty_and_whitespace_queries_return_no_articles(self):
        _make_visible_article(title="任何正式知识")

        for query in (None, "", "   ", "\t\r\n"):
            with self.subTest(query=query):
                self.assertEqual(list(search_employee_articles(self.user, query)), [])

    def test_one_article_matching_multiple_fields_is_returned_once(self):
        article, _ = _make_visible_article(
            title=SEARCH_TERM,
            summary=SEARCH_TERM,
            body_plaintext=SEARCH_TERM,
        )

        result = search_employee_articles(self.user, SEARCH_TERM)

        self.assertEqual(list(result), [article])
        self.assertEqual(result.count(), 1)

    def test_base_queryset_is_preserved_and_result_remains_sliceable(self):
        included, _ = _make_visible_article(title=SEARCH_TERM)
        _make_visible_article(title=SEARCH_TERM)
        base = Article.objects.filter(pk=included.pk)

        result = search_employee_articles(self.user, SEARCH_TERM, base=base)

        self.assertEqual(list(result[:1]), [included])

    def test_special_characters_are_parameterized_plain_text(self):
        content = "100% _ 单引号' < > <script>"
        article, version = _make_visible_article(title=content)

        for query in ("%", "_", "'", "<", ">", "<script>"):
            with self.subTest(query=query):
                self.assertEqual(list(search_employee_articles(self.user, query)), [article])
        self.assertEqual(version.title, content)
        self.assertNotIsInstance(version.title, SafeData)


class EmployeeSearchSecurityTests(TestCase):
    def setUp(self):
        self.user = _mk_user()

    def test_latest_draft_content_never_matches(self):
        article, published = _make_visible_article(
            title="电脑无法上网怎么办",
            summary="正式摘要",
            body_plaintext="正式正文",
        )
        draft = ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status=VersionStatus.DRAFT,
            title="超级管理员内部网络修复密码",
            summary="超级管理员内部网络修复密码",
            body_plaintext="超级管理员内部网络修复密码",
            change_summary="内部草稿",
            created_by=article.owner,
        )
        Article.objects.filter(pk=article.pk).update(latest_working_version=draft)

        self.assertEqual(list(search_employee_articles(self.user, "电脑无法上网")), [article])
        self.assertEqual(
            list(search_employee_articles(self.user, "超级管理员内部网络修复密码")),
            [],
        )
        self.assertEqual(article.current_published_version_id, published.pk)

    def test_deny_article_does_not_appear_or_affect_visible_count(self):
        allowed, _ = _make_visible_article(title=SEARCH_TERM)
        denied, _ = _make_visible_article(title=SEARCH_TERM)
        _add_audience(
            denied,
            AudienceType.USER,
            AudienceEffect.DENY,
            user=self.user,
        )

        result = search_employee_articles(self.user, SEARCH_TERM)

        self.assertEqual(list(result), [allowed])
        self.assertEqual(result.count(), 1)

    def test_existing_visibility_boundaries_are_applied_before_search(self):
        visible, _ = _make_visible_article(title=SEARCH_TERM)
        _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        _make_visible_article(title=SEARCH_TERM, effective_at=timezone.now() + timedelta(days=1))
        _make_visible_article(title=SEARCH_TERM, article_status=ArticleStatus.OFFLINE)
        _make_visible_article(title=SEARCH_TERM, article_status=ArticleStatus.ARCHIVED)
        inactive_space = _mk_space(is_active=False)
        _make_visible_article(
            title=SEARCH_TERM,
            space=inactive_space,
            category=_mk_category(inactive_space),
        )

        wrong_status_article = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        draft = ArticleVersion.objects.create(
            article=wrong_status_article,
            version_no=1,
            status=VersionStatus.DRAFT,
            title=SEARCH_TERM,
            summary=SEARCH_TERM,
            body_plaintext=SEARCH_TERM,
            change_summary="未发布",
            created_by=wrong_status_article.owner,
        )
        Article.objects.filter(pk=wrong_status_article.pk).update(current_published_version=draft)

        cross_pointer_article = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        source_article, source_version = _make_visible_article(title=SEARCH_TERM)
        Article.objects.filter(pk=cross_pointer_article.pk).update(
            current_published_version=source_version
        )
        Article.objects.filter(pk=source_article.pk).update(current_published_version=None)

        result = search_employee_articles(self.user, SEARCH_TERM)

        self.assertEqual(list(result), [visible])
        self.assertEqual(result.count(), 1)

    def test_anonymous_unsaved_inactive_disabled_and_departed_accounts_see_nothing(self):
        _make_visible_article(title=SEARCH_TERM)
        users = (
            None,
            AnonymousUser(),
            User(username="unsaved-search-user"),
            _mk_user(is_active=False),
            _mk_user(account_status=AccountStatus.DISABLED),
            _mk_user(account_status=AccountStatus.DEPARTED),
        )

        for user in users:
            with self.subTest(user=user):
                self.assertEqual(list(search_employee_articles(user, SEARCH_TERM)), [])


class EmployeeSearchOrderingTests(TestCase):
    def setUp(self):
        self.user = _mk_user()

    def test_title_then_summary_then_body_priority(self):
        now = timezone.now()
        title_article, _ = _make_visible_article(
            title=SEARCH_TERM,
            published_at=now - timedelta(days=3),
        )
        summary_article, _ = _make_visible_article(
            summary=SEARCH_TERM,
            published_at=now - timedelta(days=2),
        )
        body_article, _ = _make_visible_article(
            body_plaintext=SEARCH_TERM,
            published_at=now - timedelta(days=1),
        )

        self.assertEqual(
            list(search_employee_articles(self.user, SEARCH_TERM)),
            [title_article, summary_article, body_article],
        )

    def test_same_priority_orders_by_publication_update_and_primary_key(self):
        now = timezone.now()
        newest, _ = _make_visible_article(
            body_plaintext=SEARCH_TERM,
            published_at=now,
        )
        updated_newer, _ = _make_visible_article(
            body_plaintext=SEARCH_TERM,
            published_at=now - timedelta(days=1),
        )
        tied_a, _ = _make_visible_article(
            body_plaintext=SEARCH_TERM,
            published_at=now - timedelta(days=1),
        )
        tied_b, _ = _make_visible_article(
            body_plaintext=SEARCH_TERM,
            published_at=now - timedelta(days=1),
        )
        older, _ = _make_visible_article(
            body_plaintext=SEARCH_TERM,
            published_at=now - timedelta(days=2),
        )
        shared_updated_at = now - timedelta(hours=2)
        Article.objects.filter(pk=updated_newer.pk).update(updated_at=now - timedelta(hours=1))
        Article.objects.filter(pk__in=(tied_a.pk, tied_b.pk)).update(updated_at=shared_updated_at)
        tied = sorted((tied_a, tied_b), key=lambda article: article.pk)

        self.assertEqual(
            [article.pk for article in search_employee_articles(self.user, SEARCH_TERM)],
            [newest.pk, updated_newer.pk, tied[0].pk, tied[1].pk, older.pk],
        )


class EmployeeSearchQueryCountTests(TestCase):
    def setUp(self):
        self.user = _mk_user()

    def test_related_field_access_is_constant_for_three_and_twenty_three_results(self):
        for _ in range(3):
            _make_visible_article(title=SEARCH_TERM)
        small_count = self._query_count()

        for _ in range(20):
            _make_visible_article(title=SEARCH_TERM)
        large_count = self._query_count()

        self.assertEqual(small_count, large_count)
        self.assertEqual(small_count, 1)
        self.assertEqual(large_count, 1)

    def _query_count(self):
        with CaptureQueriesContext(connection) as queries:
            rows = [
                (
                    article.kb_no,
                    article.current_published_version.title,
                    article.current_published_version.summary,
                    article.category.name,
                    article.space.name,
                )
                for article in search_employee_articles(self.user, SEARCH_TERM)
            ]
        self.assertTrue(rows)
        return len(queries.captured_queries)
