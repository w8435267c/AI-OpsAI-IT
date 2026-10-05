"""Task 12B 迁移的前进、回滚与既有内容保留测试。"""

from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import IntegrityError
from django.test import TransactionTestCase
from django.utils import timezone


class KnowledgeNumberCounterMigrationTests(TransactionTestCase):
    """使用历史 App registry 验证 0003 -> 0005，不依赖当前模型。"""

    migrate_from = ("knowledge", "0003_space_audience_policy_comment")
    migrate_to = ("knowledge", "0005_seed_knowledge_number_counter")

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        self.old_apps = self.executor.loader.project_state([self.migrate_from]).apps

    def tearDown(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()

    def _create_legacy_article(self, kb_no, version_no=1):
        User = self.old_apps.get_model("accounts", "User")
        KnowledgeSpace = self.old_apps.get_model("knowledge", "KnowledgeSpace")
        Category = self.old_apps.get_model("knowledge", "Category")
        Article = self.old_apps.get_model("knowledge", "Article")
        ArticleVersion = self.old_apps.get_model("knowledge", "ArticleVersion")
        ReviewRecord = self.old_apps.get_model("knowledge", "ReviewRecord")

        suffix = kb_no[-6:]
        author = User.objects.create(username=f"author-{suffix}")
        reviewer = User.objects.create(username=f"reviewer-{suffix}")
        space = KnowledgeSpace.objects.create(
            code=f"legacy-{suffix}",
            name=f"Legacy {suffix}",
            space_type="employee",
            owner=author,
        )
        category = Category.objects.create(space=space, code=f"cat-{suffix}", name="Legacy")
        article = Article.objects.create(
            kb_no=kb_no,
            title=f"Legacy {suffix}",
            space=space,
            category=category,
            article_type="guide",
            owner=author,
            created_by=author,
            updated_by=author,
            review_due_at=timezone.now() + timedelta(days=180),
        )
        version = ArticleVersion.objects.create(
            article=article,
            version_no=version_no,
            status="draft",
            title="Legacy version",
            summary="Legacy summary",
            change_summary="Initial legacy content",
            created_by=author,
        )
        ReviewRecord.objects.create(
            article_version=version,
            reviewer=reviewer,
            decision="approved",
        )
        return article

    def _migrate_forward(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_to])
        return self.executor.loader.project_state([self.migrate_to]).apps

    def _create_pointer_roundtrip_fixture(self):
        """在 0003 历史模型中创建正式版、草稿和两个文章指针。"""
        User = self.old_apps.get_model("accounts", "User")
        KnowledgeSpace = self.old_apps.get_model("knowledge", "KnowledgeSpace")
        Category = self.old_apps.get_model("knowledge", "Category")
        Article = self.old_apps.get_model("knowledge", "Article")
        ArticleVersion = self.old_apps.get_model("knowledge", "ArticleVersion")

        owner = User.objects.create(username="roundtrip-owner")
        submitter = User.objects.create(username="roundtrip-submitter")
        space = KnowledgeSpace.objects.create(
            code="roundtrip-space",
            name="Roundtrip space",
            space_type="employee",
            owner=owner,
        )
        category = Category.objects.create(
            space=space,
            code="roundtrip-category",
            name="Roundtrip category",
        )
        article = Article.objects.create(
            kb_no="KB-123456",
            title="Task12B article",
            space=space,
            category=category,
            article_type="guide",
            owner=owner,
            created_by=owner,
            updated_by=owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )
        published_at = timezone.now()
        published = ArticleVersion.objects.create(
            article=article,
            version_no=1,
            status="published",
            title="Task12B Published Title",
            summary="Task12B Published Summary",
            body={"content": "Task12B Published Body"},
            body_plaintext="Task12B Published Body",
            change_summary="published baseline",
            created_by=owner,
            submitted_by=submitter,
            submitted_at=published_at,
            published_at=published_at,
        )
        draft = ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status="draft",
            title="Task12B Draft Title",
            summary="Task12B Draft Summary",
            body={"content": "Task12B Draft Body"},
            body_plaintext="Task12B Draft Body",
            change_summary="draft baseline",
            created_by=owner,
        )
        article.current_published_version = published
        article.latest_working_version = draft
        article.save(update_fields=["current_published_version", "latest_working_version"])
        article.refresh_from_db()
        self.assertEqual(article.current_published_version_id, published.pk)
        self.assertEqual(article.latest_working_version_id, draft.pk)

        return {
            "article_id": article.pk,
            "kb_no": article.kb_no,
            "published_id": published.pk,
            "draft_id": draft.pk,
            "published": {
                "article_id": article.pk,
                "version_no": published.version_no,
                "status": published.status,
                "title": published.title,
                "summary": published.summary,
                "body": published.body,
                "body_plaintext": published.body_plaintext,
                "change_summary": published.change_summary,
                "published_at": published.published_at,
            },
            "draft": {
                "article_id": article.pk,
                "version_no": draft.version_no,
                "status": draft.status,
                "title": draft.title,
                "summary": draft.summary,
                "body": draft.body,
                "body_plaintext": draft.body_plaintext,
                "change_summary": draft.change_summary,
            },
        }

    def _assert_pointer_roundtrip_fixture(self, apps, baseline):
        Article = apps.get_model("knowledge", "Article")
        ArticleVersion = apps.get_model("knowledge", "ArticleVersion")

        article = Article.objects.get(pk=baseline["article_id"])
        published = ArticleVersion.objects.get(pk=baseline["published_id"])
        draft = ArticleVersion.objects.get(pk=baseline["draft_id"])

        self.assertEqual(article.kb_no, baseline["kb_no"])
        self.assertEqual(article.current_published_version_id, baseline["published_id"])
        self.assertEqual(article.latest_working_version_id, baseline["draft_id"])
        for field, value in baseline["published"].items():
            self.assertEqual(getattr(published, field), value)
        for field, value in baseline["draft"].items():
            self.assertEqual(getattr(draft, field), value)

    def test_empty_database_seeds_one(self):
        apps = self._migrate_forward()
        Counter = apps.get_model("knowledge", "KnowledgeNumberCounter")
        counter = Counter.objects.get(id=1)
        self.assertEqual(counter.next_value, 1)

    def test_valid_legacy_numbers_seed_maximum_plus_one_and_preserve_records(self):
        first = self._create_legacy_article("KB-000001")
        self._create_legacy_article("KB-000010", version_no=1)
        last = self._create_legacy_article("KB-123456", version_no=1)

        apps = self._migrate_forward()
        Counter = apps.get_model("knowledge", "KnowledgeNumberCounter")
        Article = apps.get_model("knowledge", "Article")
        ArticleVersion = apps.get_model("knowledge", "ArticleVersion")
        ReviewRecord = apps.get_model("knowledge", "ReviewRecord")

        self.assertEqual(Counter.objects.get(id=1).next_value, 123_457)
        self.assertEqual(Article.objects.filter(pk__in=(first.pk, last.pk)).count(), 2)
        self.assertEqual(ArticleVersion.objects.filter(article_id=first.pk).count(), 1)
        self.assertEqual(
            ReviewRecord.objects.filter(article_version__article_id=last.pk).count(), 1
        )

    def test_backward_removes_counter_and_preserves_legacy_records(self):
        article = self._create_legacy_article("KB-000123")
        self._migrate_forward()

        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        apps = self.executor.loader.project_state([self.migrate_from]).apps
        Article = apps.get_model("knowledge", "Article")
        ArticleVersion = apps.get_model("knowledge", "ArticleVersion")
        ReviewRecord = apps.get_model("knowledge", "ReviewRecord")

        self.assertTrue(Article.objects.filter(pk=article.pk, kb_no="KB-000123").exists())
        self.assertEqual(ArticleVersion.objects.filter(article_id=article.pk).count(), 1)
        self.assertEqual(
            ReviewRecord.objects.filter(article_version__article_id=article.pk).count(), 1
        )

    def test_maximum_legacy_number_seeds_one_million(self):
        self._create_legacy_article("KB-999999")

        apps = self._migrate_forward()
        Counter = apps.get_model("knowledge", "KnowledgeNumberCounter")

        self.assertEqual(Counter.objects.get(id=1).next_value, 1_000_000)

    def test_task12b_full_roundtrip_preserves_article_version_pointers_and_published_content(
        self,
    ):
        baseline = self._create_pointer_roundtrip_fixture()
        migration_0004 = ("knowledge", "0004_task12_authoring_schema")

        self.executor = MigrationExecutor(connection)
        self.executor.migrate([migration_0004])

        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_to])
        apps = self.executor.loader.project_state([self.migrate_to]).apps
        Counter = apps.get_model("knowledge", "KnowledgeNumberCounter")
        self._assert_pointer_roundtrip_fixture(apps, baseline)
        self.assertEqual(Counter.objects.get(id=1).next_value, 123_457)

        self.executor = MigrationExecutor(connection)
        self.executor.migrate([migration_0004])
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        apps = self.executor.loader.project_state([self.migrate_from]).apps
        self._assert_pointer_roundtrip_fixture(apps, baseline)


class InvalidLegacyKbNoMigrationTests(TransactionTestCase):
    """0002 已阻止非法遗留编号，因此 0005 不会静默跳过该类脏数据。"""

    migrate_from = ("knowledge", "0001_initial")
    format_constraint_migration = ("knowledge", "0002_alter_article_kb_no_and_more")

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        self.old_apps = self.executor.loader.project_state([self.migrate_from]).apps

    def tearDown(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_invalid_legacy_value_is_unrepresentable_after_0002(self):
        User = self.old_apps.get_model("accounts", "User")
        KnowledgeSpace = self.old_apps.get_model("knowledge", "KnowledgeSpace")
        Category = self.old_apps.get_model("knowledge", "Category")
        Article = self.old_apps.get_model("knowledge", "Article")

        user = User.objects.create(username="invalid-legacy-author")
        space = KnowledgeSpace.objects.create(
            code="invalid-legacy",
            name="Invalid legacy",
            space_type="employee",
            owner=user,
        )
        category = Category.objects.create(space=space, code="invalid", name="Invalid")
        invalid_article = Article.objects.create(
            kb_no="INVALID",
            title="Invalid legacy",
            space=space,
            category=category,
            article_type="guide",
            owner=user,
            created_by=user,
            updated_by=user,
            review_due_at=timezone.now() + timedelta(days=180),
        )

        self.executor = MigrationExecutor(connection)
        try:
            with self.assertRaises(IntegrityError):
                self.executor.migrate([self.format_constraint_migration])
        finally:
            # 失败迁移不会清理 0001 中人为构造的非法行；删除它以便恢复测试库。
            Article.objects.filter(pk=invalid_article.pk).delete()
