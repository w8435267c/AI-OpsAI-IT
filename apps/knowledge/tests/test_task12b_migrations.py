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
