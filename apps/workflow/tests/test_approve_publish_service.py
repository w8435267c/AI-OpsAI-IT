"""Task 13-05：IN_REVIEW 原子批准、首次发布与重新发布 Service。"""

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
    WorkflowEventType,
    WorkflowIdempotencyRecord,
    WorkflowOutboxEvent,
    WorkflowOutboxStatus,
)
from apps.workflow.services import (
    APPROVE_PUBLISH_FORBIDDEN,
    IDEMPOTENCY_CONFLICT,
    IDEMPOTENCY_IN_PROGRESS,
    IDENTITY_DENIED,
    INVALID_INPUT,
    PUBLISH_STATE_INCONSISTENT,
    REVIEW_APPROVED_PUBLISHED,
    SELF_REVIEW_FORBIDDEN,
    VERSION_NOT_FOUND_OR_INACCESSIBLE,
    VERSION_NOT_IN_REVIEW,
    WORKFLOW_UNAVAILABLE,
    ApprovePublishArticleVersionError,
    ApprovePublishResult,
    approve_and_publish_article_version,
)


class ApproveAndPublishArticleVersionServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0)
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)

        cls.creator = User.objects.create_user(username="approve-creator")
        cls.creator.groups.add(editor_group)
        cls.submitter = User.objects.create_user(username="approve-submitter")
        cls.submitter.groups.add(editor_group)
        cls.reviewer = User.objects.create_user(username="approve-reviewer")
        cls.reviewer.groups.add(reviewer_group)
        cls.second_reviewer = User.objects.create_user(username="approve-second-reviewer")
        cls.second_reviewer.groups.add(reviewer_group)
        cls.reviewer_admin = User.objects.create_user(username="approve-reviewer-admin")
        cls.reviewer_admin.groups.add(reviewer_group, admin_group)
        cls.admin_only = User.objects.create_user(username="approve-admin-only")
        cls.admin_only.groups.add(admin_group)
        cls.editor_only = User.objects.create_user(username="approve-editor-only")
        cls.editor_only.groups.add(editor_group)
        cls.employee = User.objects.create_user(username="approve-employee")
        cls.staff_only = User.objects.create_user(username="approve-staff", is_staff=True)
        cls.superuser_only = User.objects.create_user(
            username="approve-superuser",
            is_staff=True,
            is_superuser=True,
        )
        cls.inactive_reviewer = User.objects.create_user(
            username="approve-inactive-reviewer",
            is_active=False,
        )
        cls.inactive_reviewer.groups.add(reviewer_group)
        cls.disabled_reviewer = User.objects.create_user(
            username="approve-disabled-reviewer",
            account_status=AccountStatus.DISABLED,
        )
        cls.disabled_reviewer.groups.add(reviewer_group)

        cls.space_owner = User.objects.create_user(username="approve-space-owner")
        cls.space = KnowledgeSpace.objects.create(
            code="approve-space",
            name="Task 13 Approve 空间",
            space_type="employee",
            owner=cls.space_owner,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="approve-category",
            name="Task 13 Approve 分类",
        )
        cls.other_space = KnowledgeSpace.objects.create(
            code="approve-other-space",
            name="Task 13 Approve 其他空间",
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
        effective_at=None,
        target_status=VersionStatus.IN_REVIEW,
        target_version_no=None,
        high_history_version_no=None,
    ):
        self._sequence += 1
        creator = creator or self.creator
        submitter = submitter or self.submitter
        article = Article.objects.create(
            kb_no=f"KB-{150000 + self._sequence:06d}",
            title="旧兼容标题",
            space=self.space,
            category=self.category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            owner=creator,
            article_status="active",
            effective_at=effective_at,
            created_by=creator,
            updated_by=self.space_owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )
        old_published = None
        if published:
            old_published = ArticleVersion.objects.create(
                article=article,
                version_no=1,
                status=VersionStatus.PUBLISHED,
                lock_version=4,
                title="旧正式标题",
                summary="旧正式摘要",
                applicable_scope={"published": "old"},
                body={"format": "opsai.plaintext/1", "text": "OLDKEY旧正式正文"},
                body_plaintext="OLDKEY旧正式正文",
                change_summary="旧正式版本",
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
            title="新正式标题",
            summary="新正式摘要",
            applicable_scope={"systems": ["Windows 11"]},
            body={"format": "opsai.plaintext/1", "text": "NEWKEY新正式正文"},
            body_plaintext="NEWKEY新正式正文",
            change_summary="提交发布的新版本",
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
                lock_version=7,
                title="高水位历史",
                summary="高水位历史摘要",
                change_summary="高水位历史",
                created_by=creator,
            )
        Article.objects.filter(pk=article.pk).update(
            current_published_version=old_published,
            latest_working_version=None,
        )
        article.refresh_from_db()
        return article, target, old_published

    def approve_kwargs(self, target, **overrides):
        values = {
            "actor": self.reviewer,
            "version_id": target.pk,
            "comment": "  内容准确，可以发布  ",
            "idempotency_key": f"approve-{target.pk}",
        }
        values.update(overrides)
        return values

    def expected_fingerprint(self, target, comment="内容准确，可以发布"):
        canonical = json.dumps(
            {"comment": comment, "version_id": str(target.pk)},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def assert_approve_error(self, code, target, **overrides):
        with self.assertRaises(ApprovePublishArticleVersionError) as caught:
            approve_and_publish_article_version(**self.approve_kwargs(target, **overrides))
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def business_snapshot(self, article):
        article.refresh_from_db()
        versions = list(
            ArticleVersion.objects.filter(article=article)
            .order_by("version_no")
            .values(
                "id",
                "version_no",
                "status",
                "lock_version",
                "title",
                "summary",
                "applicable_scope",
                "body",
                "body_plaintext",
                "change_summary",
                "created_by_id",
                "submitted_by_id",
                "submitted_at",
                "published_at",
                "restored_from_version_id",
                "updated_at",
            )
        )
        return {
            "article": {
                "title": article.title,
                "current_published_version_id": article.current_published_version_id,
                "latest_working_version_id": article.latest_working_version_id,
                "updated_by_id": article.updated_by_id,
                "updated_at": article.updated_at,
                "effective_at": article.effective_at,
                "space_id": article.space_id,
                "category_id": article.category_id,
                "owner_id": article.owner_id,
                "article_type": article.article_type,
                "audience_policy": article.audience_policy,
                "article_status": article.article_status,
                "review_due_at": article.review_due_at,
            },
            "versions": versions,
            "review_count": ReviewRecord.objects.count(),
            "audit_count": AuditEvent.objects.count(),
            "outbox_count": WorkflowOutboxEvent.objects.count(),
            "idempotency_count": WorkflowIdempotencyRecord.objects.count(),
        }

    def test_first_publish_creates_exact_atomic_artifacts(self):
        article, target, old = self.make_article()
        self.assertIsNone(old)
        before_version_count = article.versions.count()
        target_values = {
            field: getattr(target, field)
            for field in (
                "version_no",
                "lock_version",
                "title",
                "summary",
                "applicable_scope",
                "body",
                "body_plaintext",
                "change_summary",
                "created_by_id",
                "submitted_by_id",
                "submitted_at",
            )
        }

        result = approve_and_publish_article_version(**self.approve_kwargs(target))

        self.assertIsInstance(result, ApprovePublishResult)
        article.refresh_from_db()
        target.refresh_from_db()
        successor = ArticleVersion.objects.get(pk=result.successor_draft_id)
        review = ReviewRecord.objects.get(pk=result.review_record_id)

        self.assertEqual(result.kb_no, article.kb_no)
        self.assertEqual(result.article_id, article.pk)
        self.assertEqual(result.published_version_id, target.pk)
        self.assertEqual(result.published_version_no, 1)
        self.assertEqual(result.published_status, VersionStatus.PUBLISHED)
        self.assertEqual(result.published_at, target.published_at)
        self.assertIsNone(result.previous_published_version_id)
        self.assertEqual(result.successor_version_no, 2)
        self.assertEqual(result.successor_status, VersionStatus.DRAFT)
        self.assertEqual(result.successor_lock_version, 1)

        self.assertEqual(target.status, VersionStatus.PUBLISHED)
        self.assertIsNotNone(target.published_at)
        self.assertEqual(
            {field: getattr(target, field) for field in target_values},
            target_values,
        )
        self.assertEqual(article.current_published_version_id, target.pk)
        self.assertEqual(article.latest_working_version_id, successor.pk)
        self.assertEqual(article.title, target.title)
        self.assertEqual(article.updated_by_id, self.reviewer.pk)
        self.assertEqual(article.versions.count(), before_version_count + 1)

        self.assertEqual(review.article_version_id, target.pk)
        self.assertEqual(review.review_type, ReviewType.CONTENT_REVIEW)
        self.assertEqual(review.decision, ReviewDecision.APPROVED)
        self.assertEqual(review.reviewer_id, self.reviewer.pk)
        self.assertEqual(review.comment, "内容准确，可以发布")

        for field in ("title", "summary", "applicable_scope", "body", "body_plaintext"):
            self.assertEqual(getattr(successor, field), getattr(target, field))
        self.assertEqual(successor.change_summary, "基于已发布版本 v1 继续编辑")
        self.assertEqual(successor.created_by_id, self.submitter.pk)
        self.assertIsNone(successor.submitted_by_id)
        self.assertIsNone(successor.submitted_at)
        self.assertIsNone(successor.published_at)
        self.assertIsNone(successor.restored_from_version_id)
        self.assertEqual(
            ArticleVersion.objects.filter(article=article, status=VersionStatus.PUBLISHED).count(),
            1,
        )
        self.assertEqual(
            ArticleVersion.objects.filter(article=article, status=VersionStatus.DRAFT).count(), 1
        )

        audit = AuditEvent.objects.get()
        self.assertEqual(audit.event_type, AuditEventType.REVIEW_APPROVED_PUBLISHED)
        self.assertEqual(audit.actor_id, self.reviewer.pk)
        self.assertEqual(audit.article_id, article.pk)
        self.assertEqual(audit.article_version_id, target.pk)
        self.assertEqual(
            audit.metadata,
            {
                "kb_no": article.kb_no,
                "version_no": 1,
                "space_id": str(article.space_id),
                "review_record_id": str(review.pk),
                "previous_published_version_id": None,
                "successor_draft_id": str(successor.pk),
                "successor_version_no": 2,
            },
        )
        self.assertNotIn("comment", audit.metadata)

        outbox = WorkflowOutboxEvent.objects.get()
        self.assertEqual(outbox.event_type, WorkflowEventType.REVIEW_APPROVED_PUBLISHED)
        self.assertEqual(outbox.dedupe_key, f"review_approved_published:{target.pk}")
        self.assertEqual(
            outbox.payload,
            {
                "article_id": str(article.pk),
                "kb_no": article.kb_no,
                "published_version_id": str(target.pk),
                "published_version_no": 1,
                "previous_published_version_id": None,
                "space_id": str(article.space_id),
                "reviewer_id": str(self.reviewer.pk),
                "review_record_id": str(review.pk),
                "successor_draft_id": str(successor.pk),
                "successor_version_no": 2,
                "submitted_by_id": str(self.submitter.pk),
            },
        )
        self.assertNotIn("comment", outbox.payload)
        self.assertEqual(outbox.status, WorkflowOutboxStatus.PENDING)
        self.assertEqual(outbox.attempt_count, 0)
        self.assertIsNone(outbox.sent_at)

        idempotency = WorkflowIdempotencyRecord.objects.get()
        self.assertEqual(idempotency.operation, IdempotencyOperation.APPROVE_PUBLISH)
        self.assertEqual(idempotency.status, IdempotencyStatus.COMPLETED)
        self.assertEqual(idempotency.result_code, REVIEW_APPROVED_PUBLISHED)
        self.assertEqual(idempotency.request_fingerprint, self.expected_fingerprint(target))
        self.assertEqual(idempotency.result_payload, result.to_payload())

    def test_republish_supersedes_old_published_and_switches_employee_authority(self):
        article, target, old = self.make_article(published=True)
        old_values = {
            field: getattr(old, field)
            for field in (
                "version_no",
                "lock_version",
                "title",
                "summary",
                "applicable_scope",
                "body",
                "body_plaintext",
                "change_summary",
                "created_by_id",
                "submitted_by_id",
                "submitted_at",
                "published_at",
            )
        }
        before_detail = get_employee_article_detail(self.employee, article.kb_no)
        self.assertEqual(before_detail.title, "旧正式标题")
        self.assertTrue(search_employee_articles(self.employee, "OLDKEY").filter(pk=article.pk))
        self.assertFalse(search_employee_articles(self.employee, "NEWKEY").filter(pk=article.pk))

        result = approve_and_publish_article_version(**self.approve_kwargs(target, comment=""))

        article.refresh_from_db()
        old.refresh_from_db()
        target.refresh_from_db()
        successor = ArticleVersion.objects.get(pk=result.successor_draft_id)
        self.assertEqual(result.previous_published_version_id, old.pk)
        self.assertEqual(old.status, VersionStatus.SUPERSEDED)
        self.assertEqual(
            {field: getattr(old, field) for field in old_values},
            old_values,
        )
        self.assertEqual(target.status, VersionStatus.PUBLISHED)
        self.assertIsNotNone(target.published_at)
        self.assertEqual(article.current_published_version_id, target.pk)
        self.assertEqual(article.latest_working_version_id, successor.pk)
        self.assertEqual(article.title, "新正式标题")
        self.assertEqual(
            ArticleVersion.objects.filter(article=article, status=VersionStatus.PUBLISHED).count(),
            1,
        )
        self.assertEqual(
            ArticleVersion.objects.filter(article=article, status=VersionStatus.DRAFT).count(), 1
        )
        detail = get_employee_article_detail(self.employee, article.kb_no)
        self.assertEqual(detail.title, "新正式标题")
        self.assertEqual(detail.body_text, "NEWKEY新正式正文")
        self.assertTrue(search_employee_articles(self.employee, "NEWKEY").filter(pk=article.pk))
        self.assertFalse(search_employee_articles(self.employee, "OLDKEY").filter(pk=article.pk))
        history = get_article_version_history(actor=self.creator, article=article)
        self.assertEqual(
            list(history.values_list("version_no", "status")),
            [
                (3, VersionStatus.DRAFT),
                (2, VersionStatus.PUBLISHED),
                (1, VersionStatus.SUPERSEDED),
            ],
        )

    def test_successor_version_uses_article_maximum(self):
        article, target, _old = self.make_article(
            target_version_no=2,
            high_history_version_no=10,
        )

        result = approve_and_publish_article_version(**self.approve_kwargs(target))

        successor = ArticleVersion.objects.get(pk=result.successor_draft_id)
        self.assertEqual(successor.version_no, 11)
        self.assertEqual(article.versions.count(), 3)

    def test_comment_and_idempotency_inputs_are_normalized_and_validated(self):
        article, target, _old = self.make_article()
        invalid_cases = (
            {"version_id": "not-a-uuid"},
            {"version_id": None},
            {"comment": None},
            {"comment": 1},
            {"idempotency_key": None},
            {"idempotency_key": ""},
            {"idempotency_key": " leading"},
            {"idempotency_key": "line\nbreak"},
            {"idempotency_key": "x" * 129},
        )
        before = self.business_snapshot(article)
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                self.assert_approve_error(INVALID_INPUT, target, **overrides)
        self.assertEqual(self.business_snapshot(article), before)

        first = approve_and_publish_article_version(
            **self.approve_kwargs(target, comment="", idempotency_key="empty-comment")
        )
        second = approve_and_publish_article_version(
            **self.approve_kwargs(target, comment="   ", idempotency_key="empty-comment")
        )
        self.assertEqual(second, first)
        review = ReviewRecord.objects.get(pk=first.review_record_id)
        self.assertEqual(review.comment, "")
        record = WorkflowIdempotencyRecord.objects.get(key="empty-comment")
        self.assertEqual(record.request_fingerprint, self.expected_fingerprint(target, comment=""))

    def test_role_approve_publish_and_active_scope_are_all_required(self):
        for actor in (
            self.admin_only,
            self.editor_only,
            self.employee,
            self.staff_only,
            self.superuser_only,
        ):
            with self.subTest(actor=actor.username):
                article, target, _old = self.make_article()
                before = self.business_snapshot(article)
                self.assert_approve_error(APPROVE_PUBLISH_FORBIDDEN, target, actor=actor)
                self.assertEqual(self.business_snapshot(article), before)

        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        for codename in ("approve_articleversion", "publish_articleversion"):
            permission = Permission.objects.get(
                content_type__app_label="knowledge",
                codename=codename,
            )
            reviewer_group.permissions.remove(permission)
            try:
                actor = User.objects.create_user(username=f"approve-missing-{codename}")
                actor.groups.add(reviewer_group)
                ReviewerSpaceScope.objects.create(reviewer=actor, space=self.space)
                article, target, _old = self.make_article()
                self.assert_approve_error(APPROVE_PUBLISH_FORBIDDEN, target, actor=actor)
                self.assertEqual(ReviewRecord.objects.filter(article_version=target).count(), 0)
            finally:
                reviewer_group.permissions.add(permission)

        no_scope = User.objects.create_user(username="approve-no-scope")
        no_scope.groups.add(reviewer_group)
        article, target, _old = self.make_article()
        self.assert_approve_error(VERSION_NOT_FOUND_OR_INACCESSIBLE, target, actor=no_scope)

        inactive_scope = User.objects.create_user(username="approve-inactive-scope")
        inactive_scope.groups.add(reviewer_group)
        ReviewerSpaceScope.objects.create(
            reviewer=inactive_scope,
            space=self.space,
            is_active=False,
        )
        article, target, _old = self.make_article()
        self.assert_approve_error(
            VERSION_NOT_FOUND_OR_INACCESSIBLE,
            target,
            actor=inactive_scope,
        )

        other_scope = User.objects.create_user(username="approve-other-scope")
        other_scope.groups.add(reviewer_group)
        ReviewerSpaceScope.objects.create(reviewer=other_scope, space=self.other_space)
        article, target, _old = self.make_article()
        self.assert_approve_error(VERSION_NOT_FOUND_OR_INACCESSIBLE, target, actor=other_scope)

    def test_shared_pool_and_reviewer_admin_are_authorized(self):
        for actor in (self.reviewer, self.second_reviewer, self.reviewer_admin):
            with self.subTest(actor=actor.username):
                _article, target, _old = self.make_article()
                result = approve_and_publish_article_version(
                    **self.approve_kwargs(target, actor=actor)
                )
                self.assertEqual(result.published_status, VersionStatus.PUBLISHED)

    def test_active_saved_business_identity_is_required(self):
        _article, target, _old = self.make_article()
        for actor in (
            AnonymousUser(),
            User(username="approve-unsaved"),
            self.inactive_reviewer,
            self.disabled_reviewer,
        ):
            with self.subTest(actor=type(actor).__name__):
                self.assert_approve_error(IDENTITY_DENIED, target, actor=actor)

    def test_creator_and_submitter_cannot_self_review_even_with_extra_roles(self):
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)
        cases = (
            (self.creator, self.creator, self.submitter, (reviewer_group,)),
            (self.submitter, self.creator, self.submitter, (reviewer_group, admin_group)),
        )
        for actor, creator, submitter, groups in cases:
            with self.subTest(actor=actor.username):
                actor.groups.add(*groups)
                ReviewerSpaceScope.objects.get_or_create(reviewer=actor, space=self.space)
                article, target, _old = self.make_article(
                    creator=creator,
                    submitter=submitter,
                )
                before = self.business_snapshot(article)
                self.assert_approve_error(SELF_REVIEW_FORBIDDEN, target, actor=actor)
                self.assertEqual(self.business_snapshot(article), before)

    def test_missing_cross_article_and_non_review_targets_fail_closed(self):
        article, target, _old = self.make_article()
        before = self.business_snapshot(article)
        self.assert_approve_error(
            VERSION_NOT_FOUND_OR_INACCESSIBLE,
            target,
            version_id=uuid4(),
        )
        self.assertEqual(self.business_snapshot(article), before)

        for status in (
            VersionStatus.DRAFT,
            VersionStatus.SAVED,
            VersionStatus.REJECTED,
            VersionStatus.PUBLISHED,
            VersionStatus.SUPERSEDED,
        ):
            with self.subTest(status=status):
                other_article, other_target, _old = self.make_article(target_status=status)
                other_before = self.business_snapshot(other_article)
                self.assert_approve_error(VERSION_NOT_IN_REVIEW, other_target)
                self.assertEqual(self.business_snapshot(other_article), other_before)

    def test_inconsistent_latest_pointer_existing_review_and_old_pointer_fail_closed(self):
        article, target, _old = self.make_article()
        stray_draft = ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status=VersionStatus.DRAFT,
            title="旁路草稿",
            summary="旁路草稿",
            change_summary="旁路草稿",
            created_by=self.creator,
        )
        Article.objects.filter(pk=article.pk).update(latest_working_version=stray_draft)
        before = self.business_snapshot(article)
        self.assert_approve_error(PUBLISH_STATE_INCONSISTENT, target)
        self.assertEqual(self.business_snapshot(article), before)

        article, target, _old = self.make_article()
        ReviewRecord.objects.create(
            article_version=target,
            review_type=ReviewType.CONTENT_REVIEW,
            reviewer=self.second_reviewer,
            decision=ReviewDecision.APPROVED,
        )
        before = self.business_snapshot(article)
        self.assert_approve_error(PUBLISH_STATE_INCONSISTENT, target)
        self.assertEqual(self.business_snapshot(article), before)

        article, target, old = self.make_article(published=True)
        ArticleVersion.objects.filter(pk=old.pk).update(status=VersionStatus.SUPERSEDED)
        before = self.business_snapshot(article)
        self.assert_approve_error(PUBLISH_STATE_INCONSISTENT, target)
        self.assertEqual(self.business_snapshot(article), before)

        article, target, _old = self.make_article()
        other_article, _other_target, other_old = self.make_article(published=True)
        Article.objects.filter(pk=article.pk).update(current_published_version=other_old)
        before = self.business_snapshot(article)
        self.assert_approve_error(PUBLISH_STATE_INCONSISTENT, target)
        self.assertEqual(self.business_snapshot(article), before)
        other_old.refresh_from_db()
        self.assertEqual(other_old.article_id, other_article.pk)
        self.assertEqual(other_old.status, VersionStatus.PUBLISHED)

    def test_completed_replay_is_zero_write_and_preserves_publish_times(self):
        article, target, old = self.make_article(published=True)
        kwargs = self.approve_kwargs(target, idempotency_key="replay")
        first = approve_and_publish_article_version(**kwargs)
        successor = ArticleVersion.objects.get(pk=first.successor_draft_id)
        article.refresh_from_db()
        target.refresh_from_db()
        old.refresh_from_db()
        record = WorkflowIdempotencyRecord.objects.get()
        snapshot = {
            "business": self.business_snapshot(article),
            "article_updated_at": article.updated_at,
            "target_updated_at": target.updated_at,
            "old_updated_at": old.updated_at,
            "successor_updated_at": successor.updated_at,
            "target_published_at": target.published_at,
            "old_published_at": old.published_at,
            "idempotency_updated_at": record.updated_at,
        }

        second = approve_and_publish_article_version(**kwargs)

        self.assertEqual(second, first)
        article.refresh_from_db()
        target.refresh_from_db()
        old.refresh_from_db()
        successor.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(self.business_snapshot(article), snapshot["business"])
        self.assertEqual(article.updated_at, snapshot["article_updated_at"])
        self.assertEqual(target.updated_at, snapshot["target_updated_at"])
        self.assertEqual(old.updated_at, snapshot["old_updated_at"])
        self.assertEqual(successor.updated_at, snapshot["successor_updated_at"])
        self.assertEqual(target.published_at, snapshot["target_published_at"])
        self.assertEqual(old.published_at, snapshot["old_published_at"])
        self.assertEqual(record.updated_at, snapshot["idempotency_updated_at"])

    def test_idempotency_conflict_in_progress_and_different_key_are_safe(self):
        article, target, _old = self.make_article()
        approve_and_publish_article_version(
            **self.approve_kwargs(target, comment="", idempotency_key="first")
        )
        completed = self.business_snapshot(article)

        self.assert_approve_error(
            IDEMPOTENCY_CONFLICT,
            target,
            comment="补充说明",
            idempotency_key="first",
        )
        self.assert_approve_error(
            VERSION_NOT_IN_REVIEW,
            target,
            comment="",
            idempotency_key="second",
        )
        self.assertEqual(self.business_snapshot(article), completed)

        _article, in_progress_target, _old = self.make_article()
        WorkflowIdempotencyRecord.objects.create(
            actor=self.reviewer,
            operation=IdempotencyOperation.APPROVE_PUBLISH,
            key="in-progress",
            request_fingerprint=self.expected_fingerprint(in_progress_target),
        )
        self.assert_approve_error(
            IDEMPOTENCY_IN_PROGRESS,
            in_progress_target,
            idempotency_key="in-progress",
        )

    def test_role_permissions_and_scope_revocation_block_completed_replay(self):
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        approve_permission = Permission.objects.get(
            content_type__app_label="knowledge",
            codename="approve_articleversion",
        )
        publish_permission = Permission.objects.get(
            content_type__app_label="knowledge",
            codename="publish_articleversion",
        )
        cases = ("role", "approve", "publish", "scope")
        for name in cases:
            with self.subTest(name=name):
                actor = User.objects.create_user(username=f"approve-replay-{name}")
                actor.groups.add(reviewer_group)
                scope = ReviewerSpaceScope.objects.create(reviewer=actor, space=self.space)
                article, target, _old = self.make_article()
                kwargs = self.approve_kwargs(
                    target,
                    actor=actor,
                    idempotency_key=f"replay-{name}",
                )
                approve_and_publish_article_version(**kwargs)
                before = self.business_snapshot(article)
                removed_permission = None
                if name == "role":
                    actor.groups.remove(reviewer_group)
                elif name == "approve":
                    removed_permission = approve_permission
                    reviewer_group.permissions.remove(removed_permission)
                elif name == "publish":
                    removed_permission = publish_permission
                    reviewer_group.permissions.remove(removed_permission)
                else:
                    ReviewerSpaceScope.objects.filter(pk=scope.pk).update(is_active=False)
                try:
                    expected = (
                        VERSION_NOT_FOUND_OR_INACCESSIBLE
                        if name == "scope"
                        else APPROVE_PUBLISH_FORBIDDEN
                    )
                    self.assert_approve_error(expected, target, **kwargs)
                    self.assertEqual(self.business_snapshot(article), before)
                finally:
                    if removed_permission is not None:
                        reviewer_group.permissions.add(removed_permission)

    def test_republish_failure_points_roll_back_everything(self):
        failure_cases = (
            ("review", "apps.workflow.services._create_approval_review"),
            ("successor", "apps.workflow.services._create_approved_successor_draft"),
            ("audit", "apps.workflow.services.AuditEvent.objects.create"),
            ("outbox", "apps.workflow.services.WorkflowOutboxEvent.objects.create"),
        )
        for name, patch_target in failure_cases:
            with self.subTest(name=name):
                article, target, old = self.make_article(published=True)
                before = self.business_snapshot(article)
                old_published_at = old.published_at
                with mock.patch(
                    patch_target,
                    side_effect=DatabaseError("secret database detail"),
                ):
                    error = self.assert_approve_error(
                        WORKFLOW_UNAVAILABLE,
                        target,
                        idempotency_key=f"failure-{name}",
                    )
                self.assertNotIn("secret", str(error).lower())
                self.assertEqual(self.business_snapshot(article), before)
                old.refresh_from_db()
                target.refresh_from_db()
                article.refresh_from_db()
                self.assertEqual(old.status, VersionStatus.PUBLISHED)
                self.assertEqual(old.published_at, old_published_at)
                self.assertEqual(target.status, VersionStatus.IN_REVIEW)
                self.assertIsNone(target.published_at)
                self.assertEqual(article.current_published_version_id, old.pk)
                self.assertIsNone(article.latest_working_version_id)
                self.assertEqual(article.title, "旧兼容标题")

        article, target, old = self.make_article(published=True)
        ArticleVersion.objects.create(
            article=article,
            version_no=3,
            status=VersionStatus.DRAFT,
            title="未挂指针的异常草稿",
            summary="异常草稿",
            change_summary="异常草稿",
            created_by=self.creator,
        )
        before = self.business_snapshot(article)
        self.assert_approve_error(
            WORKFLOW_UNAVAILABLE,
            target,
            idempotency_key="draft-constraint-failure",
        )
        self.assertEqual(self.business_snapshot(article), before)
        old.refresh_from_db()
        self.assertEqual(old.status, VersionStatus.PUBLISHED)

    def test_first_publish_becomes_visible_without_leaking_successor_draft(self):
        article, target, _old = self.make_article()
        self.assertFalse(employee_visible_articles(self.employee).filter(pk=article.pk).exists())

        result = approve_and_publish_article_version(**self.approve_kwargs(target))

        detail = get_employee_article_detail(self.employee, article.kb_no)
        self.assertIsNotNone(detail)
        self.assertEqual(detail.title, "新正式标题")
        self.assertEqual(detail.body_text, "NEWKEY新正式正文")
        self.assertTrue(search_employee_articles(self.employee, "NEWKEY").filter(pk=article.pk))
        successor = ArticleVersion.objects.get(pk=result.successor_draft_id)
        successor.body_plaintext = "DRAFTONLY后继草稿内容"
        successor.body = {"format": "opsai.plaintext/1", "text": successor.body_plaintext}
        successor.save(update_fields=("body", "body_plaintext", "updated_at"))
        self.assertFalse(search_employee_articles(self.employee, "DRAFTONLY").filter(pk=article.pk))

    def test_future_effective_at_publishes_but_remains_employee_invisible(self):
        future = timezone.now() + timedelta(days=3)
        article, target, _old = self.make_article(effective_at=future)

        result = approve_and_publish_article_version(**self.approve_kwargs(target))

        article.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual(target.status, VersionStatus.PUBLISHED)
        self.assertEqual(article.current_published_version_id, target.pk)
        self.assertEqual(article.effective_at, future)
        self.assertIsNotNone(result.published_at)
        self.assertFalse(employee_visible_articles(self.employee).filter(pk=article.pk).exists())
        self.assertIsNone(get_employee_article_detail(self.employee, article.kb_no))
        self.assertFalse(search_employee_articles(self.employee, "NEWKEY").filter(pk=article.pk))

    def test_successor_editing_closes_loop_and_published_history_is_immutable(self):
        article, target, old = self.make_article(
            creator=self.submitter,
            submitter=self.submitter,
            published=True,
        )
        result = approve_and_publish_article_version(**self.approve_kwargs(target))
        successor = ArticleVersion.objects.get(pk=result.successor_draft_id)
        write_kwargs = {
            "actor": self.submitter,
            "article": article,
            "draft_id": successor.pk,
            "expected_lock_version": 1,
            "title": "发布后继续编辑",
            "summary": "发布后摘要",
            "applicable_scope": {"systems": ["Windows 11"]},
            "body_text": "DRAFTONLY发布后正文",
            "change_summary": "发布后继续维护",
        }

        updated = autosave_draft(**write_kwargs)
        saved, next_draft = manual_save_draft(
            **{**write_kwargs, "expected_lock_version": updated.lock_version}
        )

        self.assertEqual(saved.status, VersionStatus.SAVED)
        self.assertEqual(next_draft.status, VersionStatus.DRAFT)
        for immutable in (target, old):
            for writer in (autosave_draft, manual_save_draft):
                with self.subTest(version=immutable.version_no, writer=writer.__name__):
                    with self.assertRaises(ArticleVersionWriteError):
                        writer(
                            **{
                                **write_kwargs,
                                "draft_id": immutable.pk,
                                "expected_lock_version": immutable.lock_version,
                            }
                        )
        target.refresh_from_db()
        old.refresh_from_db()
        self.assertEqual(target.status, VersionStatus.PUBLISHED)
        self.assertEqual(old.status, VersionStatus.SUPERSEDED)
        history = get_article_version_history(actor=self.submitter, article=article)
        self.assertEqual(
            list(history.values_list("version_no", "status")),
            [
                (4, VersionStatus.DRAFT),
                (3, VersionStatus.SAVED),
                (2, VersionStatus.PUBLISHED),
                (1, VersionStatus.SUPERSEDED),
            ],
        )
        self.assertFalse(search_employee_articles(self.employee, "DRAFTONLY").filter(pk=article.pk))

    def test_business_lock_order_is_article_target_then_old_published(self):
        _article, target, _old = self.make_article(published=True)
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
            approve_and_publish_article_version(**self.approve_kwargs(target))

        business_locks = [model for model in lock_order if model in (Article, ArticleVersion)]
        self.assertEqual(
            business_locks,
            [Article, ArticleVersion, ArticleVersion],
        )
