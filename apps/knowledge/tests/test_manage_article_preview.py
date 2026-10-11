"""Task 12E-08：管理侧 current working DRAFT Preview 合同。"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountStatus, User
from apps.accounts.roles import (
    ROLE_EDITOR,
    ROLE_KNOWLEDGE_ADMIN,
    ROLE_REVIEWER,
    SYSTEM_ROLE_BY_CODE,
)
from apps.knowledge.manage_readers import get_manage_working_article_detail
from apps.knowledge.models import (
    Article,
    ArticleStatus,
    ArticleType,
    ArticleVersion,
    AudiencePolicy,
    Category,
    KnowledgeSpace,
    ReviewRecord,
    VersionStatus,
)
from apps.search.readers import search_employee_articles


class ManageArticlePreviewTemplateSafetyTests(SimpleTestCase):
    def test_template_has_no_unsafe_rendering_or_write_controls(self):
        source = (
            Path(settings.BASE_DIR) / "templates" / "knowledge" / "manage" / "preview.html"
        ).read_text(encoding="utf-8")

        for forbidden in (
            "|safe",
            "mark_safe",
            "保存版本",
            "自动保存",
            "恢复此版本",
            "提交审核",
            "驳回",
            "重新发布",
            'type="submit"',
            "data-autosave-url",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class ManageArticlePreviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0, stdout=StringIO())
        cls.editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        cls.admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)
        cls.reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)

        cls.owner = cls.make_user("preview-owner", cls.editor_group)
        cls.space_owner = cls.make_user("preview-space-owner", cls.editor_group)
        cls.other_editor = cls.make_user("preview-other-editor", cls.editor_group)
        cls.admin = cls.make_user("preview-admin", cls.admin_group)
        cls.employee = cls.make_user("preview-employee")
        cls.reviewer = cls.make_user("preview-reviewer", cls.reviewer_group)

        cls.space = KnowledgeSpace.objects.create(
            code="preview-space",
            name="草稿预览空间",
            space_type="employee",
            owner=cls.space_owner,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="preview-category",
            name="草稿预览分类",
        )
        cls.article = cls.make_article("KB-360001", cls.owner, title="ARTICLE-兼容标题")
        cls.published = cls.make_version(
            cls.article,
            1,
            VersionStatus.PUBLISHED,
            marker="正式标题",
        )
        cls.draft = ArticleVersion.objects.create(
            article=cls.article,
            version_no=2,
            status=VersionStatus.DRAFT,
            lock_version=7,
            title="草稿标题",
            summary="草稿摘要",
            applicable_scope={"说明": "中文范围", "nested": {"value": 1}},
            body={"format": "structured", "secret": "不得展示的结构化正文"},
            body_plaintext="草稿正文第一行\n草稿正文第二行",
            change_summary="草稿版本说明",
            created_by=cls.owner,
        )
        Article.objects.filter(pk=cls.article.pk).update(
            latest_working_version=cls.draft,
            current_published_version=cls.published,
        )

        cls.unpublished = cls.make_article("KB-360002", cls.owner, title="未发布兼容标题")
        cls.unpublished_draft = cls.make_version(
            cls.unpublished,
            1,
            VersionStatus.DRAFT,
            marker="仅草稿秘密关键词",
        )
        Article.objects.filter(pk=cls.unpublished.pk).update(
            latest_working_version=cls.unpublished_draft
        )

        cls.other_space = KnowledgeSpace.objects.create(
            code="preview-other-space",
            name="其他预览空间",
            space_type="employee",
            owner=cls.other_editor,
        )
        cls.other_category = Category.objects.create(
            space=cls.other_space,
            code="preview-other-category",
            name="其他预览分类",
        )
        cls.other_article = cls.make_article(
            "KB-360003",
            cls.other_editor,
            title="其他文章兼容标题",
            space=cls.other_space,
            category=cls.other_category,
        )
        cls.other_draft = cls.make_version(
            cls.other_article,
            1,
            VersionStatus.DRAFT,
            marker="其他秘密草稿",
        )
        Article.objects.filter(pk=cls.other_article.pk).update(
            latest_working_version=cls.other_draft
        )

        cls.no_working = cls.make_article("KB-360004", cls.owner, title="无草稿文章")
        cls.non_draft = cls.make_article("KB-360005", cls.owner, title="错误工作指针")
        cls.non_draft_version = cls.make_version(
            cls.non_draft,
            1,
            VersionStatus.SAVED,
            marker="非草稿工作版本",
        )
        Article.objects.filter(pk=cls.non_draft.pk).update(
            latest_working_version=cls.non_draft_version
        )

    @classmethod
    def make_user(cls, username, group=None, **kwargs):
        user = User.objects.create_user(username=username, **kwargs)
        if group is not None:
            user.groups.add(group)
        return user

    @classmethod
    def make_article(cls, kb_no, owner, *, title, space=None, category=None):
        return Article.objects.create(
            kb_no=kb_no,
            title=title,
            space=space or cls.space,
            category=category or cls.category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            owner=owner,
            article_status=ArticleStatus.ACTIVE,
            created_by=owner,
            updated_by=owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )

    @classmethod
    def make_version(cls, article, version_no, status, *, marker):
        workflow = {}
        if status not in (VersionStatus.DRAFT, VersionStatus.SAVED):
            workflow.update(submitted_by=article.owner, submitted_at=timezone.now())
        if status == VersionStatus.PUBLISHED:
            workflow["published_at"] = timezone.now()
        return ArticleVersion.objects.create(
            article=article,
            version_no=version_no,
            status=status,
            title=f"{marker}",
            summary=f"{marker}摘要",
            applicable_scope={"marker": marker},
            body={"format": "structured", "marker": marker},
            body_plaintext=f"{marker}正文",
            change_summary=f"{marker}说明",
            created_by=article.owner,
            **workflow,
        )

    def get_as(self, actor, article=None):
        client = Client()
        client.force_login(actor)
        target = article or self.article
        return client.get(reverse("knowledge_manage:preview", args=[target.kb_no]))

    def test_owner_space_owner_and_admin_can_preview_through_working_reader(self):
        for actor in (self.owner, self.space_owner, self.admin):
            with self.subTest(actor=actor.username):
                with mock.patch(
                    "apps.knowledge.manage_views.get_manage_working_article_detail",
                    wraps=get_manage_working_article_detail,
                ) as reader:
                    response = self.get_as(actor)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Cache-Control"], "private, no-store")
                reader.assert_called_once_with(actor=mock.ANY, kb_no=self.article.kb_no)

    def test_preview_is_get_only_with_allow_and_no_store(self):
        client = Client()
        client.force_login(self.owner)
        url = reverse("knowledge_manage:preview", args=[self.article.kb_no])

        self.assertEqual(client.get(url).status_code, 200)
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(client, method)(url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "GET")
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_non_management_and_inactive_accounts_are_rejected(self):
        staff = self.make_user("preview-staff", is_staff=True)
        superuser = User.objects.create_superuser(
            username="preview-superuser", email="", password="unused"
        )
        inactive = self.make_user("preview-inactive", self.editor_group, is_active=False)
        disabled = self.make_user(
            "preview-disabled",
            self.editor_group,
            account_status=AccountStatus.DISABLED,
        )
        for actor, status in (
            (self.employee, 403),
            (self.reviewer, 403),
            (staff, 403),
            (superuser, 403),
            (inactive, 401),
            (disabled, 401),
        ):
            with self.subTest(actor=actor.username):
                response = self.get_as(actor)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_unauthorized_missing_and_invalid_working_are_safe_404(self):
        client = Client()
        client.force_login(self.owner)
        cases = (
            self.get_as(self.other_editor),
            client.get(reverse("knowledge_manage:preview", args=["KB-999999"])),
            self.get_as(self.owner, self.no_working),
            self.get_as(self.owner, self.non_draft),
        )
        for response in cases:
            with self.subTest(status=response.status_code):
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_preview_uses_only_working_draft_fields_and_plaintext_body(self):
        response = self.get_as(self.owner)

        self.assertContains(response, "草稿标题")
        self.assertContains(response, "草稿摘要")
        self.assertContains(response, "草稿正文第一行")
        self.assertContains(response, "草稿正文第二行")
        self.assertContains(response, "草稿版本说明")
        self.assertContains(response, "&quot;说明&quot;: &quot;中文范围&quot;", html=False)
        self.assertNotContains(response, "ARTICLE-兼容标题")
        self.assertNotContains(response, self.published.title)
        self.assertNotContains(response, "不得展示的结构化正文")

    def test_preview_has_prominent_draft_identity_and_real_navigation(self):
        response = self.get_as(self.owner)

        self.assertContains(response, "草稿预览")
        self.assertContains(response, "未发布")
        self.assertContains(response, self.article.kb_no)
        self.assertContains(response, "v2")
        self.assertContains(response, self.draft.get_status_display())
        self.assertContains(response, self.space.name)
        self.assertContains(response, self.category.name)
        self.assertContains(
            response,
            f'href="{reverse("knowledge_manage:edit", args=[self.article.kb_no])}"',
        )
        self.assertContains(response, f'href="{reverse("knowledge_manage:list")}"')

    def test_all_displayed_draft_values_are_autoescaped(self):
        ArticleVersion.objects.filter(pk=self.draft.pk).update(
            title="<script>alert('title')</script>",
            summary='<img src=x onerror="alert(1)">',
            applicable_scope={"x": "<script>alert('scope')</script>"},
            body_plaintext="<b>body</b>",
            change_summary="<em>change</em>",
        )

        response = self.get_as(self.owner)
        html = response.content.decode()
        for raw in (
            "<script>alert('title')</script>",
            '<img src=x onerror="alert(1)">',
            "<script>alert('scope')</script>",
            "<b>body</b>",
            "<em>change</em>",
        ):
            with self.subTest(raw=raw):
                self.assertNotIn(raw, html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img", html)
        self.assertIn("&lt;b&gt;body&lt;/b&gt;", html)
        self.assertIn("&lt;em&gt;change&lt;/em&gt;", html)

    def test_preview_get_is_completely_read_only(self):
        article_before = Article.objects.values().get(pk=self.article.pk)
        versions_before = list(
            ArticleVersion.objects.filter(article=self.article).order_by("pk").values()
        )
        review_count = ReviewRecord.objects.count()

        response = self.get_as(self.owner)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Article.objects.values().get(pk=self.article.pk), article_before)
        self.assertEqual(
            list(ArticleVersion.objects.filter(article=self.article).order_by("pk").values()),
            versions_before,
        )
        self.assertEqual(ReviewRecord.objects.count(), review_count)

    def test_preview_refresh_reads_the_new_current_working_draft(self):
        ArticleVersion.objects.filter(pk=self.draft.pk).update(status=VersionStatus.SAVED)
        new_draft = self.make_version(
            self.article,
            3,
            VersionStatus.DRAFT,
            marker="刷新后的新草稿",
        )
        Article.objects.filter(pk=self.article.pk).update(latest_working_version=new_draft)

        response = self.get_as(self.owner)

        self.assertContains(response, "刷新后的新草稿")
        self.assertContains(response, "v3")
        self.assertNotContains(response, "草稿标题")

    def test_unpublished_draft_is_manage_preview_only(self):
        preview = self.get_as(self.owner, self.unpublished)
        employee = Client()
        employee.force_login(self.employee)
        detail = employee.get(reverse("knowledge:article_detail", args=[self.unpublished.kb_no]))

        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "仅草稿秘密关键词")
        self.assertEqual(detail.status_code, 404)
        self.assertFalse(search_employee_articles(self.employee, "仅草稿秘密关键词").exists())

    def test_published_and_draft_read_paths_remain_strictly_isolated(self):
        preview = self.get_as(self.owner)
        employee = Client()
        employee.force_login(self.employee)
        detail_url = reverse("knowledge:article_detail", args=[self.article.kb_no])
        detail = employee.get(detail_url)

        self.assertContains(preview, "草稿标题")
        self.assertNotContains(preview, "正式标题")
        self.assertContains(detail, "正式标题")
        self.assertNotContains(detail, "草稿标题")
        self.assertEqual(
            list(search_employee_articles(self.employee, "正式标题").values_list("pk", flat=True)),
            [self.article.pk],
        )
        self.assertFalse(search_employee_articles(self.employee, "草稿标题").exists())

        for query in ("?preview=1", "?draft=1", "?include_draft=1"):
            with self.subTest(query=query):
                attacked = employee.get(detail_url + query)
                self.assertContains(attacked, "正式标题")
                self.assertNotContains(attacked, "草稿标题")
