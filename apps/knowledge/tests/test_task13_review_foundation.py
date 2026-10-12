"""Task 13-02A：审核范围、核心约束与动作权限底座测试。"""

from datetime import timedelta

from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import ROLE_REVIEWER, SYSTEM_ROLE_BY_CODE
from apps.knowledge.models import (
    Article,
    ArticleType,
    ArticleVersion,
    Category,
    KnowledgeSpace,
    ReviewDecision,
    ReviewerSpaceScope,
    ReviewRecord,
    ReviewType,
    VersionStatus,
)


class ReviewFoundationFixtures:
    """为本文件提供不依赖 Service 的直接 ORM 测试数据。"""

    _sequence = 0

    @classmethod
    def next_value(cls) -> int:
        cls._sequence += 1
        return cls._sequence

    def create_user(self, prefix: str = "user") -> User:
        sequence = self.next_value()
        return User.objects.create_user(username=f"{prefix}-{sequence}")

    def create_space(self, *, owner: User | None = None) -> KnowledgeSpace:
        sequence = self.next_value()
        return KnowledgeSpace.objects.create(
            code=f"review-space-{sequence}",
            name=f"审核空间 {sequence}",
            space_type="employee",
            owner=owner or self.create_user("space-owner"),
        )

    def create_article(self) -> Article:
        sequence = self.next_value()
        owner = self.create_user("article-owner")
        space = self.create_space()
        category = Category.objects.create(
            space=space,
            code=f"review-category-{sequence}",
            name=f"审核分类 {sequence}",
        )
        return Article.objects.create(
            kb_no=f"KB-{sequence:06d}",
            title=f"审核文章 {sequence}",
            space=space,
            category=category,
            article_type=ArticleType.GUIDE,
            owner=owner,
            created_by=owner,
            updated_by=owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )

    def create_version(
        self,
        article: Article,
        version_no: int,
        status: str,
    ) -> ArticleVersion:
        submitted = status not in (VersionStatus.DRAFT, VersionStatus.SAVED)
        published = status == VersionStatus.PUBLISHED
        submitter = self.create_user("submitter") if submitted else None
        submitted_at = timezone.now() if submitted else None
        return ArticleVersion.objects.create(
            article=article,
            version_no=version_no,
            status=status,
            title=f"版本 {version_no}",
            summary="审核底座测试",
            change_summary="审核底座测试",
            created_by=article.created_by,
            submitted_by=submitter,
            submitted_at=submitted_at,
            published_at=submitted_at if published else None,
        )


class ReviewerSpaceScopeTests(ReviewFoundationFixtures, TestCase):
    def test_minimal_scope_has_expected_defaults_relations_and_timestamps(self):
        reviewer = self.create_user("reviewer")
        space = self.create_space()

        scope = ReviewerSpaceScope.objects.create(reviewer=reviewer, space=space)

        self.assertTrue(scope.is_active)
        self.assertEqual(scope.reviewer, reviewer)
        self.assertEqual(scope.space, space)
        self.assertIn(scope, reviewer.review_space_scopes.all())
        self.assertIn(scope, space.reviewer_scopes.all())
        self.assertIsNotNone(scope.created_at)
        self.assertIsNotNone(scope.updated_at)

    def test_same_reviewer_and_space_is_unique_even_when_inactive(self):
        reviewer = self.create_user("reviewer")
        space = self.create_space()
        ReviewerSpaceScope.objects.create(reviewer=reviewer, space=space, is_active=False)

        with self.assertRaises(IntegrityError), transaction.atomic():
            ReviewerSpaceScope.objects.create(reviewer=reviewer, space=space)

    def test_same_reviewer_and_space_fails_model_validation(self):
        reviewer = self.create_user("reviewer")
        space = self.create_space()
        ReviewerSpaceScope.objects.create(reviewer=reviewer, space=space)

        duplicate = ReviewerSpaceScope(reviewer=reviewer, space=space, is_active=False)
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_same_reviewer_can_have_different_spaces(self):
        reviewer = self.create_user("reviewer")
        first = ReviewerSpaceScope.objects.create(reviewer=reviewer, space=self.create_space())
        second = ReviewerSpaceScope.objects.create(reviewer=reviewer, space=self.create_space())

        self.assertNotEqual(first.space_id, second.space_id)

    def test_different_reviewers_can_share_one_space(self):
        space = self.create_space()
        first = ReviewerSpaceScope.objects.create(
            reviewer=self.create_user("reviewer"), space=space
        )
        second = ReviewerSpaceScope.objects.create(
            reviewer=self.create_user("reviewer"), space=space
        )

        self.assertNotEqual(first.reviewer_id, second.reviewer_id)

    def test_reviewer_and_space_deletion_are_protected(self):
        reviewer = self.create_user("reviewer")
        space = self.create_space()
        ReviewerSpaceScope.objects.create(reviewer=reviewer, space=space)

        with self.assertRaises(ProtectedError):
            reviewer.delete()
        with self.assertRaises(ProtectedError):
            space.delete()

    def test_scope_creation_does_not_grant_role_or_permissions(self):
        reviewer = self.create_user("reviewer")
        ReviewerSpaceScope.objects.create(reviewer=reviewer, space=self.create_space())

        self.assertFalse(reviewer.groups.exists())
        self.assertFalse(reviewer.user_permissions.exists())

    def test_reviewer_role_does_not_create_scope(self):
        call_command("sync_system_roles", verbosity=0)
        reviewer = self.create_user("reviewer")
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        reviewer.groups.add(reviewer_group)

        self.assertFalse(ReviewerSpaceScope.objects.filter(reviewer=reviewer).exists())


class ArticleVersionReviewConstraintTests(ReviewFoundationFixtures, TestCase):
    def test_only_one_in_review_version_per_article(self):
        article = self.create_article()
        self.create_version(article, 1, VersionStatus.IN_REVIEW)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_version(article, 2, VersionStatus.IN_REVIEW)

    def test_different_articles_can_each_have_an_in_review_version(self):
        first = self.create_version(self.create_article(), 1, VersionStatus.IN_REVIEW)
        second = self.create_version(self.create_article(), 1, VersionStatus.IN_REVIEW)

        self.assertNotEqual(first.article_id, second.article_id)

    def test_existing_draft_and_published_uniqueness_remains(self):
        for status in (VersionStatus.DRAFT, VersionStatus.PUBLISHED):
            with self.subTest(status=status):
                article = self.create_article()
                self.create_version(article, 1, status)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.create_version(article, 2, status)

    def test_saved_rejected_and_superseded_are_not_limited_to_one(self):
        for status in (
            VersionStatus.SAVED,
            VersionStatus.REJECTED,
            VersionStatus.SUPERSEDED,
        ):
            with self.subTest(status=status):
                article = self.create_article()
                self.create_version(article, 1, status)
                second = self.create_version(article, 2, status)
                self.assertEqual(second.status, status)


class ContentReviewConstraintTests(ReviewFoundationFixtures, TestCase):
    def create_review(self, version, review_type=ReviewType.CONTENT_REVIEW):
        return ReviewRecord.objects.create(
            article_version=version,
            review_type=review_type,
            reviewer=self.create_user("reviewer"),
            decision=ReviewDecision.APPROVED,
        )

    def test_only_one_content_review_per_version(self):
        version = self.create_version(self.create_article(), 1, VersionStatus.DRAFT)
        self.create_review(version)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_review(version)

    def test_different_versions_can_each_have_content_review(self):
        article = self.create_article()
        first = self.create_version(article, 1, VersionStatus.SAVED)
        second = self.create_version(article, 2, VersionStatus.DRAFT)

        self.create_review(first)
        record = self.create_review(second)

        self.assertEqual(record.review_type, ReviewType.CONTENT_REVIEW)

    def test_periodic_and_emergency_reviews_are_not_limited_by_content_review(self):
        version = self.create_version(self.create_article(), 1, VersionStatus.DRAFT)
        self.create_review(version)

        for review_type in (ReviewType.PERIODIC_REVIEW, ReviewType.EMERGENCY_REVIEW):
            with self.subTest(review_type=review_type):
                first = self.create_review(version, review_type)
                second = self.create_review(version, review_type)
                self.assertNotEqual(first.pk, second.pk)


class ArticleVersionActionPermissionTests(TestCase):
    EXPECTED = {
        "submit_articleversion",
        "review_articleversion",
        "approve_articleversion",
        "reject_articleversion",
        "publish_articleversion",
    }

    def test_task13_permissions_are_generated_for_articleversion_content_type(self):
        actual = set(
            Permission.objects.filter(
                content_type__app_label="knowledge",
                content_type__model="articleversion",
                codename__in=self.EXPECTED,
            ).values_list("codename", flat=True)
        )

        self.assertEqual(actual, self.EXPECTED)


class ReviewFoundationMigrationTests(TransactionTestCase):
    """使用历史 App registry 验证 0005 与 0006 可安全往返。"""

    migrate_from = ("knowledge", "0005_seed_knowledge_number_counter")
    migrate_to = ("knowledge", "0006_task13_review_authorization_foundation")

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        self.old_apps = self.executor.loader.project_state([self.migrate_from]).apps

    def tearDown(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()

    def _create_legacy_review(self):
        User = self.old_apps.get_model("accounts", "User")
        KnowledgeSpace = self.old_apps.get_model("knowledge", "KnowledgeSpace")
        Category = self.old_apps.get_model("knowledge", "Category")
        Article = self.old_apps.get_model("knowledge", "Article")
        ArticleVersion = self.old_apps.get_model("knowledge", "ArticleVersion")
        ReviewRecord = self.old_apps.get_model("knowledge", "ReviewRecord")

        owner = User.objects.create(username="task13-migration-owner")
        reviewer = User.objects.create(username="task13-migration-reviewer")
        space = KnowledgeSpace.objects.create(
            code="task13-migration-space",
            name="Task 13 migration space",
            space_type="employee",
            owner=owner,
        )
        category = Category.objects.create(
            space=space,
            code="task13-migration-category",
            name="Task 13 migration category",
        )
        article = Article.objects.create(
            kb_no="KB-913002",
            title="Task 13 migration article",
            space=space,
            category=category,
            article_type="guide",
            owner=owner,
            created_by=owner,
            updated_by=owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )
        version = ArticleVersion.objects.create(
            article=article,
            version_no=1,
            status="in_review",
            title="Task 13 migration version",
            summary="Task 13 migration summary",
            change_summary="Task 13 migration baseline",
            created_by=owner,
            submitted_by=owner,
            submitted_at=timezone.now(),
        )
        review = ReviewRecord.objects.create(
            article_version=version,
            review_type="content_review",
            reviewer=reviewer,
            decision="approved",
        )
        return {
            "article_id": article.pk,
            "version_id": version.pk,
            "review_id": review.pk,
            "reviewer_id": reviewer.pk,
            "space_id": space.pk,
        }

    def _migrate(self, target):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([target])
        return self.executor.loader.project_state([target]).apps

    def _assert_legacy_records_preserved(self, apps, baseline):
        Article = apps.get_model("knowledge", "Article")
        ArticleVersion = apps.get_model("knowledge", "ArticleVersion")
        ReviewRecord = apps.get_model("knowledge", "ReviewRecord")

        self.assertTrue(Article.objects.filter(pk=baseline["article_id"]).exists())
        self.assertTrue(ArticleVersion.objects.filter(pk=baseline["version_id"]).exists())
        self.assertTrue(ReviewRecord.objects.filter(pk=baseline["review_id"]).exists())

    def test_forward_reverse_forward_preserves_existing_review_data(self):
        baseline = self._create_legacy_review()

        apps = self._migrate(self.migrate_to)
        ReviewerSpaceScope = apps.get_model("knowledge", "ReviewerSpaceScope")
        self._assert_legacy_records_preserved(apps, baseline)
        ReviewerSpaceScope.objects.create(
            reviewer_id=baseline["reviewer_id"],
            space_id=baseline["space_id"],
        )
        self.assertEqual(ReviewerSpaceScope.objects.count(), 1)

        apps = self._migrate(self.migrate_from)
        self._assert_legacy_records_preserved(apps, baseline)
        with self.assertRaises(LookupError):
            apps.get_model("knowledge", "ReviewerSpaceScope")

        apps = self._migrate(self.migrate_to)
        ReviewerSpaceScope = apps.get_model("knowledge", "ReviewerSpaceScope")
        self._assert_legacy_records_preserved(apps, baseline)
        self.assertEqual(ReviewerSpaceScope.objects.count(), 0)
