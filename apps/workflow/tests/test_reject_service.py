"""Task 13-04：IN_REVIEW → REJECTED 并创建后继 DRAFT。"""

import hashlib
import json
from datetime import timedelta
from unittest import mock
from uuid import uuid4

from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.management import call_command
from django.db import DatabaseError
from django.db.models.query import QuerySet
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import AccountStatus, User
from apps.accounts.roles import (
    ROLE_EDITOR,
    ROLE_KNOWLEDGE_ADMIN,
    ROLE_REVIEWER,
    SYSTEM_ROLE_BY_CODE,
)
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
from apps.knowledge.readers import employee_visible_articles, get_employee_article_detail
from apps.knowledge.services import ArticleVersionWriteError, autosave_draft, manual_save_draft
from apps.knowledge.version_readers import get_article_version_history
from apps.search.readers import search_employee_articles
from apps.workflow.models import (
    IdempotencyOperation,
    IdempotencyStatus,
    WorkflowIdempotencyRecord,
    WorkflowOutboxEvent,
    WorkflowOutboxStatus,
)
from apps.workflow.services import (
    IDEMPOTENCY_CONFLICT,
    IDEMPOTENCY_IN_PROGRESS,
    IDENTITY_DENIED,
    INVALID_INPUT,
    REJECT_FORBIDDEN,
    REVIEW_REJECTED,
    SELF_REVIEW_FORBIDDEN,
    VERSION_NOT_FOUND_OR_INACCESSIBLE,
    VERSION_NOT_IN_REVIEW,
    WORKFLOW_UNAVAILABLE,
    RejectArticleVersionError,
    RejectReviewResult,
    reject_article_version,
)


class RejectArticleVersionServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0)
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)

        cls.creator = User.objects.create_user(username="reject-creator")
        cls.creator.groups.add(editor_group)
        cls.submitter = User.objects.create_user(username="reject-submitter")
        cls.submitter.groups.add(editor_group)
        cls.reviewer = User.objects.create_user(username="reject-reviewer")
        cls.reviewer.groups.add(reviewer_group)
        cls.second_reviewer = User.objects.create_user(username="reject-second-reviewer")
        cls.second_reviewer.groups.add(reviewer_group)
        cls.reviewer_admin = User.objects.create_user(username="reject-reviewer-admin")
        cls.reviewer_admin.groups.add(reviewer_group, admin_group)
        cls.admin_only = User.objects.create_user(username="reject-admin-only")
        cls.admin_only.groups.add(admin_group)
        cls.editor_only = User.objects.create_user(username="reject-editor-only")
        cls.editor_only.groups.add(editor_group)
        cls.employee = User.objects.create_user(username="reject-employee")
        cls.staff_only = User.objects.create_user(username="reject-staff", is_staff=True)
        cls.superuser_only = User.objects.create_user(
            username="reject-superuser",
            is_staff=True,
            is_superuser=True,
        )
        cls.inactive_reviewer = User.objects.create_user(
            username="reject-inactive-reviewer",
            is_active=False,
        )
        cls.inactive_reviewer.groups.add(reviewer_group)
        cls.disabled_reviewer = User.objects.create_user(
            username="reject-disabled-reviewer",
            account_status=AccountStatus.DISABLED,
        )
        cls.disabled_reviewer.groups.add(reviewer_group)

        cls.space_owner = User.objects.create_user(username="reject-space-owner")
        cls.space = KnowledgeSpace.objects.create(
            code="reject-space",
            name="Task 13 Reject 空间",
            space_type="employee",
            owner=cls.space_owner,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="reject-category",
            name="Task 13 Reject 分类",
        )
        cls.other_space = KnowledgeSpace.objects.create(
            code="reject-other-space",
            name="Task 13 其他空间",
            space_type="employee",
            owner=cls.space_owner,
        )
        for reviewer in (cls.reviewer, cls.second_reviewer, cls.reviewer_admin):
            ReviewerSpaceScope.objects.create(reviewer=reviewer, space=cls.space)

    def setUp(self):
        self._sequence = 0

    def make_article(
        self,
        *,
        creator=None,
        submitter=None,
        published=False,
        target_status=VersionStatus.IN_REVIEW,
        target_version_no=None,
        high_history_version_no=None,
    ):
        self._sequence += 1
        creator = creator or self.creator
        submitter = submitter or self.submitter
        article = Article.objects.create(
            kb_no=f"KB-{140000 + self._sequence:06d}",
            title="兼容 Published 标题",
            space=self.space,
            category=self.category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            owner=creator,
            created_by=creator,
            updated_by=self.space_owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )
        published_version = None
        if published:
            published_version = ArticleVersion.objects.create(
                article=article,
                version_no=1,
                status=VersionStatus.PUBLISHED,
                lock_version=3,
                title="正式 Published 标题",
                summary="正式 Published 摘要",
                applicable_scope={"published": True},
                body={"format": "opsai.plaintext/1", "text": "正式内容唯一关键词"},
                body_plaintext="正式内容唯一关键词",
                change_summary="既有正式版本",
                created_by=creator,
                submitted_by=submitter,
                submitted_at=timezone.now() - timedelta(days=3),
                published_at=timezone.now() - timedelta(days=2),
            )
        version_no = target_version_no or (2 if published else 1)
        submitted = target_status not in (VersionStatus.DRAFT, VersionStatus.SAVED)
        target = ArticleVersion.objects.create(
            article=article,
            version_no=version_no,
            status=target_status,
            lock_version=2,
            title="被驳回版本标题",
            summary="被驳回版本摘要",
            applicable_scope={"systems": ["Windows 11"]},
            body={"format": "opsai.plaintext/1", "text": "待审核内容唯一关键词"},
            body_plaintext="待审核内容唯一关键词",
            change_summary="原待审核修改说明",
            created_by=creator,
            submitted_by=submitter if submitted else None,
            submitted_at=timezone.now() - timedelta(hours=1) if submitted else None,
            published_at=(
                timezone.now() - timedelta(minutes=30)
                if target_status == VersionStatus.PUBLISHED
                else None
            ),
        )
        if high_history_version_no is not None:
            ArticleVersion.objects.create(
                article=article,
                version_no=high_history_version_no,
                status=VersionStatus.SAVED,
                title="高版本历史",
                summary="高版本历史摘要",
                change_summary="高版本历史",
                created_by=creator,
            )
        Article.objects.filter(pk=article.pk).update(
            current_published_version=published_version,
            latest_working_version=(target if target_status == VersionStatus.DRAFT else None),
        )
        article.refresh_from_db()
        return article, target, published_version

    def reject_kwargs(self, target, **overrides):
        values = {
            "actor": self.reviewer,
            "version_id": target.pk,
            "comment": "  步骤存在安全风险  ",
            "idempotency_key": f"reject-{target.pk}",
        }
        values.update(overrides)
        return values

    def expected_fingerprint(self, target, comment="步骤存在安全风险"):
        canonical = json.dumps(
            {"comment": comment, "version_id": str(target.pk)},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def assert_reject_error(self, code, target, **overrides):
        with self.assertRaises(RejectArticleVersionError) as caught:
            reject_article_version(**self.reject_kwargs(target, **overrides))
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def snapshot(self, article, target):
        article.refresh_from_db()
        target.refresh_from_db()
        return {
            "article_updated_at": article.updated_at,
            "article_updated_by_id": article.updated_by_id,
            "latest_working_version_id": article.latest_working_version_id,
            "current_published_version_id": article.current_published_version_id,
            "article_title": article.title,
            "target_status": target.status,
            "target_updated_at": target.updated_at,
            "target_lock_version": target.lock_version,
            "version_count": ArticleVersion.objects.filter(article=article).count(),
            "review_count": ReviewRecord.objects.count(),
            "audit_count": AuditEvent.objects.count(),
            "outbox_count": WorkflowOutboxEvent.objects.count(),
            "idempotency_count": WorkflowIdempotencyRecord.objects.count(),
        }

    def assert_snapshot_unchanged(self, before, article, target):
        self.assertEqual(self.snapshot(article, target), before)

    def test_success_rejects_version_and_creates_exact_transaction_artifacts(self):
        article, target, published = self.make_article(published=True)
        submitted_by_id = target.submitted_by_id
        submitted_at = target.submitted_at
        target_updated_at = target.updated_at
        result = reject_article_version(**self.reject_kwargs(target))

        self.assertIsInstance(result, RejectReviewResult)
        article.refresh_from_db()
        target.refresh_from_db()
        successor = ArticleVersion.objects.get(pk=result.successor_draft_id)
        review = ReviewRecord.objects.get(pk=result.review_record_id)

        self.assertEqual(result.kb_no, article.kb_no)
        self.assertEqual(result.article_id, article.pk)
        self.assertEqual(result.rejected_version_id, target.pk)
        self.assertEqual(result.rejected_version_no, 2)
        self.assertEqual(result.rejected_status, VersionStatus.REJECTED)
        self.assertEqual(result.successor_version_no, 3)
        self.assertEqual(result.successor_status, VersionStatus.DRAFT)
        self.assertEqual(result.successor_lock_version, 1)

        self.assertEqual(target.status, VersionStatus.REJECTED)
        self.assertEqual(target.lock_version, 2)
        self.assertEqual(target.submitted_by_id, submitted_by_id)
        self.assertEqual(target.submitted_at, submitted_at)
        self.assertIsNone(target.published_at)
        self.assertGreater(target.updated_at, target_updated_at)

        self.assertEqual(review.article_version_id, target.pk)
        self.assertEqual(review.review_type, ReviewType.CONTENT_REVIEW)
        self.assertEqual(review.decision, ReviewDecision.REJECTED)
        self.assertEqual(review.reviewer_id, self.reviewer.pk)
        self.assertEqual(review.comment, "步骤存在安全风险")

        for field in ("title", "summary", "applicable_scope", "body", "body_plaintext"):
            self.assertEqual(getattr(successor, field), getattr(target, field))
        self.assertEqual(successor.change_summary, "基于被驳回版本 v2 继续编辑")
        self.assertEqual(successor.created_by_id, submitted_by_id)
        self.assertIsNone(successor.submitted_by_id)
        self.assertIsNone(successor.submitted_at)
        self.assertIsNone(successor.published_at)
        self.assertIsNone(successor.restored_from_version_id)

        self.assertEqual(article.latest_working_version_id, successor.pk)
        self.assertEqual(article.current_published_version_id, published.pk)
        self.assertEqual(article.title, "兼容 Published 标题")
        self.assertEqual(article.updated_by_id, self.reviewer.pk)
        published.refresh_from_db()
        self.assertEqual(published.status, VersionStatus.PUBLISHED)

        audit = AuditEvent.objects.get()
        self.assertEqual(audit.event_type, AuditEventType.REVIEW_REJECTED)
        self.assertEqual(audit.actor_id, self.reviewer.pk)
        self.assertEqual(audit.article_id, article.pk)
        self.assertEqual(audit.article_version_id, target.pk)
        self.assertEqual(
            audit.metadata,
            {
                "kb_no": article.kb_no,
                "version_no": 2,
                "space_id": str(article.space_id),
                "review_record_id": str(review.pk),
                "successor_draft_id": str(successor.pk),
                "successor_version_no": 3,
            },
        )
        self.assertNotIn("comment", audit.metadata)

        outbox = WorkflowOutboxEvent.objects.get()
        self.assertEqual(outbox.event_type, AuditEventType.REVIEW_REJECTED)
        self.assertEqual(outbox.dedupe_key, f"review_rejected:{target.pk}")
        self.assertEqual(
            outbox.payload,
            {
                "article_id": str(article.pk),
                "kb_no": article.kb_no,
                "version_id": str(target.pk),
                "version_no": 2,
                "space_id": str(article.space_id),
                "reviewer_id": str(self.reviewer.pk),
                "review_record_id": str(review.pk),
                "successor_draft_id": str(successor.pk),
                "successor_version_no": 3,
                "submitted_by_id": str(submitted_by_id),
            },
        )
        self.assertNotIn("comment", outbox.payload)
        self.assertEqual(outbox.status, WorkflowOutboxStatus.PENDING)
        self.assertEqual(outbox.attempt_count, 0)
        self.assertIsNone(outbox.sent_at)

        idempotency = WorkflowIdempotencyRecord.objects.get()
        self.assertEqual(idempotency.operation, IdempotencyOperation.REJECT)
        self.assertEqual(idempotency.status, IdempotencyStatus.COMPLETED)
        self.assertEqual(idempotency.result_code, REVIEW_REJECTED)
        self.assertEqual(idempotency.request_fingerprint, self.expected_fingerprint(target))
        self.assertEqual(idempotency.result_payload, result.to_payload())

    def test_version_number_uses_article_maximum_not_rejected_version(self):
        article, target, _ = self.make_article(target_version_no=2, high_history_version_no=10)

        result = reject_article_version(**self.reject_kwargs(target))

        successor = ArticleVersion.objects.get(pk=result.successor_draft_id)
        self.assertEqual(successor.version_no, 11)
        self.assertEqual(article.versions.count(), 3)

    def test_comment_and_idempotency_inputs_are_strictly_validated(self):
        article, target, _ = self.make_article()
        invalid_cases = (
            {"version_id": "not-a-uuid"},
            {"version_id": None},
            {"comment": None},
            {"comment": 1},
            {"comment": ""},
            {"comment": "   "},
            {"idempotency_key": None},
            {"idempotency_key": ""},
            {"idempotency_key": " leading"},
            {"idempotency_key": "line\nbreak"},
            {"idempotency_key": "x" * 129},
        )
        before = self.snapshot(article, target)
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                self.assert_reject_error(INVALID_INPUT, target, **overrides)
        self.assert_snapshot_unchanged(before, article, target)

    def test_role_permission_and_active_scope_are_all_required(self):
        denied = (
            self.admin_only,
            self.editor_only,
            self.employee,
            self.staff_only,
            self.superuser_only,
        )
        for actor in denied:
            with self.subTest(actor=actor.username):
                article, target, _ = self.make_article()
                before = self.snapshot(article, target)
                self.assert_reject_error(REJECT_FORBIDDEN, target, actor=actor)
                self.assert_snapshot_unchanged(before, article, target)

        no_scope = User.objects.create_user(username="reject-no-scope")
        no_scope.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name))
        article, target, _ = self.make_article()
        self.assert_reject_error(VERSION_NOT_FOUND_OR_INACCESSIBLE, target, actor=no_scope)

        inactive_scope = User.objects.create_user(username="reject-inactive-scope")
        inactive_scope.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name))
        ReviewerSpaceScope.objects.create(
            reviewer=inactive_scope,
            space=self.space,
            is_active=False,
        )
        article, target, _ = self.make_article()
        self.assert_reject_error(
            VERSION_NOT_FOUND_OR_INACCESSIBLE,
            target,
            actor=inactive_scope,
        )

        other_scope = User.objects.create_user(username="reject-other-scope")
        other_scope.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name))
        ReviewerSpaceScope.objects.create(reviewer=other_scope, space=self.other_space)
        article, target, _ = self.make_article()
        self.assert_reject_error(VERSION_NOT_FOUND_OR_INACCESSIBLE, target, actor=other_scope)

        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        reject_permission = Permission.objects.get(
            content_type__app_label="knowledge",
            codename="reject_articleversion",
        )
        reviewer_group.permissions.remove(reject_permission)
        actor = User.objects.create_user(username="reject-without-permission")
        actor.groups.add(reviewer_group)
        ReviewerSpaceScope.objects.create(reviewer=actor, space=self.space)
        article, target, _ = self.make_article()
        self.assert_reject_error(REJECT_FORBIDDEN, target, actor=actor)

    def test_shared_scope_reviewers_and_multi_role_reviewer_are_authorized(self):
        for actor in (self.reviewer, self.second_reviewer, self.reviewer_admin):
            with self.subTest(actor=actor.username):
                _article, target, _ = self.make_article()
                result = reject_article_version(**self.reject_kwargs(target, actor=actor))
                self.assertEqual(result.rejected_status, VersionStatus.REJECTED)

    def test_active_saved_business_identity_is_required(self):
        _article, target, _ = self.make_article()
        for actor in (
            AnonymousUser(),
            User(username="reject-unsaved"),
            self.inactive_reviewer,
            self.disabled_reviewer,
        ):
            with self.subTest(actor=type(actor).__name__):
                self.assert_reject_error(IDENTITY_DENIED, target, actor=actor)

    def test_creator_and_submitter_cannot_self_review(self):
        for actor, creator, submitter in (
            (self.creator, self.creator, self.submitter),
            (self.submitter, self.creator, self.submitter),
        ):
            reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
            actor.groups.add(reviewer_group)
            ReviewerSpaceScope.objects.get_or_create(reviewer=actor, space=self.space)
            article, target, _ = self.make_article(creator=creator, submitter=submitter)
            before = self.snapshot(article, target)

            self.assert_reject_error(SELF_REVIEW_FORBIDDEN, target, actor=actor)

            self.assert_snapshot_unchanged(before, article, target)

    def test_missing_cross_article_and_non_review_targets_fail_closed(self):
        article, target, _ = self.make_article()
        before = self.snapshot(article, target)
        self.assert_reject_error(
            VERSION_NOT_FOUND_OR_INACCESSIBLE,
            target,
            version_id=uuid4(),
        )
        self.assert_snapshot_unchanged(before, article, target)

        for status in (
            VersionStatus.DRAFT,
            VersionStatus.SAVED,
            VersionStatus.REJECTED,
            VersionStatus.PUBLISHED,
            VersionStatus.SUPERSEDED,
        ):
            with self.subTest(status=status):
                _article, other_target, _ = self.make_article(target_status=status)
                self.assert_reject_error(VERSION_NOT_IN_REVIEW, other_target)

    def test_completed_replay_is_zero_write_and_ignores_outer_whitespace(self):
        article, target, _ = self.make_article()
        kwargs = self.reject_kwargs(target)
        first = reject_article_version(**kwargs)
        successor = ArticleVersion.objects.get(pk=first.successor_draft_id)
        article.refresh_from_db()
        target.refresh_from_db()
        record = WorkflowIdempotencyRecord.objects.get()
        snapshot = {
            "article_updated_at": article.updated_at,
            "target_updated_at": target.updated_at,
            "successor_updated_at": successor.updated_at,
            "idempotency_updated_at": record.updated_at,
            "version_count": ArticleVersion.objects.filter(article=article).count(),
            "review_count": ReviewRecord.objects.count(),
            "audit_count": AuditEvent.objects.count(),
            "outbox_count": WorkflowOutboxEvent.objects.count(),
            "idempotency_count": WorkflowIdempotencyRecord.objects.count(),
        }

        second = reject_article_version(**self.reject_kwargs(target, comment="步骤存在安全风险"))

        self.assertEqual(second, first)
        article.refresh_from_db()
        target.refresh_from_db()
        successor.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(article.updated_at, snapshot["article_updated_at"])
        self.assertEqual(target.updated_at, snapshot["target_updated_at"])
        self.assertEqual(successor.updated_at, snapshot["successor_updated_at"])
        self.assertEqual(record.updated_at, snapshot["idempotency_updated_at"])
        self.assertEqual(
            ArticleVersion.objects.filter(article=article).count(), snapshot["version_count"]
        )
        self.assertEqual(ReviewRecord.objects.count(), snapshot["review_count"])
        self.assertEqual(AuditEvent.objects.count(), snapshot["audit_count"])
        self.assertEqual(WorkflowOutboxEvent.objects.count(), snapshot["outbox_count"])
        self.assertEqual(WorkflowIdempotencyRecord.objects.count(), snapshot["idempotency_count"])

    def test_idempotency_conflict_in_progress_and_different_key_are_safe(self):
        article, target, _ = self.make_article()
        reject_article_version(**self.reject_kwargs(target, idempotency_key="first"))
        completed_snapshot = self.snapshot(article, target)

        self.assert_reject_error(
            IDEMPOTENCY_CONFLICT,
            target,
            idempotency_key="first",
            comment="另一个原因",
        )
        self.assert_reject_error(
            VERSION_NOT_IN_REVIEW,
            target,
            idempotency_key="second",
        )
        self.assert_snapshot_unchanged(completed_snapshot, article, target)

        _article, in_progress_target, _ = self.make_article()
        WorkflowIdempotencyRecord.objects.create(
            actor=self.reviewer,
            operation=IdempotencyOperation.REJECT,
            key="in-progress",
            request_fingerprint=self.expected_fingerprint(in_progress_target),
        )
        self.assert_reject_error(
            IDEMPOTENCY_IN_PROGRESS,
            in_progress_target,
            idempotency_key="in-progress",
        )

    def test_scope_revocation_blocks_completed_replay_without_writes(self):
        article, target, _ = self.make_article()
        kwargs = self.reject_kwargs(target, idempotency_key="revoked-replay")
        reject_article_version(**kwargs)
        before = self.snapshot(article, target)
        ReviewerSpaceScope.objects.filter(reviewer=self.reviewer, space=self.space).update(
            is_active=False
        )

        self.assert_reject_error(VERSION_NOT_FOUND_OR_INACCESSIBLE, target, **kwargs)

        self.assert_snapshot_unchanged(before, article, target)

    def test_existing_draft_and_three_failure_points_roll_back_everything(self):
        failure_cases = (
            ("draft", "apps.workflow.services._create_successor_draft"),
            ("audit", "apps.workflow.services.AuditEvent.objects.create"),
            ("outbox", "apps.workflow.services.WorkflowOutboxEvent.objects.create"),
        )
        for name, patch_target in failure_cases:
            with self.subTest(name=name):
                article, target, _ = self.make_article()
                before = self.snapshot(article, target)
                with mock.patch(
                    patch_target,
                    side_effect=DatabaseError("secret database detail"),
                ):
                    error = self.assert_reject_error(
                        WORKFLOW_UNAVAILABLE,
                        target,
                        idempotency_key=f"failure-{name}",
                    )
                self.assertNotIn("secret", str(error).lower())
                self.assert_snapshot_unchanged(before, article, target)

        article, target, _ = self.make_article()
        existing_draft = ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status=VersionStatus.DRAFT,
            title="异常既有草稿",
            summary="异常既有草稿",
            change_summary="异常既有草稿",
            created_by=self.submitter,
        )
        Article.objects.filter(pk=article.pk).update(latest_working_version=existing_draft)
        before = self.snapshot(article, target)
        self.assert_reject_error(WORKFLOW_UNAVAILABLE, target, idempotency_key="draft-conflict")
        self.assert_snapshot_unchanged(before, article, target)

    def test_published_and_unpublished_employee_search_isolation(self):
        published_article, published_target, published = self.make_article(published=True)
        published_result = reject_article_version(**self.reject_kwargs(published_target))
        published_article.refresh_from_db()
        published.refresh_from_db()
        self.assertEqual(published_article.current_published_version_id, published.pk)
        self.assertEqual(published.status, VersionStatus.PUBLISHED)
        detail = get_employee_article_detail(self.employee, published_article.kb_no)
        self.assertIsNotNone(detail)
        self.assertEqual(detail.title, "正式 Published 标题")
        self.assertTrue(
            search_employee_articles(self.employee, "正式内容唯一关键词")
            .filter(pk=published_article.pk)
            .exists()
        )
        self.assertFalse(
            search_employee_articles(self.employee, "待审核内容唯一关键词")
            .filter(pk=published_article.pk)
            .exists()
        )
        self.assertIsNotNone(published_result.successor_draft_id)

        unpublished_article, unpublished_target, _ = self.make_article()
        reject_article_version(**self.reject_kwargs(unpublished_target))
        self.assertFalse(
            employee_visible_articles(self.employee).filter(pk=unpublished_article.pk).exists()
        )
        self.assertIsNone(get_employee_article_detail(self.employee, unpublished_article.kb_no))
        self.assertFalse(
            search_employee_articles(self.employee, "待审核内容唯一关键词")
            .filter(pk=unpublished_article.pk)
            .exists()
        )

    def test_successor_is_editable_rejected_is_immutable_and_history_is_ordered(self):
        article, target, _ = self.make_article(
            creator=self.submitter,
            submitter=self.submitter,
        )
        result = reject_article_version(**self.reject_kwargs(target))
        successor = ArticleVersion.objects.get(pk=result.successor_draft_id)
        write_kwargs = {
            "actor": self.submitter,
            "article": article,
            "draft_id": successor.pk,
            "expected_lock_version": 1,
            "title": "驳回后已修订",
            "summary": "驳回后摘要",
            "applicable_scope": {"systems": ["Windows 11"]},
            "body_text": "驳回后正文",
            "change_summary": "根据审核意见修订",
        }

        updated = autosave_draft(**write_kwargs)

        self.assertEqual(updated.lock_version, 2)
        self.assertEqual(updated.title, "驳回后已修订")
        stale_kwargs = {**write_kwargs, "draft_id": target.pk, "expected_lock_version": 2}
        for writer in (autosave_draft, manual_save_draft):
            with self.subTest(writer=writer.__name__), self.assertRaises(ArticleVersionWriteError):
                writer(**stale_kwargs)
        target.refresh_from_db()
        self.assertEqual(target.status, VersionStatus.REJECTED)
        self.assertEqual(target.title, "被驳回版本标题")
        history = get_article_version_history(actor=self.submitter, article=article)
        self.assertEqual(
            list(history.values_list("version_no", "status")),
            [(2, VersionStatus.DRAFT), (1, VersionStatus.REJECTED)],
        )

    def test_article_is_locked_before_target_version(self):
        _article, target, _ = self.make_article()
        lock_order = []
        original_select_for_update = QuerySet.select_for_update

        def record_lock(queryset, *args, **kwargs):
            lock_order.append(queryset.model)
            return original_select_for_update(queryset, *args, **kwargs)

        with mock.patch.object(
            QuerySet,
            "select_for_update",
            autospec=True,
            side_effect=record_lock,
        ):
            reject_article_version(**self.reject_kwargs(target))

        self.assertLess(lock_order.index(Article), lock_order.index(ArticleVersion))
