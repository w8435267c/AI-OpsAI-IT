"""Task 13-07: real PostgreSQL concurrency and transaction-safety tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier, Event
from time import monotonic
from unittest import mock, skipUnless

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import (
    DatabaseError,
    IntegrityError,
    close_old_connections,
    connection,
    connections,
    transaction,
)
from django.test import TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import ROLE_EDITOR, ROLE_REVIEWER, SYSTEM_ROLE_BY_CODE
from apps.audit.models import AuditEvent, AuditEventType
from apps.knowledge.models import (
    Article,
    ArticleType,
    ArticleVersion,
    AudiencePolicy,
    Category,
    KnowledgeSpace,
    ReviewDecision,
    ReviewerSpaceScope,
    ReviewRecord,
    ReviewType,
    VersionStatus,
)
from apps.knowledge.readers import get_employee_article_detail
from apps.knowledge.services import (
    DATABASE_WRITE_FAILED,
    INVALID_DRAFT_STATE,
    ArticleVersionWriteError,
    autosave_draft,
)
from apps.knowledge.services import (
    DRAFT_CONFLICT as WRITE_DRAFT_CONFLICT,
)
from apps.knowledge.services import (
    DRAFT_NOT_CURRENT as WRITE_DRAFT_NOT_CURRENT,
)
from apps.search.readers import search_employee_articles
from apps.workflow.models import (
    IdempotencyOperation,
    IdempotencyStatus,
    WorkflowEventType,
    WorkflowIdempotencyRecord,
    WorkflowOutboxEvent,
)
from apps.workflow.services import (
    DRAFT_CONFLICT,
    DRAFT_NOT_CURRENT,
    IDEMPOTENCY_CONFLICT,
    SELF_REVIEW_FORBIDDEN,
    VERSION_NOT_FOUND_OR_INACCESSIBLE,
    VERSION_NOT_IN_REVIEW,
    WORKFLOW_UNAVAILABLE,
    ApprovePublishArticleVersionError,
    RejectArticleVersionError,
    SubmitArticleForReviewError,
    approve_and_publish_article_version,
    reject_article_version,
    submit_article_for_review,
)


@skipUnless(connection.vendor == "postgresql", "Task13-07 requires PostgreSQL.")
class ReviewWorkflowPostgreSQLConcurrencyTests(TransactionTestCase):
    """Exercise the real services with independent PostgreSQL transactions."""

    databases = {"default"}
    race_rounds = 3

    def setUp(self):
        super().setUp()
        call_command("sync_system_roles", verbosity=0, stdout=StringIO())
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)

        self.creator = User.objects.create_user(username="t1307-creator")
        self.creator.groups.add(editor_group)
        self.submitter = User.objects.create_user(username="t1307-submitter")
        self.submitter.groups.add(editor_group)
        self.reviewer_a = User.objects.create_user(username="t1307-reviewer-a")
        self.reviewer_a.groups.add(reviewer_group)
        self.reviewer_b = User.objects.create_user(username="t1307-reviewer-b")
        self.reviewer_b.groups.add(reviewer_group)
        self.reviewer_c = User.objects.create_user(username="t1307-reviewer-c")
        self.reviewer_c.groups.add(reviewer_group)
        self.employee = User.objects.create_user(username="t1307-employee")

        self.space_a = KnowledgeSpace.objects.create(
            code="t1307-space-a",
            name="Task13-07 Space A",
            space_type="employee",
            owner=self.creator,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        self.space_b = KnowledgeSpace.objects.create(
            code="t1307-space-b",
            name="Task13-07 Space B",
            space_type="employee",
            owner=self.submitter,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        self.category_a = Category.objects.create(
            space=self.space_a,
            code="t1307-category-a",
            name="Task13-07 Category A",
        )
        self.category_b = Category.objects.create(
            space=self.space_b,
            code="t1307-category-b",
            name="Task13-07 Category B",
        )
        ReviewerSpaceScope.objects.create(reviewer=self.reviewer_a, space=self.space_a)
        ReviewerSpaceScope.objects.create(reviewer=self.reviewer_b, space=self.space_b)
        ReviewerSpaceScope.objects.create(reviewer=self.reviewer_c, space=self.space_a)
        ReviewerSpaceScope.objects.create(reviewer=self.reviewer_c, space=self.space_b)
        self.sequence = 0

    def _next_kb_no(self):
        self.sequence += 1
        return f"KB-{170000 + self.sequence:06d}"

    def _create_article(
        self,
        *,
        status=VersionStatus.IN_REVIEW,
        published=False,
        space=None,
        creator=None,
        submitter=None,
        marker=None,
    ):
        space = space or self.space_a
        category = self.category_a if space == self.space_a else self.category_b
        creator = creator or self.creator
        submitter = submitter or self.submitter
        marker = marker or f"R{self.sequence + 1}"
        article = Article.objects.create(
            kb_no=self._next_kb_no(),
            title=f"{marker} old article title",
            space=space,
            category=category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            owner=creator,
            created_by=creator,
            updated_by=creator,
            review_due_at=timezone.now() + timedelta(days=180),
        )
        old_published = None
        if published:
            old_published = ArticleVersion.objects.create(
                article=article,
                version_no=1,
                status=VersionStatus.PUBLISHED,
                lock_version=3,
                title=f"{marker} OLD title",
                summary=f"{marker} OLD summary",
                applicable_scope={"marker": marker, "generation": "old"},
                body={"format": "opsai.plaintext/1", "text": f"{marker}OLDKEY body"},
                body_plaintext=f"{marker}OLDKEY body",
                change_summary="old published version",
                created_by=creator,
                submitted_by=submitter,
                submitted_at=timezone.now() - timedelta(days=2),
                published_at=timezone.now() - timedelta(days=1),
            )
        target = ArticleVersion.objects.create(
            article=article,
            version_no=2 if published else 1,
            status=status,
            lock_version=1,
            title=f"{marker} NEW title",
            summary=f"{marker} NEW summary",
            applicable_scope={"marker": marker, "generation": "new"},
            body={"format": "opsai.plaintext/1", "text": f"{marker}NEWKEY body"},
            body_plaintext=f"{marker}NEWKEY body",
            change_summary="new workflow target",
            created_by=creator,
            submitted_by=(
                submitter if status not in (VersionStatus.DRAFT, VersionStatus.SAVED) else None
            ),
            submitted_at=(
                timezone.now() - timedelta(hours=1)
                if status not in (VersionStatus.DRAFT, VersionStatus.SAVED)
                else None
            ),
            published_at=(timezone.now() if status == VersionStatus.PUBLISHED else None),
        )
        current_published = target if status == VersionStatus.PUBLISHED else old_published
        Article.objects.filter(pk=article.pk).update(
            current_published_version=current_published,
            latest_working_version=(target if status == VersionStatus.DRAFT else None),
            title=current_published.title if current_published else article.title,
        )
        article.refresh_from_db()
        return article, target, old_published

    def _worker(self, spec, barrier, ready_event=None, backend_pids=None):
        close_old_connections()
        thread_connection = connections["default"]
        try:
            thread_connection.ensure_connection()
            backend_pid = thread_connection.connection.info.backend_pid
            if backend_pids is not None:
                backend_pids[spec.get("name", spec["op"])] = backend_pid
            actor = User.objects.get(pk=spec["actor_id"])
            article = Article.objects.get(pk=spec["article_id"])
            if ready_event is not None:
                ready_event.set()
            barrier.wait(timeout=10)
            operation = spec["op"]
            if operation == "submit":
                result = submit_article_for_review(
                    actor=actor,
                    kb_no=article.kb_no,
                    draft_id=spec["version_id"],
                    expected_lock_version=spec.get("lock_version", 1),
                    idempotency_key=spec["key"],
                )
            elif operation == "autosave":
                marker = spec["marker"]
                result = autosave_draft(
                    actor=actor,
                    article=article,
                    draft_id=spec["version_id"],
                    expected_lock_version=spec.get("lock_version", 1),
                    title=f"{marker} autosave title",
                    summary=f"{marker} autosave summary",
                    applicable_scope={"worker": marker},
                    body_text=f"{marker} AUTOSAVE body",
                    change_summary=f"{marker} autosave",
                )
            elif operation == "reject":
                result = reject_article_version(
                    actor=actor,
                    version_id=spec["version_id"],
                    comment=spec.get("comment", "real PostgreSQL rejection"),
                    idempotency_key=spec["key"],
                )
            elif operation == "approve":
                result = approve_and_publish_article_version(
                    actor=actor,
                    version_id=spec["version_id"],
                    comment=spec.get("comment", "real PostgreSQL approval"),
                    idempotency_key=spec["key"],
                )
            else:
                raise AssertionError(f"Unknown operation: {operation}")
            return ("success", operation, result, backend_pid)
        except (
            SubmitArticleForReviewError,
            RejectArticleVersionError,
            ApprovePublishArticleVersionError,
            ArticleVersionWriteError,
        ) as exc:
            return ("error", spec["op"], exc.code, thread_connection.connection.info.backend_pid)
        finally:
            close_old_connections()
            thread_connection.close()

    def _race(self, specs, *, ready_events=None, backend_pids=None):
        barrier = Barrier(len(specs))
        ready_events = ready_events or [None] * len(specs)
        with ThreadPoolExecutor(max_workers=len(specs)) as executor:
            futures = [
                executor.submit(
                    self._worker,
                    spec,
                    barrier,
                    ready_events[index],
                    backend_pids,
                )
                for index, spec in enumerate(specs)
            ]
            return [future.result(timeout=40) for future in futures]

    def _submit_spec(self, article, draft, *, key, name="submit"):
        return {
            "name": name,
            "op": "submit",
            "actor_id": self.creator.pk,
            "article_id": article.pk,
            "version_id": draft.pk,
            "lock_version": draft.lock_version,
            "key": key,
        }

    def _review_spec(self, operation, article, target, reviewer, *, key, name=None):
        return {
            "name": name or operation,
            "op": operation,
            "actor_id": reviewer.pk,
            "article_id": article.pk,
            "version_id": target.pk,
            "key": key,
        }

    def _assert_one_winner(self, results, *, allowed_codes):
        successes = [result for result in results if result[0] == "success"]
        errors = [result for result in results if result[0] == "error"]
        self.assertEqual(len(successes), 1, results)
        self.assertEqual(len(errors), 1, results)
        self.assertIn(errors[0][2], allowed_codes, results)
        return successes[0], errors[0]

    def _assert_article_invariants(self, article_id):
        article = Article.objects.select_related(
            "latest_working_version", "current_published_version"
        ).get(pk=article_id)
        versions = list(ArticleVersion.objects.filter(article_id=article_id))
        for status in (
            VersionStatus.DRAFT,
            VersionStatus.IN_REVIEW,
            VersionStatus.PUBLISHED,
        ):
            self.assertLessEqual(
                sum(version.status == status for version in versions),
                1,
                (status, versions),
            )
        drafts = [version for version in versions if version.status == VersionStatus.DRAFT]
        if article.latest_working_version_id is None:
            self.assertEqual(drafts, [])
        else:
            self.assertEqual(
                [version.pk for version in drafts], [article.latest_working_version_id]
            )
        if article.current_published_version_id is not None:
            self.assertEqual(article.current_published_version.status, VersionStatus.PUBLISHED)
            self.assertEqual(article.title, article.current_published_version.title)
        self.assertFalse(
            WorkflowIdempotencyRecord.objects.filter(status=IdempotencyStatus.IN_PROGRESS).exists()
        )
        return article, versions

    def _article_evidence_counts(self, article):
        return (
            AuditEvent.objects.filter(article=article).count(),
            WorkflowOutboxEvent.objects.filter(payload__article_id=str(article.pk)).count(),
            ReviewRecord.objects.filter(article_version__article=article).count(),
        )

    def _visibility_worker(self, article_id, target_id, actor_id, key, staged, release):
        close_old_connections()
        thread_connection = connections["default"]
        try:
            thread_connection.ensure_connection()
            with transaction.atomic():
                actor = User.objects.get(pk=actor_id)
                result = approve_and_publish_article_version(
                    actor=actor,
                    version_id=target_id,
                    comment="visibility commit boundary",
                    idempotency_key=key,
                )
                staged.set()
                if not release.wait(timeout=10):
                    raise TimeoutError("visibility transaction release timeout")
            return result
        finally:
            close_old_connections()
            thread_connection.close()

    def test_pg01_submit_vs_autosave_uses_cas_without_overwrite(self):
        for round_no in range(self.race_rounds):
            article, draft, old = self._create_article(
                status=VersionStatus.DRAFT,
                marker=f"PG01R{round_no}",
            )
            submit = self._submit_spec(article, draft, key=f"pg01-submit-{round_no}")
            autosave = {
                "name": "autosave",
                "op": "autosave",
                "actor_id": self.creator.pk,
                "article_id": article.pk,
                "version_id": draft.pk,
                "lock_version": 1,
                "marker": f"PG01R{round_no}",
            }
            results = self._race([submit, autosave])
            winner, _loser = self._assert_one_winner(
                results,
                allowed_codes={
                    DRAFT_CONFLICT,
                    DRAFT_NOT_CURRENT,
                    WRITE_DRAFT_CONFLICT,
                    WRITE_DRAFT_NOT_CURRENT,
                    INVALID_DRAFT_STATE,
                    DATABASE_WRITE_FAILED,
                },
            )
            article.refresh_from_db()
            draft.refresh_from_db()
            self.assertIsNone(article.current_published_version_id)
            self.assertIsNone(old)
            if winner[1] == "submit":
                self.assertEqual(draft.status, VersionStatus.IN_REVIEW)
                self.assertNotIn("AUTOSAVE", draft.body_plaintext)
                self.assertIsNone(article.latest_working_version_id)
                self.assertEqual(self._article_evidence_counts(article), (1, 1, 0))
            else:
                self.assertEqual(draft.status, VersionStatus.DRAFT)
                self.assertIn("AUTOSAVE", draft.body_plaintext)
                self.assertEqual(article.latest_working_version_id, draft.pk)
                self.assertEqual(self._article_evidence_counts(article), (0, 0, 0))
            self._assert_article_invariants(article.pk)

    def test_pg02_submit_same_key_executes_once_and_replays(self):
        for round_no in range(self.race_rounds):
            article, draft, _old = self._create_article(status=VersionStatus.DRAFT)
            spec = self._submit_spec(article, draft, key=f"pg02-same-{round_no}")
            results = self._race([dict(spec, name="submit-a"), dict(spec, name="submit-b")])
            self.assertEqual([result[0] for result in results], ["success", "success"], results)
            self.assertEqual(results[0][2], results[1][2])
            self.assertEqual(self._article_evidence_counts(article), (1, 1, 0))
            records = WorkflowIdempotencyRecord.objects.filter(key=spec["key"])
            self.assertEqual(records.count(), 1)
            self.assertEqual(records.get().status, IdempotencyStatus.COMPLETED)
            replay = submit_article_for_review(
                actor=self.creator,
                kb_no=article.kb_no,
                draft_id=draft.pk,
                expected_lock_version=1,
                idempotency_key=spec["key"],
            )
            self.assertEqual(replay.version_id, draft.pk)
            self._assert_article_invariants(article.pk)

    def test_pg03_submit_different_keys_has_one_transition(self):
        for round_no in range(self.race_rounds):
            article, draft, _old = self._create_article(status=VersionStatus.DRAFT)
            results = self._race(
                [
                    self._submit_spec(article, draft, key=f"pg03-a-{round_no}", name="a"),
                    self._submit_spec(article, draft, key=f"pg03-b-{round_no}", name="b"),
                ]
            )
            self._assert_one_winner(
                results,
                allowed_codes={DRAFT_NOT_CURRENT, DRAFT_CONFLICT},
            )
            self.assertEqual(self._article_evidence_counts(article), (1, 1, 0))
            self.assertEqual(
                WorkflowIdempotencyRecord.objects.filter(
                    operation=IdempotencyOperation.SUBMIT,
                    status=IdempotencyStatus.COMPLETED,
                ).count(),
                round_no + 1,
            )
            self._assert_article_invariants(article.pk)

    def test_pg04_reject_vs_reject_has_one_terminal_record_and_successor(self):
        for round_no in range(self.race_rounds):
            article, target, _old = self._create_article(marker=f"PG04R{round_no}")
            results = self._race(
                [
                    self._review_spec(
                        "reject",
                        article,
                        target,
                        self.reviewer_a,
                        key=f"pg04-a-{round_no}",
                        name="a",
                    ),
                    self._review_spec(
                        "reject",
                        article,
                        target,
                        self.reviewer_c,
                        key=f"pg04-c-{round_no}",
                        name="c",
                    ),
                ]
            )
            self._assert_one_winner(results, allowed_codes={VERSION_NOT_IN_REVIEW})
            target.refresh_from_db()
            self.assertEqual(target.status, VersionStatus.REJECTED)
            article, versions = self._assert_article_invariants(article.pk)
            self.assertEqual(sum(v.status == VersionStatus.DRAFT for v in versions), 1)
            self.assertEqual(self._article_evidence_counts(article), (1, 1, 1))
            review = ReviewRecord.objects.get(article_version=target)
            self.assertEqual(review.decision, ReviewDecision.REJECTED)

    def test_pg05_first_approve_vs_approve_has_one_publish(self):
        for round_no in range(self.race_rounds):
            article, target, _old = self._create_article(marker=f"PG05R{round_no}")
            results = self._race(
                [
                    self._review_spec(
                        "approve", article, target, self.reviewer_a, key=f"pg05-a-{round_no}"
                    ),
                    self._review_spec(
                        "approve", article, target, self.reviewer_c, key=f"pg05-c-{round_no}"
                    ),
                ]
            )
            self._assert_one_winner(results, allowed_codes={VERSION_NOT_IN_REVIEW})
            target.refresh_from_db()
            self.assertEqual(target.status, VersionStatus.PUBLISHED)
            article, versions = self._assert_article_invariants(article.pk)
            self.assertEqual(article.current_published_version_id, target.pk)
            self.assertEqual(sum(v.status == VersionStatus.DRAFT for v in versions), 1)
            self.assertEqual(self._article_evidence_counts(article), (1, 1, 1))

    def test_pg06_republish_vs_approve_preserves_one_published_and_draft(self):
        for round_no in range(self.race_rounds):
            article, target, old = self._create_article(
                published=True,
                marker=f"PG06R{round_no}",
            )
            old_published_at = old.published_at
            results = self._race(
                [
                    self._review_spec(
                        "approve", article, target, self.reviewer_a, key=f"pg06-a-{round_no}"
                    ),
                    self._review_spec(
                        "approve", article, target, self.reviewer_c, key=f"pg06-c-{round_no}"
                    ),
                ]
            )
            self._assert_one_winner(results, allowed_codes={VERSION_NOT_IN_REVIEW})
            old.refresh_from_db()
            target.refresh_from_db()
            self.assertEqual(old.status, VersionStatus.SUPERSEDED)
            self.assertEqual(old.published_at, old_published_at)
            self.assertEqual(target.status, VersionStatus.PUBLISHED)
            article, versions = self._assert_article_invariants(article.pk)
            self.assertEqual(article.current_published_version_id, target.pk)
            self.assertEqual(sum(v.status == VersionStatus.PUBLISHED for v in versions), 1)
            self.assertEqual(sum(v.status == VersionStatus.DRAFT for v in versions), 1)
            self.assertEqual(self._article_evidence_counts(article), (1, 1, 1))

    def test_pg07_approve_vs_reject_has_exactly_one_legal_terminal_state(self):
        for round_no in range(5):
            article, target, old = self._create_article(
                published=True,
                marker=f"PG07R{round_no}",
            )
            results = self._race(
                [
                    self._review_spec(
                        "approve", article, target, self.reviewer_a, key=f"pg07-a-{round_no}"
                    ),
                    self._review_spec(
                        "reject", article, target, self.reviewer_c, key=f"pg07-r-{round_no}"
                    ),
                ]
            )
            winner, _loser = self._assert_one_winner(
                results,
                allowed_codes={VERSION_NOT_IN_REVIEW},
            )
            target.refresh_from_db()
            old.refresh_from_db()
            article, versions = self._assert_article_invariants(article.pk)
            review = ReviewRecord.objects.get(article_version=target)
            self.assertEqual(self._article_evidence_counts(article), (1, 1, 1))
            self.assertEqual(sum(v.status == VersionStatus.DRAFT for v in versions), 1)
            if winner[1] == "approve":
                self.assertEqual(target.status, VersionStatus.PUBLISHED)
                self.assertEqual(review.decision, ReviewDecision.APPROVED)
                self.assertEqual(old.status, VersionStatus.SUPERSEDED)
                self.assertEqual(article.current_published_version_id, target.pk)
                expected_event = AuditEventType.REVIEW_APPROVED_PUBLISHED
            else:
                self.assertEqual(target.status, VersionStatus.REJECTED)
                self.assertEqual(review.decision, ReviewDecision.REJECTED)
                self.assertEqual(old.status, VersionStatus.PUBLISHED)
                self.assertEqual(article.current_published_version_id, old.pk)
                expected_event = AuditEventType.REVIEW_REJECTED
            self.assertEqual(AuditEvent.objects.get(article=article).event_type, expected_event)

    def _hold_article_lock(self, article_id, acquired, release, pids):
        close_old_connections()
        thread_connection = connections["default"]
        try:
            thread_connection.ensure_connection()
            pids["blocker"] = thread_connection.connection.info.backend_pid
            with transaction.atomic():
                Article.objects.select_for_update().get(pk=article_id)
                acquired.set()
                if not release.wait(timeout=10):
                    raise TimeoutError("article lock release timeout")
        finally:
            close_old_connections()
            thread_connection.close()

    def _wait_for_blocking(self, waiter_pid, blocker_pid, timeout=5):
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_blocking_pids(pid), wait_event_type, wait_event "
                    "FROM pg_stat_activity WHERE pid = %s",
                    [waiter_pid],
                )
                row = cursor.fetchone()
            if row and blocker_pid in row[0] and row[1] == "Lock":
                return row
            Event().wait(0.05)
        return None

    def test_pg08_postgres_reports_real_article_lock_wait_and_recheck(self):
        article, target, _old = self._create_article(marker="PG08")
        acquired = Event()
        release = Event()
        ready = Event()
        pids = {}
        spec = self._review_spec(
            "approve",
            article,
            target,
            self.reviewer_a,
            key="pg08-lock",
            name="waiter",
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            lock_future = executor.submit(
                self._hold_article_lock,
                article.pk,
                acquired,
                release,
                pids,
            )
            self.assertTrue(acquired.wait(timeout=5))
            service_future = executor.submit(self._worker, spec, Barrier(1), ready, pids)
            try:
                self.assertTrue(ready.wait(timeout=5))
                deadline = monotonic() + 5
                while "waiter" not in pids and monotonic() < deadline:
                    Event().wait(0.01)
                self.assertIn("waiter", pids)
                evidence = self._wait_for_blocking(pids["waiter"], pids["blocker"])
                self.assertIsNotNone(evidence)
                self.assertNotEqual(pids["blocker"], pids["waiter"])
            finally:
                release.set()
            result = service_future.result(timeout=20)
            lock_future.result(timeout=10)
        self.assertEqual(result[0], "success", result)
        target.refresh_from_db()
        self.assertEqual(target.status, VersionStatus.PUBLISHED)
        second = reject_article_version
        with self.assertRaises(RejectArticleVersionError) as caught:
            second(
                actor=self.reviewer_c,
                version_id=target.pk,
                comment="must re-read committed status",
                idempotency_key="pg08-after",
            )
        self.assertEqual(caught.exception.code, VERSION_NOT_IN_REVIEW)
        self._assert_article_invariants(article.pk)

    def test_pg09_idempotency_unique_competes_then_service_replays_and_conflicts(self):
        barrier = Barrier(2)

        def create_record(name):
            close_old_connections()
            thread_connection = connections["default"]
            try:
                thread_connection.ensure_connection()
                actor = User.objects.get(pk=self.creator.pk)
                barrier.wait(timeout=10)
                try:
                    with transaction.atomic():
                        WorkflowIdempotencyRecord.objects.create(
                            actor=actor,
                            operation=IdempotencyOperation.SUBMIT,
                            key="pg09-direct-race",
                            request_fingerprint="a" * 64,
                        )
                    return (name, "success")
                except IntegrityError:
                    return (name, "integrity_error")
            finally:
                close_old_connections()
                thread_connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [
                future.result(timeout=20)
                for future in (
                    executor.submit(create_record, "a"),
                    executor.submit(create_record, "b"),
                )
            ]
        self.assertEqual(sorted(result[1] for result in results), ["integrity_error", "success"])
        self.assertEqual(
            WorkflowIdempotencyRecord.objects.filter(key="pg09-direct-race").count(),
            1,
        )
        WorkflowIdempotencyRecord.objects.create(
            actor=self.creator,
            operation=IdempotencyOperation.SUBMIT,
            key="pg09-different-key",
            request_fingerprint="b" * 64,
        )
        article, draft, _old = self._create_article(status=VersionStatus.DRAFT)
        kwargs = {
            "actor": self.creator,
            "kb_no": article.kb_no,
            "draft_id": draft.pk,
            "expected_lock_version": 1,
            "idempotency_key": "pg09-service-replay",
        }
        first = submit_article_for_review(**kwargs)
        replay = submit_article_for_review(**kwargs)
        self.assertEqual(first, replay)
        with self.assertRaises(SubmitArticleForReviewError) as caught:
            submit_article_for_review(**dict(kwargs, expected_lock_version=2))
        self.assertEqual(caught.exception.code, IDEMPOTENCY_CONFLICT)
        self.assertEqual(self._article_evidence_counts(article), (1, 1, 0))

    def test_pg10_first_publish_is_invisible_until_outer_commit(self):
        article, target, _old = self._create_article(marker="PG10")
        staged = Event()
        release = Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self._visibility_worker,
                article.pk,
                target.pk,
                self.reviewer_a.pk,
                "pg10-visible",
                staged,
                release,
            )
            try:
                self.assertTrue(staged.wait(timeout=10))
                self.assertIsNone(get_employee_article_detail(self.employee, article.kb_no))
                self.assertFalse(
                    search_employee_articles(self.employee, "PG10NEWKEY")
                    .filter(pk=article.pk)
                    .exists()
                )
            finally:
                release.set()
            future.result(timeout=20)
        detail = get_employee_article_detail(self.employee, article.kb_no)
        self.assertEqual(detail.body_text, "PG10NEWKEY body")
        self.assertTrue(
            search_employee_articles(self.employee, "PG10NEWKEY").filter(pk=article.pk).exists()
        )

    def test_pg11_republish_switches_employee_content_only_after_commit(self):
        article, target, old = self._create_article(published=True, marker="PG11")
        staged = Event()
        release = Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self._visibility_worker,
                article.pk,
                target.pk,
                self.reviewer_a.pk,
                "pg11-visible",
                staged,
                release,
            )
            try:
                self.assertTrue(staged.wait(timeout=10))
                detail = get_employee_article_detail(self.employee, article.kb_no)
                self.assertEqual(detail.body_text, "PG11OLDKEY body")
                self.assertTrue(
                    search_employee_articles(self.employee, "PG11OLDKEY")
                    .filter(pk=article.pk)
                    .exists()
                )
                self.assertFalse(
                    search_employee_articles(self.employee, "PG11NEWKEY")
                    .filter(pk=article.pk)
                    .exists()
                )
            finally:
                release.set()
            future.result(timeout=20)
        detail = get_employee_article_detail(self.employee, article.kb_no)
        self.assertEqual(detail.body_text, "PG11NEWKEY body")
        self.assertFalse(
            search_employee_articles(self.employee, "PG11OLDKEY").filter(pk=article.pk).exists()
        )
        self.assertTrue(
            search_employee_articles(self.employee, "PG11NEWKEY").filter(pk=article.pk).exists()
        )
        old.refresh_from_db()
        self.assertEqual(old.status, VersionStatus.SUPERSEDED)

    def _business_snapshot(self, article_id):
        article = Article.objects.get(pk=article_id)
        return {
            "article": (
                article.title,
                article.current_published_version_id,
                article.latest_working_version_id,
                article.updated_by_id,
            ),
            "versions": list(
                ArticleVersion.objects.filter(article_id=article_id)
                .order_by("version_no")
                .values_list(
                    "id",
                    "version_no",
                    "status",
                    "published_at",
                    "created_by_id",
                )
            ),
            "reviews": ReviewRecord.objects.filter(article_version__article_id=article_id).count(),
            "audits": AuditEvent.objects.filter(article_id=article_id).count(),
            "outbox": WorkflowOutboxEvent.objects.filter(
                payload__article_id=str(article_id)
            ).count(),
            "idempotency": WorkflowIdempotencyRecord.objects.count(),
        }

    def test_pg12_republish_failure_injections_roll_back_all_business_state(self):
        failure_points = (
            ("review", "apps.workflow.services._create_approval_review"),
            ("successor", "apps.workflow.services._create_approved_successor_draft"),
            ("audit", "apps.workflow.services.AuditEvent.objects.create"),
            ("outbox", "apps.workflow.services.WorkflowOutboxEvent.objects.create"),
            ("idempotency", "apps.workflow.services._complete_approve_publish_idempotency"),
        )
        for name, patch_target in failure_points:
            article, target, old = self._create_article(
                published=True,
                marker=f"PG12{name}",
            )
            before = self._business_snapshot(article.pk)
            old_published_at = old.published_at
            with mock.patch(patch_target, side_effect=DatabaseError("injected failure")):
                with self.assertRaises(ApprovePublishArticleVersionError) as caught:
                    approve_and_publish_article_version(
                        actor=self.reviewer_a,
                        version_id=target.pk,
                        comment="rollback proof",
                        idempotency_key=f"pg12-{name}",
                    )
            self.assertEqual(caught.exception.code, WORKFLOW_UNAVAILABLE)
            self.assertEqual(self._business_snapshot(article.pk), before)
            old.refresh_from_db()
            target.refresh_from_db()
            self.assertEqual(old.status, VersionStatus.PUBLISHED)
            self.assertEqual(old.published_at, old_published_at)
            self.assertEqual(target.status, VersionStatus.IN_REVIEW)

    def test_pg13_cross_space_concurrency_and_self_review_cannot_bypass_scope(self):
        article, target, _old = self._create_article(space=self.space_b, marker="PG13")
        results = self._race(
            [
                self._review_spec(
                    "reject",
                    article,
                    target,
                    self.reviewer_a,
                    key="pg13-out-of-scope",
                    name="out-of-scope",
                ),
                self._review_spec(
                    "reject",
                    article,
                    target,
                    self.reviewer_c,
                    key="pg13-authorized",
                    name="authorized",
                ),
            ]
        )
        success, failure = self._assert_one_winner(
            results,
            allowed_codes={VERSION_NOT_FOUND_OR_INACCESSIBLE},
        )
        self.assertEqual(success[1], "reject")
        self.assertEqual(failure[1], "reject")
        self.assertEqual(self._article_evidence_counts(article), (1, 1, 1))

        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        self.creator.groups.add(reviewer_group)
        ReviewerSpaceScope.objects.create(reviewer=self.creator, space=self.space_a)
        own_article, own_target, _old = self._create_article(
            creator=self.creator,
            submitter=self.submitter,
            marker="PG13SELF",
        )
        with self.assertRaises(ApprovePublishArticleVersionError) as caught:
            approve_and_publish_article_version(
                actor=self.creator,
                version_id=own_target.pk,
                comment="self review must fail",
                idempotency_key="pg13-self",
            )
        self.assertEqual(caught.exception.code, SELF_REVIEW_FORBIDDEN)
        self.assertEqual(self._article_evidence_counts(own_article), (0, 0, 0))

    def _assert_duplicate_version_status_rejected(self, status):
        article, target, _old = self._create_article(
            status=status,
            marker=f"PG14{status}",
        )
        submitted = status not in (VersionStatus.DRAFT, VersionStatus.SAVED)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ArticleVersion.objects.create(
                    article=article,
                    version_no=99,
                    status=status,
                    lock_version=1,
                    title="duplicate constrained status",
                    summary="duplicate constrained status",
                    applicable_scope={},
                    body={"format": "opsai.plaintext/1", "text": "duplicate"},
                    body_plaintext="duplicate",
                    change_summary="duplicate",
                    created_by=self.creator,
                    submitted_by=self.submitter if submitted else None,
                    submitted_at=timezone.now() if submitted else None,
                    published_at=timezone.now() if status == VersionStatus.PUBLISHED else None,
                )
        self.assertEqual(
            ArticleVersion.objects.filter(article=article, status=status).count(),
            1,
        )
        return article, target

    def test_pg14_postgres_partial_unique_review_outbox_constraints_hold(self):
        self._assert_duplicate_version_status_rejected(VersionStatus.DRAFT)
        self._assert_duplicate_version_status_rejected(VersionStatus.IN_REVIEW)
        published_article, published_target = self._assert_duplicate_version_status_rejected(
            VersionStatus.PUBLISHED
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexname FROM pg_indexes WHERE indexname = ANY(%s)",
                [
                    [
                        "kb_ver_working_uniq",
                        "kb_ver_in_review_uniq",
                        "kb_ver_published_uniq",
                        "kb_review_content_uniq",
                    ]
                ],
            )
            index_names = {row[0] for row in cursor.fetchall()}
        self.assertEqual(
            index_names,
            {
                "kb_ver_working_uniq",
                "kb_ver_in_review_uniq",
                "kb_ver_published_uniq",
                "kb_review_content_uniq",
            },
        )
        ReviewRecord.objects.create(
            article_version=published_target,
            review_type=ReviewType.CONTENT_REVIEW,
            reviewer=self.reviewer_a,
            decision=ReviewDecision.APPROVED,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ReviewRecord.objects.create(
                    article_version=published_target,
                    review_type=ReviewType.CONTENT_REVIEW,
                    reviewer=self.reviewer_c,
                    decision=ReviewDecision.REJECTED,
                    comment="duplicate terminal record",
                )
        WorkflowOutboxEvent.objects.create(
            event_type=WorkflowEventType.REVIEW_SUBMITTED,
            dedupe_key="pg14-outbox-dedupe",
            payload={"article_id": str(published_article.pk)},
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkflowOutboxEvent.objects.create(
                    event_type=WorkflowEventType.REVIEW_SUBMITTED,
                    dedupe_key="pg14-outbox-dedupe",
                    payload={"article_id": str(published_article.pk)},
                )
