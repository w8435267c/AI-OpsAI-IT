"""审核 Web 工作台必须复用既有 Reader 与 Service 的端到端契约。"""

from datetime import timedelta
from uuid import uuid4

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import ROLE_EDITOR, ROLE_REVIEWER, SYSTEM_ROLE_BY_CODE
from apps.audit.models import AuditEvent
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
from apps.knowledge.readers import employee_visible_articles
from apps.workflow.models import WorkflowIdempotencyRecord, WorkflowOutboxEvent


class ReviewWebTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0)
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)

        cls.author = User.objects.create_user(username="review-web-author")
        cls.author.groups.add(editor_group)
        cls.other_editor = User.objects.create_user(username="review-web-other-editor")
        cls.other_editor.groups.add(editor_group)
        cls.reviewer = User.objects.create_user(username="review-web-reviewer")
        cls.reviewer.groups.add(reviewer_group)
        cls.second_reviewer = User.objects.create_user(username="review-web-second-reviewer")
        cls.second_reviewer.groups.add(reviewer_group)
        cls.employee = User.objects.create_user(username="review-web-employee")
        cls.space = KnowledgeSpace.objects.create(
            code="review-web-space",
            name="审核 Web 空间",
            space_type="employee",
            owner=cls.author,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="review-web-category",
            name="审核 Web 分类",
        )
        cls.reclassified_category = Category.objects.create(
            space=cls.space,
            code="review-web-reclassified",
            name="审核 Web 改类目标",
        )
        cls.other_space = KnowledgeSpace.objects.create(
            code="review-web-other-space",
            name="审核 Web 其他空间",
            space_type="employee",
            owner=cls.other_editor,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.other_category = Category.objects.create(
            space=cls.other_space,
            code="review-web-other-category",
            name="审核 Web 其他分类",
        )
        from apps.knowledge.models import ReviewerSpaceScope

        ReviewerSpaceScope.objects.create(reviewer=cls.reviewer, space=cls.space)
        ReviewerSpaceScope.objects.create(reviewer=cls.second_reviewer, space=cls.space)

    def setUp(self):
        self.sequence = 0
        self.client = Client()

    def make_article(
        self, *, creator=None, submitted_by=None, status=VersionStatus.DRAFT, space=None
    ):
        self.sequence += 1
        creator = creator or self.author
        space = space or self.space
        article = Article.objects.create(
            kb_no=f"KB-{180000 + self.sequence:06d}",
            title=f"审核 Web 文章 {self.sequence}",
            space=space,
            category=self.category if space == self.space else self.other_category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            owner=creator,
            created_by=creator,
            updated_by=creator,
            review_due_at=timezone.now() + timedelta(days=180),
        )
        version = ArticleVersion.objects.create(
            article=article,
            version_no=1,
            status=status,
            lock_version=1,
            title=f"审核 Web 版本 {self.sequence}",
            summary="审核 Web 测试摘要",
            applicable_scope={},
            body={"format": "opsai.plaintext/1", "text": "审核 Web 测试正文"},
            body_plaintext="审核 Web 测试正文",
            change_summary="提交审核 Web 测试",
            created_by=creator,
            submitted_by=(submitted_by or self.author)
            if status == VersionStatus.IN_REVIEW
            else None,
            submitted_at=timezone.now() if status == VersionStatus.IN_REVIEW else None,
        )
        if status == VersionStatus.DRAFT:
            Article.objects.filter(pk=article.pk).update(latest_working_version=version)
            article.refresh_from_db()
        return article, version

    def login(self, user):
        self.client.force_login(user)

    def test_queue_and_detail_only_expose_in_scope_non_self_pending_review(self):
        article, version = self.make_article(status=VersionStatus.IN_REVIEW)
        self.make_article(
            creator=self.reviewer,
            submitted_by=self.author,
            status=VersionStatus.IN_REVIEW,
        )

        self.login(self.reviewer)
        response = self.client.get(reverse("workflow:queue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, version.title)
        self.assertNotContains(response, "审核 Web 版本 2")
        detail = self.client.get(reverse("workflow:detail", args=[version.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "待审核版本")

    def test_queue_and_detail_fail_closed_for_non_reviewer_and_self_review(self):
        _article, version = self.make_article(
            creator=self.reviewer,
            submitted_by=self.author,
            status=VersionStatus.IN_REVIEW,
        )
        self.login(self.employee)
        self.assertEqual(self.client.get(reverse("workflow:queue")).status_code, 403)

        self.login(self.reviewer)
        self.assertEqual(
            self.client.get(reverse("workflow:detail", args=[version.pk])).status_code,
            404,
        )

    def test_author_can_submit_current_draft_only_through_service(self):
        article, draft = self.make_article()
        self.login(self.author)
        url = reverse("workflow:submission", args=[article.kb_no])

        edit_page = self.client.get(reverse("knowledge_manage:edit", args=[article.kb_no]))
        self.assertEqual(edit_page.status_code, 200)
        self.assertContains(edit_page, url)
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "提交审核")
        payload = {
            "draft_id": str(draft.pk),
            "expected_lock_version": draft.lock_version,
            "idempotency_key": "review-web-submit-001",
        }
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.client.post(url, payload).status_code, 303)
        draft.refresh_from_db()
        article.refresh_from_db()
        self.assertEqual(draft.status, VersionStatus.IN_REVIEW)
        self.assertIsNone(article.latest_working_version_id)
        self.assertEqual(WorkflowOutboxEvent.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), 1)
        self.assertEqual(WorkflowIdempotencyRecord.objects.count(), 1)

    def test_submission_does_not_expose_or_submit_other_editors_draft(self):
        article, _draft = self.make_article(creator=self.other_editor, space=self.other_space)
        self.login(self.author)
        self.assertEqual(
            self.client.get(reverse("workflow:submission", args=[article.kb_no])).status_code,
            404,
        )

    def test_approve_uses_service_and_publishes_only_after_valid_post(self):
        article, version = self.make_article(status=VersionStatus.IN_REVIEW)
        self.login(self.reviewer)
        detail_url = reverse("workflow:detail", args=[version.pk])

        response = self.client.post(
            detail_url,
            {
                "action": "approve",
                "comment": "审核通过",
                "idempotency_key": "review-web-approve-001",
            },
        )

        self.assertEqual(response.status_code, 303)
        version.refresh_from_db()
        article.refresh_from_db()
        self.assertEqual(version.status, VersionStatus.PUBLISHED)
        self.assertEqual(article.current_published_version_id, version.pk)
        self.assertEqual(ReviewRecord.objects.count(), 1)
        self.assertEqual(WorkflowOutboxEvent.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), 1)
        self.assertEqual(
            [row.kb_no for row in employee_visible_articles(self.employee)], [article.kb_no]
        )

    def test_reject_requires_reason_and_never_publishes(self):
        article, version = self.make_article(status=VersionStatus.IN_REVIEW)
        self.login(self.reviewer)
        detail_url = reverse("workflow:detail", args=[version.pk])

        invalid = self.client.post(
            detail_url,
            {"action": "reject", "comment": "  ", "idempotency_key": "review-web-reject-001"},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(ReviewRecord.objects.count(), 0)

        response = self.client.post(
            detail_url,
            {
                "action": "reject",
                "comment": "请补充网络检查步骤",
                "idempotency_key": "review-web-reject-001",
            },
        )
        self.assertEqual(response.status_code, 303)
        version.refresh_from_db()
        article.refresh_from_db()
        self.assertEqual(version.status, VersionStatus.REJECTED)
        self.assertIsNone(article.current_published_version_id)
        self.assertEqual(ReviewRecord.objects.count(), 1)
        self.assertEqual(employee_visible_articles(self.employee).count(), 0)

    def test_approval_switches_only_the_submitted_proposed_category(self):
        article, published = self.make_article()
        ArticleVersion.objects.filter(pk=published.pk).update(
            status=VersionStatus.PUBLISHED,
            published_at=timezone.now(),
            submitted_by=self.author,
            submitted_at=timezone.now(),
        )
        Article.objects.filter(pk=article.pk).update(
            current_published_version=published, latest_working_version=None
        )
        published.refresh_from_db()
        pending = ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status=VersionStatus.IN_REVIEW,
            title=published.title,
            summary=published.summary,
            applicable_scope=published.applicable_scope,
            body=published.body,
            body_plaintext=published.body_plaintext,
            change_summary="仅修改分类",
            proposed_category=self.reclassified_category,
            created_by=self.author,
            submitted_by=self.author,
            submitted_at=timezone.now(),
        )
        self.login(self.reviewer)
        detail_url = reverse("workflow:detail", args=[pending.pk])
        detail_page = self.client.get(detail_url)
        self.assertContains(detail_page, "分类变更")
        self.assertContains(detail_page, "审核 Web 改类目标")
        self.client.post(
            detail_url,
            {
                "action": "approve",
                "comment": "改类通过",
                "idempotency_key": "review-web-category-1",
            },
        )
        article.refresh_from_db()
        self.assertEqual(article.category_id, self.reclassified_category.pk)
        self.assertEqual(article.current_published_version_id, pending.pk)

    def test_rejection_keeps_current_category_and_preserves_proposed_change_in_draft(self):
        article, published = self.make_article()
        ArticleVersion.objects.filter(pk=published.pk).update(
            status=VersionStatus.PUBLISHED,
            published_at=timezone.now(),
            submitted_by=self.author,
            submitted_at=timezone.now(),
        )
        Article.objects.filter(pk=article.pk).update(
            current_published_version=published, latest_working_version=None
        )
        published.refresh_from_db()
        pending = ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status=VersionStatus.IN_REVIEW,
            title=published.title,
            summary=published.summary,
            applicable_scope={},
            body={},
            body_plaintext=published.body_plaintext,
            change_summary="仅修改分类",
            proposed_category=self.reclassified_category,
            created_by=self.author,
            submitted_by=self.author,
            submitted_at=timezone.now(),
        )
        self.login(self.reviewer)
        self.client.post(
            reverse("workflow:detail", args=[pending.pk]),
            {
                "action": "reject",
                "comment": "请确认分类",
                "idempotency_key": "review-web-category-2",
            },
        )
        article.refresh_from_db()
        self.assertEqual(article.category_id, self.category.pk)
        self.assertEqual(
            article.latest_working_version.proposed_category_id, self.reclassified_category.pk
        )

    def test_duplicate_and_stale_review_posts_do_not_duplicate_business_results(self):
        article, version = self.make_article(status=VersionStatus.IN_REVIEW)
        detail_url = reverse("workflow:detail", args=[version.pk])
        self.login(self.reviewer)
        payload = {
            "action": "approve",
            "comment": "审核通过",
            "idempotency_key": "review-web-repeat-001",
        }

        self.assertEqual(self.client.post(detail_url, payload).status_code, 303)
        self.assertEqual(self.client.post(detail_url, payload).status_code, 303)
        self.assertEqual(ReviewRecord.objects.count(), 1)
        self.assertEqual(WorkflowOutboxEvent.objects.count(), 1)

        self.login(self.second_reviewer)
        stale = self.client.post(
            detail_url,
            {"action": "reject", "comment": "过期审核", "idempotency_key": "review-web-stale-001"},
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(ReviewRecord.objects.count(), 1)

    def test_get_never_changes_review_state_and_csrf_is_enforced(self):
        article, version = self.make_article(status=VersionStatus.IN_REVIEW)
        detail_url = reverse("workflow:detail", args=[version.pk])
        self.login(self.reviewer)
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        version.refresh_from_db()
        self.assertEqual(version.status, VersionStatus.IN_REVIEW)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.reviewer)
        rejected = csrf_client.post(
            detail_url,
            {
                "action": "approve",
                "comment": "审核通过",
                "idempotency_key": str(uuid4()),
            },
        )
        self.assertEqual(rejected.status_code, 403)
        version.refresh_from_db()
        self.assertEqual(version.status, VersionStatus.IN_REVIEW)
        self.assertEqual(ReviewRecord.objects.count(), 0)

    def test_reviewed_by_me_page_only_shows_current_reviewers_own_history(self):
        article, version = self.make_article(status=VersionStatus.IN_REVIEW)
        self.login(self.reviewer)
        self.client.post(
            reverse("workflow:detail", args=[version.pk]),
            {
                "action": "approve",
                "comment": "审核通过",
                "idempotency_key": "review-web-history-001",
            },
        )

        page = self.client.get(reverse("workflow:reviewed"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, version.title)
        self.login(self.second_reviewer)
        self.assertNotContains(self.client.get(reverse("workflow:reviewed")), version.title)
