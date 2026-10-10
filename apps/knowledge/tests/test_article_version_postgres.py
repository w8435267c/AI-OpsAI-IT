"""Task 12D-06：仅在 PostgreSQL 上验证版本写入的真实并发语义。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier, Event
from time import monotonic
from unittest import skipUnless

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import close_old_connections, connection, connections, transaction
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
    KnowledgeSpace,
    ReviewRecord,
    VersionStatus,
)
from apps.knowledge.readers import employee_visible_articles, get_employee_article_detail
from apps.knowledge.services import (
    DRAFT_CONFLICT,
    DRAFT_NOT_CURRENT,
    ArticleVersionWriteError,
    autosave_draft,
    manual_save_draft,
    restore_article_version,
)
from apps.search.readers import search_employee_articles


@skipUnless(connection.vendor == "postgresql", "仅在 PostgreSQL 上验证真实并发语义。")
class ArticleVersionPostgreSQLConcurrencyTests(TransactionTestCase):
    """使用独立线程连接验证 CAS、行锁、版本分配和事务不变量。"""

    databases = {"default"}
    version_snapshot_fields = (
        "id",
        "article_id",
        "version_no",
        "status",
        "lock_version",
        "title",
        "summary",
        "applicable_scope",
        "body",
        "body_plaintext",
        "change_summary",
        "restored_from_version_id",
        "created_by_id",
        "submitted_by_id",
        "submitted_at",
        "published_at",
        "created_at",
        "updated_at",
    )

    def setUp(self):
        super().setUp()
        call_command("sync_system_roles", verbosity=0, stdout=StringIO())
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        self.editor = User.objects.create_user(username="task12d06-pg-editor")
        self.editor.groups.add(editor_group)
        self.employee = User.objects.create_user(username="task12d06-pg-employee")
        self.space = KnowledgeSpace.objects.create(
            code="task12d06-pg-space",
            name="Task 12D-06 PostgreSQL 空间",
            space_type="employee",
            owner=self.editor,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        self.category = Category.objects.create(
            space=self.space,
            code="task12d06-pg-category",
            name="Task 12D-06 PostgreSQL 分类",
        )

    def _create_article(self, suffix):
        return Article.objects.create(
            kb_no=f"KB-{suffix}",
            title=f"Task 12D-06 {suffix}",
            space=self.space,
            category=self.category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            owner=self.editor,
            created_by=self.editor,
            updated_by=self.editor,
            review_due_at=timezone.now() + timedelta(days=180),
        )

    def _create_version(
        self,
        *,
        article,
        version_no,
        status,
        marker,
        lock_version=1,
        restored_from=None,
    ):
        submitted_fields = {}
        if status not in (VersionStatus.DRAFT, VersionStatus.SAVED):
            submitted_fields = {
                "submitted_by": self.editor,
                "submitted_at": timezone.now(),
            }
        if status == VersionStatus.PUBLISHED:
            submitted_fields["published_at"] = timezone.now()
        return ArticleVersion.objects.create(
            article=article,
            version_no=version_no,
            status=status,
            lock_version=lock_version,
            title=f"{marker} 标题",
            summary=f"{marker} 摘要",
            applicable_scope={"marker": marker},
            body={"format": "opsai.plaintext/1", "text": f"{marker} 正文"},
            body_plaintext=f"{marker} 正文",
            change_summary=f"{marker} 说明",
            restored_from_version=restored_from,
            created_by=self.editor,
            **submitted_fields,
        )

    def _set_pointers(self, article, *, draft, published=None):
        Article.objects.filter(pk=article.pk).update(
            latest_working_version=draft,
            current_published_version=published,
        )
        article.refresh_from_db()

    def _version_snapshot(self, version_id):
        return ArticleVersion.objects.values(*self.version_snapshot_fields).get(pk=version_id)

    def _operation_kwargs(self, *, actor, article, draft_id, expected_lock_version, marker):
        return {
            "actor": actor,
            "article": article,
            "draft_id": draft_id,
            "expected_lock_version": expected_lock_version,
            "title": f"{marker} 标题",
            "summary": f"{marker} 摘要",
            "applicable_scope": {"worker": marker},
            "body_text": f"{marker} 正文",
            "change_summary": f"{marker} 说明",
        }

    def _run_operation(
        self,
        operation,
        *,
        article_id,
        draft_id,
        expected_lock_version,
        marker,
        barrier,
        source_id=None,
        connection_ready=None,
        backend_pids=None,
    ):
        close_old_connections()
        thread_connection = connections["default"]
        try:
            thread_connection.ensure_connection()
            if backend_pids is not None:
                backend_pids.append(thread_connection.connection.info.backend_pid)
            actor = User.objects.get(pk=self.editor.pk)
            article = Article.objects.get(pk=article_id)
            ArticleVersion.objects.get(pk=draft_id, article_id=article_id)
            if source_id is not None:
                ArticleVersion.objects.get(pk=source_id, article_id=article_id)
            if connection_ready is not None:
                connection_ready.set()
            barrier.wait(timeout=10)

            if operation == "autosave":
                result = autosave_draft(
                    **self._operation_kwargs(
                        actor=actor,
                        article=article,
                        draft_id=draft_id,
                        expected_lock_version=expected_lock_version,
                        marker=marker,
                    )
                )
                return ("success", operation, result.pk, marker, None)
            if operation == "manual":
                _saved, result = manual_save_draft(
                    **self._operation_kwargs(
                        actor=actor,
                        article=article,
                        draft_id=draft_id,
                        expected_lock_version=expected_lock_version,
                        marker=marker,
                    )
                )
                return ("success", operation, result.pk, marker, None)
            if operation == "restore":
                result = restore_article_version(
                    actor=actor,
                    article=article,
                    source_version_id=source_id,
                    draft_id=draft_id,
                    expected_lock_version=expected_lock_version,
                    current_title=f"{marker} 当前标题",
                    current_summary=f"{marker} 当前摘要",
                    current_applicable_scope={"worker": marker},
                    current_body_text=f"{marker} 当前正文",
                    current_change_summary=f"{marker} 当前说明",
                )
                return ("success", operation, result.pk, marker, source_id)
            raise AssertionError(f"未知操作：{operation}")
        except ArticleVersionWriteError as exc:
            return ("error", operation, exc.code, exc.public_message, source_id)
        finally:
            close_old_connections()
            thread_connection.close()

    def _race(self, workers, *, barrier=None, ready_events=None, backend_pids=None):
        barrier = barrier or Barrier(len(workers))
        ready_events = ready_events or [None] * len(workers)
        with ThreadPoolExecutor(max_workers=len(workers)) as executor:
            futures = [
                executor.submit(
                    self._run_operation,
                    worker["operation"],
                    article_id=worker["article_id"],
                    draft_id=worker["draft_id"],
                    expected_lock_version=worker["expected_lock_version"],
                    marker=worker["marker"],
                    barrier=barrier,
                    source_id=worker.get("source_id"),
                    connection_ready=ready_events[index],
                    backend_pids=backend_pids,
                )
                for index, worker in enumerate(workers)
            ]
            return [future.result(timeout=20) for future in futures]

    def _assert_one_success(self, results, *, allowed_error_codes):
        successes = [result for result in results if result[0] == "success"]
        errors = [result for result in results if result[0] == "error"]
        self.assertEqual(len(successes), 1, results)
        self.assertEqual(len(errors), 1, results)
        self.assertIn(errors[0][2], allowed_error_codes)
        public_message = errors[0][3].lower()
        for secret_detail in ("postgres", "sql", "constraint", "dsn", "password"):
            self.assertNotIn(secret_detail, public_message)
        return successes[0], errors[0]

    def _assert_global_invariants(self, article_id, *, expected_review_count=0):
        article = Article.objects.select_related(
            "latest_working_version", "current_published_version"
        ).get(pk=article_id)
        versions = list(
            ArticleVersion.objects.filter(article_id=article_id)
            .select_related("restored_from_version")
            .order_by("version_no")
        )
        version_numbers = [version.version_no for version in versions]
        self.assertTrue(all(isinstance(number, int) and number > 0 for number in version_numbers))
        self.assertEqual(len(version_numbers), len(set(version_numbers)))
        self.assertEqual({version.article_id for version in versions}, {article.pk})

        drafts = [version for version in versions if version.status == VersionStatus.DRAFT]
        self.assertLessEqual(len(drafts), 1)
        if article.latest_working_version_id is None:
            self.assertEqual(drafts, [])
        else:
            self.assertEqual(len(drafts), 1)
            self.assertEqual(article.latest_working_version_id, drafts[0].pk)
            self.assertEqual(article.latest_working_version.article_id, article.pk)

        if article.current_published_version_id is not None:
            self.assertEqual(article.current_published_version.article_id, article.pk)
            self.assertEqual(article.current_published_version.status, VersionStatus.PUBLISHED)

        for version in versions:
            if version.restored_from_version_id is not None:
                self.assertEqual(version.restored_from_version.article_id, article.pk)
            if version.status == VersionStatus.SAVED:
                self.assertNotEqual(version.pk, article.latest_working_version_id)
        self.assertEqual(
            ReviewRecord.objects.filter(article_version__article_id=article_id).count(),
            expected_review_count,
        )
        return article, versions

    def _assert_employee_reads_published_only(self, article_id, *, work_markers):
        article = Article.objects.get(pk=article_id)
        self.assertTrue(employee_visible_articles(self.employee).filter(pk=article_id).exists())
        detail = get_employee_article_detail(self.employee, article.kb_no)
        self.assertIsNotNone(detail)
        self.assertEqual(detail.body_text, "正式发布唯一关键词 正文")
        self.assertTrue(
            search_employee_articles(self.employee, "正式发布唯一关键词")
            .filter(pk=article_id)
            .exists()
        )
        for marker in work_markers:
            self.assertFalse(
                search_employee_articles(self.employee, marker).filter(pk=article_id).exists()
            )

    def _hold_article_lock(self, article_id, lock_acquired, release_lock):
        close_old_connections()
        thread_connection = connections["default"]
        try:
            with transaction.atomic():
                Article.objects.select_for_update().get(pk=article_id)
                lock_acquired.set()
                if not release_lock.wait(timeout=10):
                    raise TimeoutError("等待释放 PostgreSQL Article 行锁超时。")
        finally:
            close_old_connections()
            thread_connection.close()

    def _wait_for_any_database_lock(self, backend_pids, *, timeout=5):
        deadline = monotonic() + timeout
        pause = Event()
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pid, wait_event_type, wait_event "
                    "FROM pg_stat_activity WHERE pid = ANY(%s)",
                    [backend_pids],
                )
                rows = cursor.fetchall()
            lock_rows = [row for row in rows if row[1] == "Lock"]
            if lock_rows:
                return lock_rows
            pause.wait(timeout=0.05)
        return []

    def test_two_autosaves_with_same_token_have_one_winner(self):
        article = self._create_article("120601")
        draft = self._create_version(
            article=article,
            version_no=1,
            status=VersionStatus.DRAFT,
            marker="autosave-base",
            lock_version=5,
        )
        self._set_pointers(article, draft=draft)
        version_count = ArticleVersion.objects.filter(article=article).count()

        results = self._race(
            [
                {
                    "operation": "autosave",
                    "article_id": article.pk,
                    "draft_id": draft.pk,
                    "expected_lock_version": 5,
                    "marker": marker,
                }
                for marker in ("autosave-A", "autosave-B")
            ]
        )
        success, _error = self._assert_one_success(
            results,
            allowed_error_codes={DRAFT_CONFLICT},
        )

        draft.refresh_from_db()
        article.refresh_from_db()
        self.assertEqual(draft.lock_version, 6)
        self.assertEqual(draft.title, f"{success[3]} 标题")
        self.assertEqual(draft.body_plaintext, f"{success[3]} 正文")
        self.assertEqual(ArticleVersion.objects.filter(article=article).count(), version_count)
        self.assertEqual(article.latest_working_version_id, draft.pk)
        self.assertIsNone(article.current_published_version_id)
        self._assert_global_invariants(article.pk)

    def test_autosave_and_manual_save_have_one_business_winner(self):
        article = self._create_article("120602")
        published = self._create_version(
            article=article,
            version_no=1,
            status=VersionStatus.PUBLISHED,
            marker="正式发布唯一关键词",
        )
        draft = self._create_version(
            article=article,
            version_no=2,
            status=VersionStatus.DRAFT,
            marker="mixed-base",
            lock_version=5,
        )
        self._set_pointers(article, draft=draft, published=published)
        published_id = article.current_published_version_id

        results = self._race(
            [
                {
                    "operation": "autosave",
                    "article_id": article.pk,
                    "draft_id": draft.pk,
                    "expected_lock_version": 5,
                    "marker": "mixed-autosave",
                },
                {
                    "operation": "manual",
                    "article_id": article.pk,
                    "draft_id": draft.pk,
                    "expected_lock_version": 5,
                    "marker": "mixed-manual",
                },
            ]
        )
        success, error = self._assert_one_success(
            results,
            allowed_error_codes={DRAFT_CONFLICT, DRAFT_NOT_CURRENT},
        )

        draft.refresh_from_db()
        article, versions = self._assert_global_invariants(article.pk)
        self.assertEqual(article.current_published_version_id, published_id)
        if success[1] == "autosave":
            self.assertEqual(error[1], "manual")
            self.assertEqual(draft.status, VersionStatus.DRAFT)
            self.assertEqual(draft.lock_version, 6)
            self.assertEqual(len(versions), 2)
        else:
            self.assertEqual(error[1], "autosave")
            self.assertEqual(draft.status, VersionStatus.SAVED)
            self.assertEqual(len(versions), 3)
        self._assert_employee_reads_published_only(
            article.pk,
            work_markers=("mixed-autosave", "mixed-manual"),
        )

    def test_two_manual_saves_serialize_and_allocate_article_max_plus_one(self):
        article = self._create_article("120603")
        draft = self._create_version(
            article=article,
            version_no=5,
            status=VersionStatus.DRAFT,
            marker="manual-base",
            lock_version=3,
        )
        published = self._create_version(
            article=article,
            version_no=10,
            status=VersionStatus.PUBLISHED,
            marker="正式发布唯一关键词",
        )
        self._set_pointers(article, draft=draft, published=published)
        initial_numbers = set(
            ArticleVersion.objects.filter(article=article).values_list("version_no", flat=True)
        )
        lock_acquired = Event()
        release_lock = Event()
        ready_events = [Event(), Event()]
        backend_pids = []
        barrier = Barrier(2)
        workers = [
            {
                "operation": "manual",
                "article_id": article.pk,
                "draft_id": draft.pk,
                "expected_lock_version": 3,
                "marker": marker,
            }
            for marker in ("manual-A", "manual-B")
        ]

        with ThreadPoolExecutor(max_workers=3) as executor:
            lock_future = executor.submit(
                self._hold_article_lock,
                article.pk,
                lock_acquired,
                release_lock,
            )
            self.assertTrue(lock_acquired.wait(timeout=5))
            futures = [
                executor.submit(
                    self._run_operation,
                    worker["operation"],
                    article_id=worker["article_id"],
                    draft_id=worker["draft_id"],
                    expected_lock_version=worker["expected_lock_version"],
                    marker=worker["marker"],
                    barrier=barrier,
                    connection_ready=ready_events[index],
                    backend_pids=backend_pids,
                )
                for index, worker in enumerate(workers)
            ]
            try:
                self.assertTrue(all(event.wait(timeout=5) for event in ready_events))
                lock_rows = self._wait_for_any_database_lock(backend_pids)
                self.assertTrue(lock_rows, "未观察到 PostgreSQL Lock wait。")
            finally:
                release_lock.set()
            results = [future.result(timeout=20) for future in futures]
            lock_future.result(timeout=10)

        self._assert_one_success(
            results,
            allowed_error_codes={DRAFT_CONFLICT, DRAFT_NOT_CURRENT},
        )
        draft.refresh_from_db()
        article, versions = self._assert_global_invariants(article.pk)
        final_numbers = {version.version_no for version in versions}
        self.assertEqual(initial_numbers, {5, 10})
        self.assertEqual(final_numbers, {5, 10, 11})
        self.assertEqual(draft.status, VersionStatus.SAVED)
        self.assertEqual(article.latest_working_version.version_no, 11)
        self.assertEqual(article.current_published_version_id, published.pk)

    def test_manual_save_and_restore_have_one_winner_and_preserve_source(self):
        article = self._create_article("120604")
        published = self._create_version(
            article=article,
            version_no=1,
            status=VersionStatus.PUBLISHED,
            marker="正式发布唯一关键词",
        )
        source = self._create_version(
            article=article,
            version_no=4,
            status=VersionStatus.SAVED,
            marker="restore-source",
        )
        draft = self._create_version(
            article=article,
            version_no=7,
            status=VersionStatus.DRAFT,
            marker="manual-restore-base",
            lock_version=2,
        )
        self._set_pointers(article, draft=draft, published=published)
        source_before = self._version_snapshot(source.pk)

        results = self._race(
            [
                {
                    "operation": "manual",
                    "article_id": article.pk,
                    "draft_id": draft.pk,
                    "expected_lock_version": 2,
                    "marker": "manual-restore-manual",
                },
                {
                    "operation": "restore",
                    "article_id": article.pk,
                    "draft_id": draft.pk,
                    "expected_lock_version": 2,
                    "marker": "manual-restore-restore",
                    "source_id": source.pk,
                },
            ]
        )
        success, _error = self._assert_one_success(
            results,
            allowed_error_codes={DRAFT_CONFLICT, DRAFT_NOT_CURRENT},
        )

        article, versions = self._assert_global_invariants(article.pk)
        self.assertEqual(len(versions), 4)
        self.assertEqual(article.latest_working_version.version_no, 8)
        self.assertEqual(article.current_published_version_id, published.pk)
        expected_source = source.pk if success[1] == "restore" else None
        self.assertEqual(article.latest_working_version.restored_from_version_id, expected_source)
        self.assertEqual(self._version_snapshot(source.pk), source_before)
        self._assert_employee_reads_published_only(
            article.pk,
            work_markers=("restore-source", "manual-restore"),
        )

    def test_two_restores_have_one_winner_and_keep_both_sources_immutable(self):
        article = self._create_article("120605")
        published = self._create_version(
            article=article,
            version_no=1,
            status=VersionStatus.PUBLISHED,
            marker="正式发布唯一关键词",
        )
        source_a = self._create_version(
            article=article,
            version_no=2,
            status=VersionStatus.SAVED,
            marker="restore-source-A",
        )
        source_b = self._create_version(
            article=article,
            version_no=3,
            status=VersionStatus.SAVED,
            marker="restore-source-B",
        )
        draft = self._create_version(
            article=article,
            version_no=4,
            status=VersionStatus.DRAFT,
            marker="restore-race-base",
            lock_version=5,
        )
        self._set_pointers(article, draft=draft, published=published)
        sources_before = {
            source_a.pk: self._version_snapshot(source_a.pk),
            source_b.pk: self._version_snapshot(source_b.pk),
        }

        results = self._race(
            [
                {
                    "operation": "restore",
                    "article_id": article.pk,
                    "draft_id": draft.pk,
                    "expected_lock_version": 5,
                    "marker": "restore-A",
                    "source_id": source_a.pk,
                },
                {
                    "operation": "restore",
                    "article_id": article.pk,
                    "draft_id": draft.pk,
                    "expected_lock_version": 5,
                    "marker": "restore-B",
                    "source_id": source_b.pk,
                },
            ]
        )
        success, _error = self._assert_one_success(
            results,
            allowed_error_codes={DRAFT_CONFLICT, DRAFT_NOT_CURRENT},
        )

        article, versions = self._assert_global_invariants(article.pk)
        self.assertEqual(len(versions), 5)
        self.assertEqual(article.latest_working_version.version_no, 5)
        self.assertEqual(article.latest_working_version.restored_from_version_id, success[4])
        self.assertEqual(article.current_published_version_id, published.pk)
        self.assertEqual(self._version_snapshot(source_a.pk), sources_before[source_a.pk])
        self.assertEqual(self._version_snapshot(source_b.pk), sources_before[source_b.pk])
        self._assert_employee_reads_published_only(
            article.pk,
            work_markers=("restore-source-A", "restore-source-B", "restore-race-base"),
        )
