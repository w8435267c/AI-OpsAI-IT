"""Task 12C：仅在 PostgreSQL 上验证 Article 创建的锁与事务语义。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier, Event
from time import monotonic
from unittest import mock, skipUnless

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import DatabaseError, close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import ROLE_EDITOR, SYSTEM_ROLE_BY_CODE
from apps.knowledge.models import (
    Article,
    ArticleType,
    ArticleVersion,
    AudiencePolicy,
    Category,
    KnowledgeNumberCounter,
    KnowledgeSpace,
    VersionStatus,
)
from apps.knowledge.services import ArticleCreationError, create_article


@skipUnless(connection.vendor == "postgresql", "仅在 PostgreSQL 上验证真实锁语义。")
class ArticleCreationPostgreSQLTests(TransactionTestCase):
    """使用独立线程连接验证数据库行锁、并发编号和原子回滚。"""

    databases = {"default"}

    def setUp(self):
        super().setUp()
        call_command("sync_system_roles", verbosity=0, stdout=StringIO())
        KnowledgeNumberCounter.objects.update_or_create(pk=1, defaults={"next_value": 1})

        self.editor = User.objects.create_user(username="task12c-pg-editor")
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        self.editor.groups.add(editor_group)
        self.space = KnowledgeSpace.objects.create(
            code="task12c-pg-space",
            name="Task 12C PostgreSQL 空间",
            space_type="employee",
            owner=self.editor,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        self.category = Category.objects.create(
            space=self.space,
            code="task12c-pg-category",
            name="Task 12C PostgreSQL 分类",
        )

    def _create_kwargs(self, *, actor, space, category, index):
        return {
            "actor": actor,
            "space": space,
            "category": category,
            "article_type": ArticleType.GUIDE,
            "title": f"PostgreSQL 并发创建 {index}",
            "summary": f"Task 12C PostgreSQL 并发摘要 {index}",
            "applicable_scope": {"worker": index},
            "body_text": f"Task 12C PostgreSQL 并发正文 {index}",
            "change_summary": "创建初始草稿",
            "review_due_at": timezone.now() + timedelta(days=180),
        }

    def _create_in_independent_connection(
        self,
        index,
        *,
        barrier=None,
        connection_ready=None,
        backend_pids=None,
        completed=None,
    ):
        close_old_connections()
        thread_connection = connections["default"]
        try:
            thread_connection.ensure_connection()
            if backend_pids is not None:
                backend_pids.append(thread_connection.connection.info.backend_pid)
            if connection_ready is not None:
                connection_ready.set()

            actor = User.objects.get(pk=self.editor.pk)
            space = KnowledgeSpace.objects.get(pk=self.space.pk)
            category = Category.objects.get(pk=self.category.pk)
            if barrier is not None:
                barrier.wait(timeout=10)
            article, draft = create_article(
                **self._create_kwargs(
                    actor=actor,
                    space=space,
                    category=category,
                    index=index,
                )
            )
            return article.kb_no, article.pk, draft.pk
        finally:
            if completed is not None:
                completed.set()
            close_old_connections()
            thread_connection.close()

    def _hold_counter_lock(self, lock_acquired, release_lock):
        close_old_connections()
        thread_connection = connections["default"]
        try:
            with transaction.atomic():
                KnowledgeNumberCounter.objects.select_for_update().get(pk=1)
                lock_acquired.set()
                if not release_lock.wait(timeout=10):
                    raise TimeoutError("等待释放 PostgreSQL Counter 行锁超时。")
        finally:
            close_old_connections()
            thread_connection.close()

    def _wait_for_database_lock(self, backend_pid, *, timeout=5):
        deadline = monotonic() + timeout
        pause = Event()
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT wait_event_type, wait_event FROM pg_stat_activity WHERE pid = %s",
                    [backend_pid],
                )
                row = cursor.fetchone()
            if row and row[0] == "Lock":
                return row
            pause.wait(timeout=0.05)
        return None

    def _assert_complete_articles(self, expected_count):
        articles = list(Article.objects.prefetch_related("versions"))
        self.assertEqual(len(articles), expected_count)
        pointer_errors = 0
        for article in articles:
            versions = list(article.versions.all())
            if (
                len(versions) != 1
                or article.latest_working_version_id != versions[0].pk
                or versions[0].status != VersionStatus.DRAFT
                or article.current_published_version_id is not None
            ):
                pointer_errors += 1
        self.assertEqual(pointer_errors, 0)
        self.assertEqual(ArticleVersion.objects.count(), expected_count)

    def test_select_for_update_really_blocks_until_counter_lock_is_released(self):
        lock_acquired = Event()
        release_lock = Event()
        creator_ready = Event()
        creator_completed = Event()
        creator_pids = []

        with ThreadPoolExecutor(max_workers=2) as executor:
            lock_future = executor.submit(
                self._hold_counter_lock,
                lock_acquired,
                release_lock,
            )
            self.assertTrue(lock_acquired.wait(timeout=5))
            creator_future = executor.submit(
                self._create_in_independent_connection,
                1,
                connection_ready=creator_ready,
                backend_pids=creator_pids,
                completed=creator_completed,
            )
            try:
                self.assertTrue(creator_ready.wait(timeout=5))
                wait_state = self._wait_for_database_lock(creator_pids[0])
                self.assertIsNotNone(wait_state)
                self.assertFalse(creator_completed.is_set())
            finally:
                release_lock.set()

            kb_no, _article_id, _draft_id = creator_future.result(timeout=10)
            lock_future.result(timeout=10)

        self.assertEqual(kb_no, "KB-000001")
        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, 2)
        self._assert_complete_articles(1)

    def test_two_concurrent_creations_allocate_two_unique_consecutive_numbers(self):
        KnowledgeNumberCounter.objects.filter(pk=1).update(next_value=100)
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    self._create_in_independent_connection,
                    index,
                    barrier=barrier,
                )
                for index in range(2)
            ]
            results = [future.result(timeout=15) for future in futures]

        self.assertEqual({result[0] for result in results}, {"KB-000100", "KB-000101"})
        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, 102)
        self._assert_complete_articles(2)

    def test_twenty_concurrent_creations_have_no_duplicates_or_partial_rows(self):
        KnowledgeNumberCounter.objects.filter(pk=1).update(next_value=200)
        worker_count = 20
        barrier = Barrier(worker_count)

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(
                    self._create_in_independent_connection,
                    index,
                    barrier=barrier,
                )
                for index in range(worker_count)
            ]
            results = [future.result(timeout=30) for future in futures]

        kb_numbers = {result[0] for result in results}
        expected_numbers = {f"KB-{number:06d}" for number in range(200, 220)}
        self.assertEqual(kb_numbers, expected_numbers)
        self.assertEqual(len(kb_numbers), worker_count)
        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, 220)
        self._assert_complete_articles(worker_count)

    def test_draft_failure_rolls_back_article_counter_and_allows_number_reuse(self):
        KnowledgeNumberCounter.objects.filter(pk=1).update(next_value=300)

        with mock.patch.object(
            ArticleVersion,
            "save",
            side_effect=DatabaseError("injected PostgreSQL draft failure"),
        ):
            with self.assertRaises(ArticleCreationError) as caught:
                create_article(
                    **self._create_kwargs(
                        actor=self.editor,
                        space=self.space,
                        category=self.category,
                        index="rollback",
                    )
                )

        self.assertEqual(caught.exception.code, "DATABASE_WRITE_FAILED")
        self.assertEqual(Article.objects.count(), 0)
        self.assertEqual(ArticleVersion.objects.count(), 0)
        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, 300)

        article, draft = create_article(
            **self._create_kwargs(
                actor=self.editor,
                space=self.space,
                category=self.category,
                index="recovery",
            )
        )

        self.assertEqual(article.kb_no, "KB-000300")
        self.assertEqual(draft.article_id, article.pk)
        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, 301)
        self._assert_complete_articles(1)
