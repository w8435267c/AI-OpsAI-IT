"""Task 10A 正式员工知识 Reader 契约测试。"""

from dataclasses import FrozenInstanceError
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.safestring import SafeData

from apps.accounts.models import (
    AccountStatus,
    Department,
    UserDepartment,
    UserGroup,
    UserGroupMembership,
)
from apps.knowledge.models import (
    Article,
    ArticleStatus,
    ArticleVersion,
    AudienceEffect,
    AudiencePolicy,
    AudienceType,
    ReviewRecord,
    VersionStatus,
)
from apps.knowledge.readers import employee_visible_articles, get_employee_article_detail
from apps.knowledge.tests.test_selectors import (
    _add_audience,
    _mk_article,
    _mk_user,
    _publish,
)


class EmployeeDetailSnapshotTests(TestCase):
    def test_detail_uses_published_version_whitelist(self):
        user = _mk_user()
        article, version = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        published_at = timezone.now() - timedelta(hours=1)
        Article.objects.filter(pk=article.pk).update(title="主表标题不应作为详情快照")
        ArticleVersion.objects.filter(pk=version.pk).update(
            title="正式版本标题",
            summary="正式版本摘要",
            applicable_scope={"systems": ["Windows 11"], "network": "内网"},
            body={"unknown": [{"node": "不解析"}]},
            body_plaintext="正式版本正文",
            published_at=published_at,
        )

        detail = get_employee_article_detail(user, article.kb_no)

        self.assertIsNotNone(detail)
        self.assertEqual(detail.kb_no, article.kb_no)
        self.assertEqual(detail.title, "正式版本标题")
        self.assertEqual(detail.summary, "正式版本摘要")
        self.assertEqual(
            detail.applicable_scope,
            {"systems": ["Windows 11"], "network": "内网"},
        )
        self.assertEqual(detail.body_text, "正式版本正文")
        self.assertEqual(detail.category_id, article.category_id)
        self.assertEqual(detail.category_name, article.category.name)
        self.assertEqual(detail.space_id, article.space_id)
        self.assertEqual(detail.space_code, article.space.code)
        self.assertEqual(detail.space_name, article.space.name)
        self.assertEqual(detail.published_at, published_at)
        with self.assertRaises(FrozenInstanceError):
            detail.title = "不能修改"

    def test_latest_working_version_never_leaks_into_detail(self):
        user = _mk_user()
        article, published = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        ArticleVersion.objects.filter(pk=published.pk).update(
            title="正式标题",
            summary="正式摘要",
            body_plaintext="正式正文",
        )
        working = ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status=VersionStatus.DRAFT,
            title="秘密工作标题",
            summary="秘密工作摘要",
            applicable_scope={"secret": True},
            body={"secret": "工作正文"},
            body_plaintext="秘密工作正文",
            change_summary="未提交工作版本",
            created_by=article.owner,
        )
        article.latest_working_version = working
        article.save(update_fields=["latest_working_version"])

        detail = get_employee_article_detail(user, article.kb_no)

        self.assertEqual(detail.title, "正式标题")
        self.assertEqual(detail.summary, "正式摘要")
        self.assertEqual(detail.body_text, "正式正文")
        self.assertNotIn("秘密", repr(detail))

    def test_missing_pointer_does_not_fall_back_to_historical_published_version(self):
        user = _mk_user()
        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        Article.objects.filter(pk=article.pk).update(current_published_version=None)

        self.assertIsNone(get_employee_article_detail(user, article.kb_no))

    def test_non_published_or_cross_article_pointer_is_not_readable(self):
        user = _mk_user()
        draft_article = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        draft = ArticleVersion.objects.create(
            article=draft_article,
            version_no=1,
            status=VersionStatus.DRAFT,
            title="草稿",
            summary="草稿摘要",
            body_plaintext="草稿正文",
            change_summary="草稿",
            created_by=draft_article.owner,
        )
        Article.objects.filter(pk=draft_article.pk).update(current_published_version=draft)

        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        other, other_version = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        Article.objects.filter(pk=article.pk).update(current_published_version=other_version)

        self.assertIsNone(get_employee_article_detail(user, draft_article.kb_no))
        self.assertIsNone(get_employee_article_detail(user, article.kb_no))
        self.assertIsNotNone(get_employee_article_detail(user, other.kb_no))

    def test_reader_trusts_formal_published_pointer_without_review_record(self):
        user = _mk_user()
        article, version = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        self.assertFalse(ReviewRecord.objects.filter(article_version=version).exists())

        detail = get_employee_article_detail(user, article.kb_no)

        self.assertIsNotNone(detail)
        self.assertEqual(detail.kb_no, article.kb_no)

    def test_body_text_is_plain_string_and_not_marked_safe(self):
        user = _mk_user()
        article, version = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        body_text = "<script>alert(1)</script>\n<b>test</b>"
        ArticleVersion.objects.filter(pk=version.pk).update(body_plaintext=body_text)

        detail = get_employee_article_detail(user, article.kb_no)

        self.assertEqual(detail.body_text, body_text)
        self.assertIs(type(detail.body_text), str)
        self.assertNotIsInstance(detail.body_text, SafeData)

    def test_empty_body_plaintext_does_not_fall_back_to_body_json(self):
        user = _mk_user()
        article, version = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        ArticleVersion.objects.filter(pk=version.pk).update(
            body={"paragraph": "不得回退的结构化正文"},
            body_plaintext="",
        )

        detail = get_employee_article_detail(user, article.kb_no)

        self.assertEqual(detail.body_text, "")
        self.assertNotIn("不得回退", repr(detail))


class EmployeeReaderAudienceTests(TestCase):
    def test_all_employees_and_three_restricted_allow_targets(self):
        user = _mk_user()
        department = Department.objects.create(name="Reader 允许部门")
        group = UserGroup.objects.create(name="Reader 允许内容组")
        UserDepartment.objects.create(user=user, department=department)
        UserGroupMembership.objects.create(user=user, user_group=group)

        all_article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        department_article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        group_article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        user_article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(department_article, AudienceType.DEPARTMENT, department=department)
        _add_audience(group_article, AudienceType.USER_GROUP, user_group=group)
        _add_audience(user_article, AudienceType.USER, user=user)

        visible_ids = set(employee_visible_articles(user).values_list("pk", flat=True))

        self.assertTrue(
            {all_article.pk, department_article.pk, group_article.pk, user_article.pk}
            <= visible_ids
        )

    def test_it_only_uses_configured_active_content_group(self):
        user = _mk_user()
        group = UserGroup.objects.create(name="Reader IT 内容组")
        UserGroupMembership.objects.create(user=user, user_group=group)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.IT_ONLY))

        with self.settings(KNOWLEDGE_IT_USER_GROUP_ID=group.pk):
            self.assertIsNotNone(get_employee_article_detail(user, article.kb_no))

    def test_department_group_and_user_deny_override_allow(self):
        user = _mk_user()
        department = Department.objects.create(name="Reader 拒绝部门")
        group = UserGroup.objects.create(name="Reader 拒绝内容组")
        UserDepartment.objects.create(user=user, department=department)
        UserGroupMembership.objects.create(user=user, user_group=group)

        cases = (
            (AudienceType.DEPARTMENT, {"department": department}),
            (AudienceType.USER_GROUP, {"user_group": group}),
            (AudienceType.USER, {"user": user}),
        )
        for audience_type, target in cases:
            with self.subTest(audience_type=audience_type):
                article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
                _add_audience(article, audience_type, AudienceEffect.ALLOW, **target)
                _add_audience(article, audience_type, AudienceEffect.DENY, **target)
                self.assertIsNone(get_employee_article_detail(user, article.kb_no))

    def test_staff_superuser_author_and_space_owner_do_not_bypass(self):
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        staff = _mk_user(is_staff=True)
        superuser = _mk_user(is_staff=True, is_superuser=True)

        for user in (staff, superuser, article.owner, article.space.owner):
            with self.subTest(user=user.username):
                self.assertIsNone(get_employee_article_detail(user, article.kb_no))


class EmployeeReaderStateTests(TestCase):
    def test_anonymous_and_invalid_accounts_receive_no_detail(self):
        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        inactive = _mk_user(is_active=False)
        disabled = _mk_user(account_status=AccountStatus.DISABLED)
        departed = _mk_user(account_status=AccountStatus.DEPARTED)

        for user in (AnonymousUser(), inactive, disabled, departed):
            with self.subTest(user=type(user).__name__):
                self.assertIsNone(get_employee_article_detail(user, article.kb_no))

    def test_article_lifecycle_and_effective_time_are_enforced(self):
        user = _mk_user()
        active, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        offline, _ = _publish(
            _mk_article(
                policy=AudiencePolicy.ALL_EMPLOYEES,
                article_status=ArticleStatus.OFFLINE,
            )
        )
        archived, _ = _publish(
            _mk_article(
                policy=AudiencePolicy.ALL_EMPLOYEES,
                article_status=ArticleStatus.ARCHIVED,
            )
        )
        future, _ = _publish(
            _mk_article(
                policy=AudiencePolicy.ALL_EMPLOYEES,
                effective_at=timezone.now() + timedelta(days=1),
            )
        )
        draft_only = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        working = ArticleVersion.objects.create(
            article=draft_only,
            version_no=1,
            status=VersionStatus.DRAFT,
            title="仅工作版本",
            summary="不可见",
            body_plaintext="不可见",
            change_summary="草稿",
            created_by=draft_only.owner,
        )
        draft_only.latest_working_version = working
        draft_only.save(update_fields=["latest_working_version"])

        self.assertIsNotNone(get_employee_article_detail(user, active.kb_no))
        for article in (offline, archived, future, draft_only):
            with self.subTest(article=article.kb_no):
                self.assertIsNone(get_employee_article_detail(user, article.kb_no))

    def test_inactive_category_does_not_hide_formal_article(self):
        user = _mk_user()
        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        article.category.is_active = False
        article.category.save(update_fields=["is_active"])

        self.assertIsNotNone(get_employee_article_detail(user, article.kb_no))


class EmployeeReaderQueryTests(TestCase):
    def test_base_queryset_is_preserved(self):
        user = _mk_user()
        included, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        excluded, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))

        result = employee_visible_articles(
            user,
            base=Article.objects.filter(pk=included.pk),
        )

        self.assertIn(included, result)
        self.assertNotIn(excluded, result)

    def test_related_access_query_count_does_not_grow_with_article_count(self):
        user = _mk_user()
        for _ in range(3):
            _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))

        small_count = self._related_access_query_count(user)

        for _ in range(20):
            _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))

        large_count = self._related_access_query_count(user)

        self.assertEqual(small_count, large_count)
        self.assertEqual(large_count, 1)

    def _related_access_query_count(self, user):
        with CaptureQueriesContext(connection) as queries:
            articles = list(employee_visible_articles(user))
            for article in articles:
                _ = (
                    article.current_published_version.title,
                    article.category.name,
                    article.space.name,
                )
        return len(queries.captured_queries)
