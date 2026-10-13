"""Task 13-06：审核工作流纯只读 Reader 契约。"""

from dataclasses import FrozenInstanceError
from datetime import timedelta
from unittest import mock
from uuid import uuid4

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.db import connection
from django.db.models.query import QuerySet
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import AccountStatus, User
from apps.accounts.roles import (
    ROLE_EDITOR,
    ROLE_KNOWLEDGE_ADMIN,
    ROLE_REVIEWER,
    SYSTEM_ROLE_BY_CODE,
)
from apps.audit.models import AuditEvent
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
from apps.workflow.models import WorkflowIdempotencyRecord, WorkflowOutboxEvent
from apps.workflow.readers import (
    ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
    IDENTITY_DENIED,
    INVALID_INPUT,
    REVIEW_FORBIDDEN,
    VERSION_NOT_FOUND_OR_INACCESSIBLE,
    WorkflowReaderError,
    get_rejection_context,
    get_review_detail,
    get_submitted_article_status,
    list_pending_reviews,
    list_reviewed_by_me,
)


class ReviewReadersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0)
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)

        cls.creator = User.objects.create_user(username="reader-creator")
        cls.creator.groups.add(editor_group)
        cls.submitter = User.objects.create_user(username="reader-submitter")
        cls.submitter.groups.add(editor_group)
        cls.space_owner = User.objects.create_user(username="reader-space-owner")
        cls.space_owner.groups.add(editor_group)
        cls.other_editor = User.objects.create_user(username="reader-other-editor")
        cls.other_editor.groups.add(editor_group)
        cls.reviewer = User.objects.create_user(username="reader-reviewer")
        cls.reviewer.groups.add(reviewer_group)
        cls.reviewer_b = User.objects.create_user(username="reader-reviewer-b")
        cls.reviewer_b.groups.add(reviewer_group)
        cls.reviewer_admin = User.objects.create_user(username="reader-reviewer-admin")
        cls.reviewer_admin.groups.add(reviewer_group, admin_group)
        cls.admin = User.objects.create_user(username="reader-admin")
        cls.admin.groups.add(admin_group)
        cls.employee = User.objects.create_user(username="reader-employee")
        cls.staff = User.objects.create_user(username="reader-staff", is_staff=True)
        cls.superuser = User.objects.create_user(
            username="reader-superuser", is_staff=True, is_superuser=True
        )
        cls.inactive = User.objects.create_user(username="reader-inactive", is_active=False)
        cls.inactive.groups.add(reviewer_group)
        cls.disabled = User.objects.create_user(
            username="reader-disabled", account_status=AccountStatus.DISABLED
        )
        cls.disabled.groups.add(reviewer_group)

        cls.space_a = KnowledgeSpace.objects.create(
            code="reader-space-a",
            name="Reader 空间 A",
            space_type="employee",
            owner=cls.space_owner,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.space_b = KnowledgeSpace.objects.create(
            code="reader-space-b",
            name="Reader 空间 B",
            space_type="employee",
            owner=cls.other_editor,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category_a = Category.objects.create(
            space=cls.space_a, code="reader-category-a", name="Reader 分类 A"
        )
        cls.category_b = Category.objects.create(
            space=cls.space_b, code="reader-category-b", name="Reader 分类 B"
        )
        ReviewerSpaceScope.objects.create(reviewer=cls.reviewer, space=cls.space_a)
        ReviewerSpaceScope.objects.create(reviewer=cls.reviewer_b, space=cls.space_b)
        ReviewerSpaceScope.objects.create(reviewer=cls.reviewer_admin, space=cls.space_a)
        ReviewerSpaceScope.objects.create(reviewer=cls.reviewer_admin, space=cls.space_b)

    def setUp(self):
        self.sequence = 0

    def make_article(self, *, space=None, owner=None, title="旧 Article 标题"):
        self.sequence += 1
        space = space or self.space_a
        owner = owner or self.creator
        category = self.category_a if space == self.space_a else self.category_b
        return Article.objects.create(
            kb_no=f"KB-{160000 + self.sequence:06d}",
            title=title,
            space=space,
            category=category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            owner=owner,
            created_by=owner,
            updated_by=owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )

    def make_version(
        self,
        article,
        *,
        version_no,
        status,
        creator=None,
        submitter=None,
        submitted_at=None,
        title=None,
    ):
        creator = creator or self.creator
        submitted = status not in (VersionStatus.DRAFT, VersionStatus.SAVED)
        submitter = (submitter or self.submitter) if submitted else None
        return ArticleVersion.objects.create(
            article=article,
            version_no=version_no,
            status=status,
            lock_version=1,
            title=title or f"版本标题 {version_no}",
            summary=f"版本摘要 {version_no}",
            applicable_scope={"systems": ["Windows 11"], "version": version_no},
            body={"format": "opsai.plaintext/1", "text": f"正文 {version_no}"},
            body_plaintext=f"正文 {version_no}",
            change_summary=f"版本说明 {version_no}",
            created_by=creator,
            submitted_by=submitter,
            submitted_at=(submitted_at or timezone.now()) if submitted else None,
            published_at=timezone.now() if status == VersionStatus.PUBLISHED else None,
        )

    def assert_reader_error(self, code, callback, *args, **kwargs):
        with self.assertRaises(WorkflowReaderError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_pending_queue_enforces_scope_self_review_status_fields_and_order(self):
        older_article = self.make_article()
        older = self.make_version(
            older_article,
            version_no=1,
            status=VersionStatus.IN_REVIEW,
            submitted_at=timezone.now() - timedelta(hours=2),
            title="较早待审标题",
        )
        republish_article = self.make_article()
        published = self.make_version(
            republish_article, version_no=1, status=VersionStatus.PUBLISHED
        )
        pending = self.make_version(
            republish_article,
            version_no=2,
            status=VersionStatus.IN_REVIEW,
            submitted_at=timezone.now() - timedelta(hours=1),
            title="新待审标题",
        )
        Article.objects.filter(pk=republish_article.pk).update(current_published_version=published)
        other_space = self.make_article(space=self.space_b)
        self.make_version(other_space, version_no=1, status=VersionStatus.IN_REVIEW)
        self_article = self.make_article(owner=self.reviewer)
        self.make_version(
            self_article,
            version_no=1,
            status=VersionStatus.IN_REVIEW,
            creator=self.reviewer,
        )
        self_submitted_article = self.make_article()
        self.make_version(
            self_submitted_article,
            version_no=1,
            status=VersionStatus.IN_REVIEW,
            submitter=self.reviewer,
        )
        draft_article = self.make_article()
        self.make_version(draft_article, version_no=1, status=VersionStatus.DRAFT)
        for status in (
            VersionStatus.SAVED,
            VersionStatus.REJECTED,
            VersionStatus.PUBLISHED,
            VersionStatus.SUPERSEDED,
        ):
            non_pending_article = self.make_article()
            self.make_version(non_pending_article, version_no=1, status=status)

        result = list_pending_reviews(self.reviewer)

        self.assertEqual([item.version_id for item in result], [older.pk, pending.pk])
        self.assertEqual(result[1].title, "新待审标题")
        self.assertNotEqual(result[1].title, republish_article.title)
        self.assertTrue(result[1].is_republish)
        self.assertEqual(result[1].current_published_version_id, published.pk)
        self.assertEqual(result[1].current_published_version_no, 1)
        self.assertFalse(hasattr(result[0], "body"))
        self.assertFalse(hasattr(result[0], "body_plaintext"))
        with self.assertRaises(FrozenInstanceError):
            result[0].title = "不可修改"

        multi_scope = list_pending_reviews(self.reviewer_admin)
        self.assertIn(other_space.pk, {item.article_id for item in multi_scope})

    def test_pending_queue_requires_current_business_reviewer_identity_and_permission(self):
        article = self.make_article()
        self.make_version(article, version_no=1, status=VersionStatus.IN_REVIEW)

        for actor in (self.inactive, self.disabled):
            with self.subTest(actor=actor.username):
                self.assert_reader_error(IDENTITY_DENIED, list_pending_reviews, actor)
        for actor in (self.employee, self.staff, self.superuser, self.admin):
            with self.subTest(actor=actor.username):
                self.assert_reader_error(REVIEW_FORBIDDEN, list_pending_reviews, actor)

        permission = Permission.objects.get(
            content_type__app_label="knowledge", codename="review_articleversion"
        )
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        reviewer_group.permissions.remove(permission)
        try:
            self.assert_reader_error(REVIEW_FORBIDDEN, list_pending_reviews, self.reviewer)
        finally:
            reviewer_group.permissions.add(permission)

    def test_review_detail_returns_whitelisted_snapshot_and_own_history_only(self):
        article = self.make_article()
        published = self.make_version(article, version_no=1, status=VersionStatus.PUBLISHED)
        target = self.make_version(
            article, version_no=2, status=VersionStatus.IN_REVIEW, title="审核目标标题"
        )
        saved = self.make_version(article, version_no=3, status=VersionStatus.SAVED)
        Article.objects.filter(pk=article.pk).update(current_published_version=published)

        detail = get_review_detail(actor=self.reviewer, version_id=target.pk)

        self.assertEqual(detail.target.version_id, target.pk)
        self.assertEqual(detail.target.title, "审核目标标题")
        self.assertEqual(detail.target.body, target.body)
        self.assertEqual(detail.target.body_plaintext, target.body_plaintext)
        self.assertEqual(detail.article.article_id, article.pk)
        self.assertEqual(detail.article.space_id, self.space_a.pk)
        self.assertEqual(detail.current_published.version_id, published.pk)
        self.assertEqual(
            [item.version_id for item in detail.history], [saved.pk, target.pk, published.pk]
        )
        self.assertEqual(detail.review_records, ())
        detail.target.body["text"] = "调用方修改"
        target.refresh_from_db()
        self.assertEqual(target.body["text"], "正文 2")
        self.assertNotIn("payload", repr(detail))

        historical_article = self.make_article()
        historical = self.make_version(
            historical_article, version_no=1, status=VersionStatus.REJECTED
        )
        own_review = ReviewRecord.objects.create(
            article_version=historical,
            reviewer=self.reviewer,
            review_type=ReviewType.CONTENT_REVIEW,
            decision=ReviewDecision.REJECTED,
            comment="历史驳回原因",
        )
        historical_detail = get_review_detail(actor=self.reviewer, version_id=historical.pk)
        self.assertEqual(historical_detail.review_records[0].review_record_id, own_review.pk)
        self.assertEqual(historical_detail.review_records[0].comment, "历史驳回原因")

        foreign_article = self.make_article()
        foreign = self.make_version(foreign_article, version_no=1, status=VersionStatus.REJECTED)
        ReviewRecord.objects.create(
            article_version=foreign,
            reviewer=self.reviewer_b,
            review_type=ReviewType.CONTENT_REVIEW,
            decision=ReviewDecision.REJECTED,
            comment="其他审核员",
        )
        denied = self.assert_reader_error(
            VERSION_NOT_FOUND_OR_INACCESSIBLE,
            get_review_detail,
            actor=self.reviewer,
            version_id=foreign.pk,
        )
        missing = self.assert_reader_error(
            VERSION_NOT_FOUND_OR_INACCESSIBLE,
            get_review_detail,
            actor=self.reviewer,
            version_id=uuid4(),
        )
        self.assertEqual(denied.public_message, missing.public_message)
        self.assert_reader_error(
            INVALID_INPUT,
            get_review_detail,
            actor=self.reviewer,
            version_id="invalid-uuid",
        )

    def test_review_detail_rejects_self_review_and_current_authorization_revocation(self):
        own_article = self.make_article(owner=self.reviewer)
        own = self.make_version(
            own_article,
            version_no=1,
            status=VersionStatus.IN_REVIEW,
            creator=self.reviewer,
        )
        submitted_article = self.make_article()
        submitted = self.make_version(
            submitted_article,
            version_no=1,
            status=VersionStatus.IN_REVIEW,
            submitter=self.reviewer,
        )
        for version in (own, submitted):
            self.assert_reader_error(
                VERSION_NOT_FOUND_OR_INACCESSIBLE,
                get_review_detail,
                actor=self.reviewer,
                version_id=version.pk,
            )

        article = self.make_article(space=self.space_b)
        target = self.make_version(article, version_no=1, status=VersionStatus.IN_REVIEW)
        self.assert_reader_error(
            VERSION_NOT_FOUND_OR_INACCESSIBLE,
            get_review_detail,
            actor=self.reviewer,
            version_id=target.pk,
        )

        authorized_article = self.make_article()
        authorized = self.make_version(
            authorized_article,
            version_no=1,
            status=VersionStatus.IN_REVIEW,
        )
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        self.reviewer.groups.remove(reviewer_group)
        try:
            self.assert_reader_error(
                REVIEW_FORBIDDEN,
                get_review_detail,
                actor=self.reviewer,
                version_id=authorized.pk,
            )
        finally:
            self.reviewer.groups.add(reviewer_group)

        permission = Permission.objects.get(
            content_type__app_label="knowledge", codename="review_articleversion"
        )
        reviewer_group.permissions.remove(permission)
        try:
            self.assert_reader_error(
                REVIEW_FORBIDDEN,
                get_review_detail,
                actor=self.reviewer,
                version_id=authorized.pk,
            )
        finally:
            reviewer_group.permissions.add(permission)

    def test_reviewed_by_me_filters_reviewer_current_scope_and_orders_latest_first(self):
        first_article = self.make_article()
        first_version = self.make_version(
            first_article, version_no=1, status=VersionStatus.REJECTED
        )
        first = ReviewRecord.objects.create(
            article_version=first_version,
            reviewer=self.reviewer,
            review_type=ReviewType.CONTENT_REVIEW,
            decision=ReviewDecision.REJECTED,
            comment="first",
        )
        second_article = self.make_article()
        second_version = self.make_version(
            second_article, version_no=1, status=VersionStatus.PUBLISHED
        )
        second = ReviewRecord.objects.create(
            article_version=second_version,
            reviewer=self.reviewer,
            review_type=ReviewType.CONTENT_REVIEW,
            decision=ReviewDecision.APPROVED,
            comment="second",
        )
        other_reviewer_article = self.make_article()
        other_reviewer_version = self.make_version(
            other_reviewer_article, version_no=1, status=VersionStatus.REJECTED
        )
        ReviewRecord.objects.create(
            article_version=other_reviewer_version,
            reviewer=self.reviewer_b,
            review_type=ReviewType.CONTENT_REVIEW,
            decision=ReviewDecision.REJECTED,
            comment="other",
        )
        other_space_article = self.make_article(space=self.space_b)
        other_space_version = self.make_version(
            other_space_article, version_no=1, status=VersionStatus.REJECTED
        )
        ReviewRecord.objects.create(
            article_version=other_space_version,
            reviewer=self.reviewer,
            review_type=ReviewType.CONTENT_REVIEW,
            decision=ReviewDecision.REJECTED,
            comment="out of scope",
        )
        ReviewRecord.objects.filter(pk=first.pk).update(
            reviewed_at=timezone.now() - timedelta(hours=2)
        )
        ReviewRecord.objects.filter(pk=second.pk).update(
            reviewed_at=timezone.now() - timedelta(hours=1)
        )

        result = list_reviewed_by_me(self.reviewer)

        self.assertEqual([item.review_record_id for item in result], [second.pk, first.pk])
        self.assertTrue(all(not hasattr(item, "body") for item in result))
        scope = ReviewerSpaceScope.objects.get(reviewer=self.reviewer, space=self.space_a)
        scope.is_active = False
        scope.save(update_fields=("is_active", "updated_at"))
        self.assertEqual(list_reviewed_by_me(self.reviewer), ())
        self.assert_reader_error(
            VERSION_NOT_FOUND_OR_INACCESSIBLE,
            get_review_detail,
            actor=self.reviewer,
            version_id=first_version.pk,
        )

    def test_submitted_status_uses_manage_access_and_current_in_review(self):
        article = self.make_article()
        published = self.make_version(article, version_no=1, status=VersionStatus.PUBLISHED)
        pending = self.make_version(article, version_no=2, status=VersionStatus.IN_REVIEW)
        Article.objects.filter(pk=article.pk).update(current_published_version=published)

        for actor in (self.creator, self.space_owner, self.admin):
            with self.subTest(actor=actor.username):
                result = get_submitted_article_status(actor=actor, kb_no=article.kb_no)
                self.assertEqual(result.version_id, pending.pk)
                self.assertEqual(result.current_published_version_id, published.pk)
                self.assertEqual(result.current_published_title, published.title)

        for actor in (self.other_editor, self.employee, self.staff, self.superuser):
            with self.subTest(actor=actor.username):
                self.assert_reader_error(
                    ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
                    get_submitted_article_status,
                    actor=actor,
                    kb_no=article.kb_no,
                )
        for actor in (self.inactive, self.disabled):
            with self.subTest(actor=actor.username):
                self.assert_reader_error(
                    IDENTITY_DENIED,
                    get_submitted_article_status,
                    actor=actor,
                    kb_no=article.kb_no,
                )

        no_pending = self.make_article()
        self.make_version(no_pending, version_no=1, status=VersionStatus.SAVED)
        self.assertIsNone(get_submitted_article_status(actor=self.creator, kb_no=no_pending.kb_no))

    def test_rejection_context_uses_latest_content_reject_and_current_working(self):
        article = self.make_article()
        first_version = self.make_version(article, version_no=1, status=VersionStatus.REJECTED)
        first = ReviewRecord.objects.create(
            article_version=first_version,
            reviewer=self.reviewer,
            review_type=ReviewType.CONTENT_REVIEW,
            decision=ReviewDecision.REJECTED,
            comment="第一次驳回",
        )
        second_version = self.make_version(article, version_no=2, status=VersionStatus.REJECTED)
        second = ReviewRecord.objects.create(
            article_version=second_version,
            reviewer=self.reviewer_admin,
            review_type=ReviewType.CONTENT_REVIEW,
            decision=ReviewDecision.REJECTED,
            comment="第二次驳回",
        )
        current = self.make_version(article, version_no=4, status=VersionStatus.DRAFT)
        Article.objects.filter(pk=article.pk).update(latest_working_version=current)
        ReviewRecord.objects.filter(pk=first.pk).update(
            reviewed_at=timezone.now() - timedelta(hours=2)
        )
        ReviewRecord.objects.filter(pk=second.pk).update(
            reviewed_at=timezone.now() - timedelta(hours=1)
        )

        result = get_rejection_context(actor=self.creator, kb_no=article.kb_no)

        self.assertEqual(result.review_record_id, second.pk)
        self.assertEqual(result.rejected_version_id, second_version.pk)
        self.assertEqual(result.comment, "第二次驳回")
        self.assertEqual(result.current_working_version_id, current.pk)
        self.assertEqual(result.current_working_version_no, 4)
        self.assertIsNone(
            get_rejection_context(actor=self.creator, kb_no=self.make_article().kb_no)
        )
        self.assert_reader_error(
            ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
            get_rejection_context,
            actor=self.other_editor,
            kb_no=article.kb_no,
        )
        self.assert_reader_error(
            ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
            get_rejection_context,
            actor=self.employee,
            kb_no=article.kb_no,
        )

    def test_all_readers_are_zero_write_and_never_lock_rows(self):
        pending_article = self.make_article()
        pending = self.make_version(pending_article, version_no=1, status=VersionStatus.IN_REVIEW)
        rejected_article = self.make_article()
        rejected = self.make_version(rejected_article, version_no=1, status=VersionStatus.REJECTED)
        review = ReviewRecord.objects.create(
            article_version=rejected,
            reviewer=self.reviewer_admin,
            review_type=ReviewType.CONTENT_REVIEW,
            decision=ReviewDecision.REJECTED,
            comment="只读检查",
        )
        draft = self.make_version(rejected_article, version_no=2, status=VersionStatus.DRAFT)
        Article.objects.filter(pk=rejected_article.pk).update(latest_working_version=draft)
        counts_before = (
            Article.objects.count(),
            ArticleVersion.objects.count(),
            ReviewRecord.objects.count(),
            AuditEvent.objects.count(),
            WorkflowOutboxEvent.objects.count(),
            WorkflowIdempotencyRecord.objects.count(),
        )
        timestamps_before = (
            Article.objects.get(pk=pending_article.pk).updated_at,
            ArticleVersion.objects.get(pk=pending.pk).updated_at,
            ReviewRecord.objects.get(pk=review.pk).reviewed_at,
        )

        with mock.patch.object(QuerySet, "select_for_update", side_effect=AssertionError):
            list_pending_reviews(self.reviewer_admin)
            get_review_detail(actor=self.reviewer_admin, version_id=pending.pk)
            list_reviewed_by_me(self.reviewer_admin)
            get_submitted_article_status(actor=self.admin, kb_no=pending_article.kb_no)
            get_rejection_context(actor=self.admin, kb_no=rejected_article.kb_no)

        self.assertEqual(
            counts_before,
            (
                Article.objects.count(),
                ArticleVersion.objects.count(),
                ReviewRecord.objects.count(),
                AuditEvent.objects.count(),
                WorkflowOutboxEvent.objects.count(),
                WorkflowIdempotencyRecord.objects.count(),
            ),
        )
        self.assertEqual(
            timestamps_before,
            (
                Article.objects.get(pk=pending_article.pk).updated_at,
                ArticleVersion.objects.get(pk=pending.pk).updated_at,
                ReviewRecord.objects.get(pk=review.pk).reviewed_at,
            ),
        )

    def test_queue_and_reviewed_query_counts_do_not_grow_with_ten_rows(self):
        article = self.make_article()
        detail_target = self.make_version(article, version_no=1, status=VersionStatus.IN_REVIEW)
        with CaptureQueriesContext(connection) as captured:
            list_pending_reviews(User.objects.get(pk=self.reviewer.pk))
        queue_one = len(captured)

        reviewed_article = self.make_article()
        reviewed_version = self.make_version(
            reviewed_article, version_no=1, status=VersionStatus.REJECTED
        )
        ReviewRecord.objects.create(
            article_version=reviewed_version,
            reviewer=self.reviewer,
            review_type=ReviewType.CONTENT_REVIEW,
            decision=ReviewDecision.REJECTED,
            comment="query one",
        )
        with CaptureQueriesContext(connection) as captured:
            list_reviewed_by_me(User.objects.get(pk=self.reviewer.pk))
        reviewed_one = len(captured)

        for index in range(9):
            pending_article = self.make_article()
            self.make_version(
                pending_article,
                version_no=1,
                status=VersionStatus.IN_REVIEW,
                title=f"批量待审 {index}",
            )
            history_article = self.make_article()
            history_version = self.make_version(
                history_article, version_no=1, status=VersionStatus.REJECTED
            )
            ReviewRecord.objects.create(
                article_version=history_version,
                reviewer=self.reviewer,
                review_type=ReviewType.CONTENT_REVIEW,
                decision=ReviewDecision.REJECTED,
                comment=f"批量历史 {index}",
            )

        with CaptureQueriesContext(connection) as captured:
            queue_ten_result = list_pending_reviews(User.objects.get(pk=self.reviewer.pk))
        queue_ten = len(captured)
        with CaptureQueriesContext(connection) as captured:
            reviewed_ten_result = list_reviewed_by_me(User.objects.get(pk=self.reviewer.pk))
        reviewed_ten = len(captured)
        with CaptureQueriesContext(connection) as captured:
            get_review_detail(
                actor=User.objects.get(pk=self.reviewer.pk),
                version_id=detail_target.pk,
            )
        detail_queries = len(captured)

        self.assertEqual(len(queue_ten_result), 10)
        self.assertEqual(len(reviewed_ten_result), 10)
        self.assertEqual(queue_ten, queue_one)
        self.assertEqual(reviewed_ten, reviewed_one)
        self.assertLessEqual(detail_queries, 8)
