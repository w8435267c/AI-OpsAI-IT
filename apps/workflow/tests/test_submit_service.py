"""Task 13-03：DRAFT → IN_REVIEW 正式提交审核 Service。"""

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
    ReviewerSpaceScope,
    ReviewRecord,
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
    ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
    DRAFT_CONFLICT,
    DRAFT_NOT_CURRENT,
    IDEMPOTENCY_CONFLICT,
    IDEMPOTENCY_IN_PROGRESS,
    IDENTITY_DENIED,
    INVALID_INPUT,
    REVIEW_SUBMITTED,
    SUBMIT_FORBIDDEN,
    WORKFLOW_UNAVAILABLE,
    SubmitArticleForReviewError,
    SubmitReviewResult,
    submit_article_for_review,
)


class SubmitArticleForReviewServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0)
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)

        cls.article_owner = User.objects.create_user(username="submit-article-owner")
        cls.article_owner.groups.add(editor_group)
        cls.space_owner = User.objects.create_user(username="submit-space-owner")
        cls.space_owner.groups.add(editor_group)
        cls.other_editor = User.objects.create_user(username="submit-other-editor")
        cls.other_editor.groups.add(editor_group)
        cls.admin = User.objects.create_user(username="submit-admin")
        cls.admin.groups.add(admin_group)
        cls.reviewer = User.objects.create_user(username="submit-reviewer")
        cls.reviewer.groups.add(reviewer_group)
        cls.reviewer_editor = User.objects.create_user(username="submit-reviewer-editor")
        cls.reviewer_editor.groups.add(reviewer_group, editor_group)
        cls.employee = User.objects.create_user(username="submit-employee")
        cls.staff_only = User.objects.create_user(username="submit-staff", is_staff=True)
        cls.superuser_only = User.objects.create_user(
            username="submit-superuser",
            is_staff=True,
            is_superuser=True,
        )
        cls.inactive_editor = User.objects.create_user(
            username="submit-inactive-editor",
            is_active=False,
        )
        cls.inactive_editor.groups.add(editor_group)
        cls.disabled_editor = User.objects.create_user(
            username="submit-disabled-editor",
            account_status=AccountStatus.DISABLED,
        )
        cls.disabled_editor.groups.add(editor_group)

        cls.space = KnowledgeSpace.objects.create(
            code="submit-space",
            name="Task 13 Submit 空间",
            space_type="employee",
            owner=cls.space_owner,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="submit-category",
            name="Task 13 Submit 分类",
        )

    def setUp(self):
        self._sequence = 0

    def make_article(
        self,
        *,
        owner=None,
        published=False,
        title="兼容发布标题",
        draft_title="待审核草稿标题",
    ):
        self._sequence += 1
        owner = owner or self.article_owner
        article = Article.objects.create(
            kb_no=f"KB-{130000 + self._sequence:06d}",
            title=title,
            space=self.space,
            category=self.category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            owner=owner,
            created_by=owner,
            updated_by=self.space_owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )
        published_version = None
        next_version_no = 1
        if published:
            published_version = ArticleVersion.objects.create(
                article=article,
                version_no=1,
                status=VersionStatus.PUBLISHED,
                lock_version=3,
                title="正式 Published 标题",
                summary="正式 Published 摘要",
                applicable_scope={"published": True},
                body={"format": "opsai.plaintext/1", "text": "正式 Published 正文唯一关键词"},
                body_plaintext="正式 Published 正文唯一关键词",
                change_summary="既有正式版本",
                created_by=owner,
                submitted_by=owner,
                submitted_at=timezone.now() - timedelta(days=2),
                published_at=timezone.now() - timedelta(days=1),
            )
            next_version_no = 2
        draft = ArticleVersion.objects.create(
            article=article,
            version_no=next_version_no,
            status=VersionStatus.DRAFT,
            lock_version=1,
            title=draft_title,
            summary="待审核草稿摘要",
            applicable_scope={"systems": ["Windows 11"]},
            body={"format": "opsai.plaintext/1", "text": "待审核草稿正文唯一关键词"},
            body_plaintext="待审核草稿正文唯一关键词",
            change_summary="准备提交审核",
            created_by=owner,
        )
        Article.objects.filter(pk=article.pk).update(
            current_published_version=published_version,
            latest_working_version=draft,
        )
        article.refresh_from_db()
        return article, draft, published_version

    def submit_kwargs(self, article, draft, **overrides):
        values = {
            "actor": self.article_owner,
            "kb_no": article.kb_no,
            "draft_id": draft.pk,
            "expected_lock_version": draft.lock_version,
            "idempotency_key": f"submit-{article.kb_no.lower()}",
        }
        values.update(overrides)
        return values

    def assert_submit_error(self, code, article, draft, **overrides):
        with self.assertRaises(SubmitArticleForReviewError) as caught:
            submit_article_for_review(**self.submit_kwargs(article, draft, **overrides))
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def expected_fingerprint(self, article, draft, expected_lock_version=1):
        canonical = json.dumps(
            {
                "draft_id": str(draft.pk),
                "expected_lock_version": expected_lock_version,
                "kb_no": article.kb_no,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def assert_submit_rolled_back(self, article, draft, published_version=None):
        article.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(draft.status, VersionStatus.DRAFT)
        self.assertEqual(draft.lock_version, 1)
        self.assertIsNone(draft.submitted_by_id)
        self.assertIsNone(draft.submitted_at)
        self.assertIsNone(draft.published_at)
        self.assertEqual(article.latest_working_version_id, draft.pk)
        self.assertEqual(
            article.current_published_version_id,
            published_version.pk if published_version else None,
        )
        self.assertEqual(AuditEvent.objects.count(), 0)
        self.assertEqual(WorkflowOutboxEvent.objects.count(), 0)
        self.assertEqual(WorkflowIdempotencyRecord.objects.count(), 0)
        self.assertEqual(ReviewRecord.objects.count(), 0)

    def test_success_transitions_current_draft_and_writes_exact_transaction_artifacts(self):
        article, draft, published = self.make_article(published=True)
        article_before = {
            "title": article.title,
            "space_id": article.space_id,
            "category_id": article.category_id,
            "owner_id": article.owner_id,
            "current_published_version_id": article.current_published_version_id,
        }
        content_before = {
            field: getattr(draft, field)
            for field in (
                "title",
                "summary",
                "applicable_scope",
                "body",
                "body_plaintext",
                "change_summary",
                "restored_from_version_id",
                "created_by_id",
                "version_no",
            )
        }
        version_count = ArticleVersion.objects.filter(article=article).count()

        result = submit_article_for_review(**self.submit_kwargs(article, draft))

        self.assertIsInstance(result, SubmitReviewResult)
        article.refresh_from_db()
        draft.refresh_from_db()
        published.refresh_from_db()
        self.assertEqual(result.kb_no, article.kb_no)
        self.assertEqual(result.article_id, article.pk)
        self.assertEqual(result.version_id, draft.pk)
        self.assertEqual(result.version_no, 2)
        self.assertEqual(result.status, VersionStatus.IN_REVIEW)
        self.assertEqual(result.lock_version, 2)
        self.assertEqual(result.submitted_at, draft.submitted_at)
        self.assertEqual(draft.status, VersionStatus.IN_REVIEW)
        self.assertEqual(draft.submitted_by, self.article_owner)
        self.assertIsNotNone(draft.submitted_at)
        self.assertEqual(draft.lock_version, 2)
        self.assertIsNone(draft.published_at)
        self.assertEqual(
            {field: getattr(draft, field) for field in content_before},
            content_before,
        )
        self.assertEqual(ArticleVersion.objects.filter(article=article).count(), version_count)
        self.assertIsNone(article.latest_working_version_id)
        self.assertEqual(article.updated_by_id, self.article_owner.pk)
        self.assertEqual(
            {
                "title": article.title,
                "space_id": article.space_id,
                "category_id": article.category_id,
                "owner_id": article.owner_id,
                "current_published_version_id": article.current_published_version_id,
            },
            article_before,
        )
        self.assertEqual(published.status, VersionStatus.PUBLISHED)

        audit = AuditEvent.objects.get()
        self.assertEqual(audit.event_type, AuditEventType.REVIEW_SUBMITTED)
        self.assertEqual(audit.actor, self.article_owner)
        self.assertEqual(audit.article, article)
        self.assertEqual(audit.article_version, draft)
        self.assertEqual(
            audit.metadata,
            {
                "kb_no": article.kb_no,
                "version_no": 2,
                "space_id": str(article.space_id),
                "lock_version": 2,
            },
        )

        outbox = WorkflowOutboxEvent.objects.get()
        self.assertEqual(outbox.event_type, AuditEventType.REVIEW_SUBMITTED)
        self.assertEqual(outbox.dedupe_key, f"review_submitted:{draft.pk}")
        self.assertEqual(
            outbox.payload,
            {
                "kb_no": article.kb_no,
                "article_id": str(article.pk),
                "version_id": str(draft.pk),
                "version_no": 2,
                "space_id": str(article.space_id),
                "actor_id": str(self.article_owner.pk),
            },
        )
        self.assertEqual(outbox.status, WorkflowOutboxStatus.PENDING)
        self.assertEqual(outbox.attempt_count, 0)
        self.assertIsNone(outbox.sent_at)

        idempotency = WorkflowIdempotencyRecord.objects.get()
        self.assertEqual(idempotency.operation, IdempotencyOperation.SUBMIT)
        self.assertEqual(idempotency.status, IdempotencyStatus.COMPLETED)
        self.assertEqual(idempotency.result_code, REVIEW_SUBMITTED)
        self.assertEqual(
            idempotency.request_fingerprint,
            self.expected_fingerprint(article, draft),
        )
        self.assertEqual(idempotency.result_payload["version_id"], str(draft.pk))
        self.assertEqual(ReviewRecord.objects.count(), 0)

    def test_submit_accepts_no_content_snapshot_parameters(self):
        article, draft, _published = self.make_article()
        for field in (
            "title",
            "summary",
            "body",
            "body_plaintext",
            "applicable_scope",
            "change_summary",
        ):
            with self.subTest(field=field), self.assertRaises(TypeError):
                submit_article_for_review(
                    **self.submit_kwargs(article, draft),
                    **{field: "不得由 Submit 接收"},
                )
        self.assert_submit_rolled_back(article, draft)

    def test_owner_space_owner_admin_and_editor_reviewer_are_authorized(self):
        cases = (
            (self.article_owner, self.article_owner),
            (self.space_owner, self.article_owner),
            (self.admin, self.other_editor),
            (self.reviewer_editor, self.reviewer_editor),
        )
        for actor, owner in cases:
            with self.subTest(actor=actor.username):
                article, draft, _published = self.make_article(owner=owner)
                result = submit_article_for_review(
                    **self.submit_kwargs(article, draft, actor=actor)
                )
                self.assertEqual(result.status, VersionStatus.IN_REVIEW)

    def test_denied_identity_role_and_object_access_leave_no_writes(self):
        role_denied = (self.reviewer, self.employee, self.staff_only, self.superuser_only)
        for actor in role_denied:
            with self.subTest(actor=actor.username):
                article, draft, _published = self.make_article()
                self.assert_submit_error(SUBMIT_FORBIDDEN, article, draft, actor=actor)
                self.assert_submit_rolled_back(article, draft)

        for actor in (self.inactive_editor, self.disabled_editor):
            with self.subTest(actor=actor.username):
                article, draft, _published = self.make_article(owner=actor)
                self.assert_submit_error(IDENTITY_DENIED, article, draft, actor=actor)
                self.assert_submit_rolled_back(article, draft)

        article, draft, _published = self.make_article()
        self.assert_submit_error(
            ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
            article,
            draft,
            actor=self.other_editor,
        )
        self.assert_submit_rolled_back(article, draft)

    def test_authenticated_saved_and_active_business_identity_is_required(self):
        article, draft, _published = self.make_article()
        for actor in (AnonymousUser(), User(username="submit-unsaved-editor")):
            with self.subTest(actor=type(actor).__name__):
                self.assert_submit_error(IDENTITY_DENIED, article, draft, actor=actor)
        self.assert_submit_rolled_back(article, draft)

    def test_inactive_space_fails_closed_as_inaccessible(self):
        article, draft, _published = self.make_article()
        KnowledgeSpace.objects.filter(pk=self.space.pk).update(is_active=False)

        self.assert_submit_error(
            ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
            article,
            draft,
        )

        self.assert_submit_rolled_back(article, draft)

    def test_submit_action_permission_is_required_in_addition_to_editor_role(self):
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        editor_group.permissions.remove(
            Permission.objects.get(
                content_type__app_label="knowledge",
                codename="submit_articleversion",
            )
        )
        actor = User.objects.create_user(username="submit-editor-without-action")
        actor.groups.add(editor_group)
        article, draft, _published = self.make_article(owner=actor)

        self.assert_submit_error(SUBMIT_FORBIDDEN, article, draft, actor=actor)
        self.assert_submit_rolled_back(article, draft)

    def test_reviewer_scope_is_not_required_for_submit(self):
        article, draft, _published = self.make_article()
        self.assertFalse(ReviewerSpaceScope.objects.filter(reviewer=self.article_owner).exists())

        result = submit_article_for_review(**self.submit_kwargs(article, draft))

        self.assertEqual(result.status, VersionStatus.IN_REVIEW)

    def test_missing_and_inaccessible_article_are_indistinguishable(self):
        article, draft, _published = self.make_article()
        denied = self.assert_submit_error(
            ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
            article,
            draft,
            actor=self.other_editor,
        )
        missing = self.assert_submit_error(
            ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
            article,
            draft,
            kb_no="KB-999999",
        )
        self.assertEqual(denied.public_message, missing.public_message)

    def test_strict_input_validation_rejects_invalid_values_before_write(self):
        article, draft, _published = self.make_article()
        invalid_cases = (
            {"kb_no": None},
            {"kb_no": "KB-1"},
            {"kb_no": " KB-130001"},
            {"draft_id": "not-a-uuid"},
            {"expected_lock_version": 0},
            {"expected_lock_version": -1},
            {"expected_lock_version": True},
            {"expected_lock_version": 1.0},
            {"expected_lock_version": "1"},
            {"idempotency_key": None},
            {"idempotency_key": ""},
            {"idempotency_key": "   "},
            {"idempotency_key": " leading-space"},
            {"idempotency_key": "line\nbreak"},
            {"idempotency_key": "x" * 129},
        )
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                self.assert_submit_error(INVALID_INPUT, article, draft, **overrides)
        self.assert_submit_rolled_back(article, draft)

    def test_draft_and_lock_cas_failures_leave_no_writes(self):
        article, draft, _published = self.make_article()
        other_article, other_draft, _ = self.make_article()
        saved = ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status=VersionStatus.SAVED,
            lock_version=1,
            title="非当前历史",
            summary="非当前历史摘要",
            change_summary="非当前历史",
            created_by=self.article_owner,
        )
        cases = (
            (DRAFT_NOT_CURRENT, {"draft_id": uuid4()}),
            (DRAFT_NOT_CURRENT, {"draft_id": other_draft.pk}),
            (DRAFT_NOT_CURRENT, {"draft_id": saved.pk}),
            (DRAFT_CONFLICT, {"expected_lock_version": 2}),
        )
        for index, (code, overrides) in enumerate(cases):
            with self.subTest(code=code, overrides=overrides):
                self.assert_submit_error(
                    code,
                    article,
                    draft,
                    idempotency_key=f"cas-{index}",
                    **overrides,
                )
        self.assert_submit_rolled_back(article, draft)
        self.assertEqual(other_article.latest_working_version_id, other_draft.pk)

        Article.objects.filter(pk=article.pk).update(latest_working_version=None)
        self.assert_submit_error(
            DRAFT_NOT_CURRENT,
            article,
            draft,
            idempotency_key="latest-none",
        )
        self.assertEqual(WorkflowIdempotencyRecord.objects.count(), 0)

    def test_fingerprint_is_stable_canonical_sha256(self):
        article, draft, _published = self.make_article()
        submit_article_for_review(**self.submit_kwargs(article, draft))

        record = WorkflowIdempotencyRecord.objects.get()
        self.assertEqual(record.request_fingerprint, self.expected_fingerprint(article, draft))
        self.assertEqual(len(record.request_fingerprint), 64)

    def test_completed_replay_is_read_only_and_returns_equivalent_result(self):
        article, draft, _published = self.make_article()
        kwargs = self.submit_kwargs(article, draft)
        first = submit_article_for_review(**kwargs)
        article.refresh_from_db()
        draft.refresh_from_db()
        record = WorkflowIdempotencyRecord.objects.get()
        snapshot = {
            "article_updated_at": article.updated_at,
            "version_updated_at": draft.updated_at,
            "lock_version": draft.lock_version,
            "idempotency_updated_at": record.updated_at,
            "audit_count": AuditEvent.objects.count(),
            "outbox_count": WorkflowOutboxEvent.objects.count(),
            "idempotency_count": WorkflowIdempotencyRecord.objects.count(),
            "review_count": ReviewRecord.objects.count(),
            "version_count": ArticleVersion.objects.filter(article=article).count(),
        }

        second = submit_article_for_review(**kwargs)

        self.assertEqual(second, first)
        article.refresh_from_db()
        draft.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(article.updated_at, snapshot["article_updated_at"])
        self.assertEqual(draft.updated_at, snapshot["version_updated_at"])
        self.assertEqual(draft.lock_version, snapshot["lock_version"])
        self.assertEqual(record.updated_at, snapshot["idempotency_updated_at"])
        self.assertEqual(AuditEvent.objects.count(), snapshot["audit_count"])
        self.assertEqual(WorkflowOutboxEvent.objects.count(), snapshot["outbox_count"])
        self.assertEqual(WorkflowIdempotencyRecord.objects.count(), snapshot["idempotency_count"])
        self.assertEqual(ReviewRecord.objects.count(), snapshot["review_count"])
        self.assertEqual(
            ArticleVersion.objects.filter(article=article).count(), snapshot["version_count"]
        )

    def test_same_key_different_fingerprint_wins_over_draft_state_error(self):
        article, draft, _published = self.make_article()
        kwargs = self.submit_kwargs(article, draft, idempotency_key="fingerprint-conflict")
        submit_article_for_review(**kwargs)

        self.assert_submit_error(
            IDEMPOTENCY_CONFLICT,
            article,
            draft,
            idempotency_key="fingerprint-conflict",
            expected_lock_version=2,
        )
        self.assertEqual(AuditEvent.objects.count(), 1)
        self.assertEqual(WorkflowOutboxEvent.objects.count(), 1)
        self.assertEqual(WorkflowIdempotencyRecord.objects.count(), 1)

    def test_existing_in_progress_record_fails_without_business_writes(self):
        article, draft, _published = self.make_article()
        WorkflowIdempotencyRecord.objects.create(
            actor=self.article_owner,
            operation=IdempotencyOperation.SUBMIT,
            key="in-progress",
            request_fingerprint=self.expected_fingerprint(article, draft),
        )

        self.assert_submit_error(
            IDEMPOTENCY_IN_PROGRESS,
            article,
            draft,
            idempotency_key="in-progress",
        )
        article.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(draft.status, VersionStatus.DRAFT)
        self.assertEqual(article.latest_working_version_id, draft.pk)
        self.assertEqual(AuditEvent.objects.count(), 0)
        self.assertEqual(WorkflowOutboxEvent.objects.count(), 0)

    def test_same_key_is_independent_for_different_actor_and_article(self):
        first_article, first_draft, _ = self.make_article(owner=self.article_owner)
        second_article, second_draft, _ = self.make_article(owner=self.reviewer_editor)

        first = submit_article_for_review(
            **self.submit_kwargs(
                first_article,
                first_draft,
                actor=self.article_owner,
                idempotency_key="shared-key",
            )
        )
        second = submit_article_for_review(
            **self.submit_kwargs(
                second_article,
                second_draft,
                actor=self.reviewer_editor,
                idempotency_key="shared-key",
            )
        )

        self.assertNotEqual(first.article_id, second.article_id)
        self.assertEqual(WorkflowIdempotencyRecord.objects.count(), 2)
        self.assertEqual(AuditEvent.objects.count(), 2)
        self.assertEqual(WorkflowOutboxEvent.objects.count(), 2)

    def test_different_key_cannot_resubmit_already_in_review_version(self):
        article, draft, _published = self.make_article()
        submit_article_for_review(**self.submit_kwargs(article, draft, idempotency_key="first"))

        self.assert_submit_error(
            DRAFT_NOT_CURRENT,
            article,
            draft,
            idempotency_key="second",
        )
        self.assertEqual(AuditEvent.objects.count(), 1)
        self.assertEqual(WorkflowOutboxEvent.objects.count(), 1)
        self.assertEqual(WorkflowIdempotencyRecord.objects.count(), 1)

    def test_permission_revocation_blocks_completed_replay(self):
        article, draft, _published = self.make_article()
        kwargs = self.submit_kwargs(article, draft, idempotency_key="revoked-replay")
        submit_article_for_review(**kwargs)
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        self.article_owner.groups.remove(editor_group)

        with self.assertRaises(SubmitArticleForReviewError) as caught:
            submit_article_for_review(**kwargs)

        self.assertEqual(caught.exception.code, SUBMIT_FORBIDDEN)
        self.assertEqual(AuditEvent.objects.count(), 1)
        self.assertEqual(WorkflowOutboxEvent.objects.count(), 1)

    def test_outbox_failure_rolls_back_everything(self):
        article, draft, published = self.make_article(published=True)
        with mock.patch.object(
            WorkflowOutboxEvent.objects,
            "create",
            side_effect=DatabaseError("secret database detail"),
        ):
            error = self.assert_submit_error(WORKFLOW_UNAVAILABLE, article, draft)

        self.assertNotIn("secret", str(error).lower())
        self.assert_submit_rolled_back(article, draft, published)

    def test_audit_failure_rolls_back_everything(self):
        article, draft, published = self.make_article(published=True)
        with mock.patch.object(
            AuditEvent.objects,
            "create",
            side_effect=DatabaseError("secret database detail"),
        ):
            self.assert_submit_error(WORKFLOW_UNAVAILABLE, article, draft)

        self.assert_submit_rolled_back(article, draft, published)

    def test_unpublished_submit_remains_invisible_to_employee_and_search(self):
        article, draft, _published = self.make_article(draft_title="仅审核中可见关键词")

        submit_article_for_review(**self.submit_kwargs(article, draft))

        self.assertFalse(employee_visible_articles(self.employee).filter(pk=article.pk).exists())
        self.assertIsNone(get_employee_article_detail(self.employee, article.kb_no))
        self.assertFalse(
            search_employee_articles(self.employee, "仅审核中可见关键词")
            .filter(pk=article.pk)
            .exists()
        )

    def test_existing_published_content_remains_employee_authority(self):
        article, draft, published = self.make_article(published=True)

        submit_article_for_review(**self.submit_kwargs(article, draft))

        article.refresh_from_db()
        published.refresh_from_db()
        self.assertEqual(article.current_published_version_id, published.pk)
        self.assertEqual(published.status, VersionStatus.PUBLISHED)
        detail = get_employee_article_detail(self.employee, article.kb_no)
        self.assertIsNotNone(detail)
        self.assertEqual(detail.title, "正式 Published 标题")
        self.assertEqual(detail.body_text, "正式 Published 正文唯一关键词")
        self.assertTrue(
            search_employee_articles(self.employee, "正式 Published 正文唯一关键词")
            .filter(pk=article.pk)
            .exists()
        )
        self.assertFalse(
            search_employee_articles(self.employee, "待审核草稿正文唯一关键词")
            .filter(pk=article.pk)
            .exists()
        )

    def test_old_autosave_and_manual_save_tokens_fail_after_submit(self):
        article, draft, _published = self.make_article()
        submit_article_for_review(**self.submit_kwargs(article, draft))
        write_kwargs = {
            "actor": self.article_owner,
            "article": article,
            "draft_id": draft.pk,
            "expected_lock_version": 1,
            "title": "旧窗口标题",
            "summary": "旧窗口摘要",
            "applicable_scope": {"window": "stale"},
            "body_text": "旧窗口正文",
            "change_summary": "旧窗口写入",
        }

        for writer in (autosave_draft, manual_save_draft):
            with self.subTest(writer=writer.__name__), self.assertRaises(ArticleVersionWriteError):
                writer(**write_kwargs)

        article.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(draft.status, VersionStatus.IN_REVIEW)
        self.assertEqual(draft.lock_version, 2)
        self.assertIsNone(article.latest_working_version_id)
        history = get_article_version_history(actor=self.article_owner, article=article)
        self.assertEqual(list(history.values_list("status", flat=True)), [VersionStatus.IN_REVIEW])

    def test_article_is_locked_before_draft(self):
        article, draft, _published = self.make_article()
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
            submit_article_for_review(**self.submit_kwargs(article, draft))

        self.assertLess(lock_order.index(Article), lock_order.index(ArticleVersion))
