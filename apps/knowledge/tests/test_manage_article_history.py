"""Task 12E-07：管理侧版本历史列表与详情合同。"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from uuid import uuid4

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountStatus, User
from apps.accounts.roles import (
    ROLE_EDITOR,
    ROLE_KNOWLEDGE_ADMIN,
    ROLE_REVIEWER,
    SYSTEM_ROLE_BY_CODE,
)
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
from apps.knowledge.version_readers import (
    ArticleVersionHistoryDetail,
    ArticleVersionHistoryReadError,
    get_article_version_history_detail,
)


class ManageArticleHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0, stdout=StringIO())
        cls.editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        cls.admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)
        cls.reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)

        cls.owner = cls.make_user("history-ui-owner", cls.editor_group)
        cls.space_owner = cls.make_user("history-ui-space-owner", cls.editor_group)
        cls.other_editor = cls.make_user("history-ui-other-editor", cls.editor_group)
        cls.admin = cls.make_user("history-ui-admin", cls.admin_group)
        cls.employee = cls.make_user("history-ui-employee")
        cls.reviewer = cls.make_user("history-ui-reviewer", cls.reviewer_group)

        cls.space = KnowledgeSpace.objects.create(
            code="history-ui-space",
            name="历史页面空间",
            space_type="employee",
            owner=cls.space_owner,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="history-ui-category",
            name="历史页面分类",
        )
        cls.article = cls.make_article("KB-340001", cls.owner, title="ARTICLE-兼容标题")

        cls.versions = []
        for version_no, status in enumerate(VersionStatus.values, start=1):
            workflow = {}
            if status not in (VersionStatus.DRAFT, VersionStatus.SAVED):
                workflow.update(submitted_by=cls.owner, submitted_at=timezone.now())
            if status == VersionStatus.PUBLISHED:
                workflow["published_at"] = timezone.now()
            version = ArticleVersion.objects.create(
                article=cls.article,
                version_no=version_no,
                status=status,
                title=f"VERSION-{version_no}-权威标题",
                summary=f"版本 {version_no} 摘要",
                applicable_scope={"说明": f"范围 {version_no}"},
                body_plaintext=(
                    f'<script>alert("history")</script>\n<img src=x>\nFULL-BODY-MARKER-{version_no}'
                ),
                change_summary=f"版本 {version_no} 说明",
                created_by=cls.owner,
                **workflow,
            )
            cls.versions.append(version)
        cls.saved = cls.versions[0]
        cls.published = next(
            version for version in cls.versions if version.status == VersionStatus.PUBLISHED
        )
        cls.draft = next(
            version for version in cls.versions if version.status == VersionStatus.DRAFT
        )
        ArticleVersion.objects.filter(pk=cls.draft.pk).update(restored_from_version=cls.saved)
        cls.draft.refresh_from_db()
        Article.objects.filter(pk=cls.article.pk).update(
            latest_working_version=cls.draft,
            current_published_version=cls.published,
        )

        cls.other_space = KnowledgeSpace.objects.create(
            code="history-ui-other-space",
            name="无权历史空间",
            space_type="employee",
            owner=cls.other_editor,
        )
        cls.other_category = Category.objects.create(
            space=cls.other_space,
            code="history-ui-other-category",
            name="无权历史分类",
        )
        cls.other_article = cls.make_article(
            "KB-340002",
            cls.other_editor,
            title="OTHER-ARTICLE",
            space=cls.other_space,
            category=cls.other_category,
        )
        cls.other_version = cls.make_version(cls.other_article, 1, "OTHER-SECRET")

        cls.single_article = cls.make_article("KB-340003", cls.owner, title="单版本文章")
        cls.make_version(cls.single_article, 1, "单版本")
        cls.twenty_article = cls.make_article("KB-340004", cls.owner, title="二十版本文章")
        for number in range(1, 21):
            cls.make_version(cls.twenty_article, number, f"批量版本 {number}")

        cls.paged_article = cls.make_article("KB-340005", cls.owner, title="分页文章")
        for number in range(1, 26):
            cls.make_version(cls.paged_article, number, f"分页版本 {number}")

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
    def make_version(cls, article, version_no, title):
        return ArticleVersion.objects.create(
            article=article,
            version_no=version_no,
            status=VersionStatus.SAVED,
            title=title,
            summary=f"{title} 摘要",
            body_plaintext=f"{title} 正文",
            change_summary=f"{title} 说明",
            created_by=article.owner,
        )

    def get_as(self, actor, name="history", *, article=None, version=None, query=""):
        client = Client()
        client.force_login(actor)
        target_article = article or self.article
        args = [target_article.kb_no]
        if version is not None:
            args.append(version.pk if hasattr(version, "pk") else version)
        return client.get(reverse(f"knowledge_manage:{name}", args=args) + query)

    def test_history_and_detail_are_get_only_and_private(self):
        history_url = reverse("knowledge_manage:history", args=[self.article.kb_no])
        detail_url = reverse(
            "knowledge_manage:history_detail", args=[self.article.kb_no, self.saved.pk]
        )
        client = Client()
        client.force_login(self.owner)
        for url in (history_url, detail_url):
            with self.subTest(url=url):
                response = client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Cache-Control"], "private, no-store")
                for method in ("post", "put", "patch", "delete"):
                    denied = getattr(client, method)(url)
                    self.assertEqual(denied.status_code, 405)
                    self.assertEqual(denied["Allow"], "GET")
                    self.assertEqual(denied["Cache-Control"], "private, no-store")

    def test_owner_space_owner_and_admin_can_view_history(self):
        for actor in (self.owner, self.space_owner, self.admin):
            with self.subTest(actor=actor.username):
                self.assertEqual(self.get_as(actor).status_code, 200)

    def test_non_management_and_inactive_accounts_are_rejected(self):
        staff = self.make_user("history-ui-staff", is_staff=True)
        superuser = User.objects.create_superuser(
            username="history-ui-superuser", email="", password="unused"
        )
        inactive = self.make_user("history-ui-inactive", self.editor_group, is_active=False)
        disabled = self.make_user(
            "history-ui-disabled",
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

    def test_unauthorized_and_missing_articles_are_safe_404(self):
        denied = self.get_as(self.other_editor)
        missing = self.get_as(
            self.owner,
            article=Article(kb_no="KB-999999"),
        )
        for response in (denied, missing):
            self.assertEqual(response.status_code, 404)
            self.assertNotContains(response, "ARTICLE-兼容标题", status_code=404)

    def test_list_shows_all_statuses_in_reader_order_and_version_titles(self):
        response = self.get_as(self.owner)
        self.assertEqual(response.status_code, 200)
        rows = list(response.context["versions"])
        self.assertEqual(
            [row.version_no for row in rows],
            sorted([row.version_no for row in self.versions], reverse=True),
        )
        self.assertEqual({row.status for row in rows}, set(VersionStatus.values))
        for version in self.versions:
            self.assertContains(response, version.title)
        self.assertNotContains(response, "ARTICLE-兼容标题")
        self.assertContains(response, "当前工作草稿")
        self.assertContains(response, "当前发布版本")
        self.assertContains(response, "恢复自 v1")
        self.assertNotContains(response, "FULL-BODY-MARKER")

    def test_list_paginates_twenty_after_filtering_and_handles_invalid_pages(self):
        first = self.get_as(self.owner, article=self.paged_article)
        nonnumeric = self.get_as(self.owner, article=self.paged_article, query="?page=nope")
        negative = self.get_as(self.owner, article=self.paged_article, query="?page=-1")
        out_of_range = self.get_as(self.owner, article=self.paged_article, query="?page=999")

        self.assertEqual(len(first.context["versions"]), 20)
        self.assertEqual(first.context["pagination"]["number"], 1)
        self.assertEqual(nonnumeric.context["pagination"]["number"], 1)
        self.assertEqual(negative.context["pagination"]["number"], 2)
        self.assertEqual(out_of_range.context["pagination"]["number"], 2)
        self.assertEqual(len(out_of_range.context["versions"]), 5)

    def test_history_query_count_does_not_grow_per_row(self):
        client = Client()
        client.force_login(self.owner)
        with CaptureQueriesContext(connection) as single_queries:
            single = client.get(
                reverse("knowledge_manage:history", args=[self.single_article.kb_no])
            )
        with CaptureQueriesContext(connection) as twenty_queries:
            twenty = client.get(
                reverse("knowledge_manage:history", args=[self.twenty_article.kb_no])
            )
        self.assertEqual(single.status_code, 200)
        self.assertEqual(twenty.status_code, 200)
        self.assertLessEqual(len(twenty_queries), len(single_queries) + 1)

    def test_detail_reader_returns_safe_dto_and_rejects_cross_article_version(self):
        detail = get_article_version_history_detail(
            actor=self.owner,
            kb_no=self.article.kb_no,
            version_id=self.published.pk,
        )
        self.assertIsInstance(detail, ArticleVersionHistoryDetail)
        self.assertEqual(detail.version_no, self.published.version_no)
        self.assertEqual(detail.title, self.published.title)
        self.assertTrue(detail.is_current_published)
        self.assertFalse(hasattr(detail, "save"))

        for version_id in (self.other_version.pk, uuid4()):
            with self.subTest(version_id=version_id):
                with self.assertRaises(ArticleVersionHistoryReadError) as caught:
                    get_article_version_history_detail(
                        actor=self.owner,
                        kb_no=self.article.kb_no,
                        version_id=version_id,
                    )
                self.assertEqual(
                    caught.exception.code,
                    "ARTICLE_VERSION_HISTORY_NOT_FOUND_OR_INACCESSIBLE",
                )

    def test_detail_displays_plaintext_pretty_scope_metadata_flags_and_safe_xss(self):
        response = self.get_as(
            self.owner,
            "history_detail",
            version=self.published,
        )
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        for value in (
            self.article.kb_no,
            f"v{self.published.version_no}",
            self.published.get_status_display(),
            self.published.title,
            self.published.summary,
            self.published.change_summary,
            self.owner.username,
            "  &quot;说明&quot;: &quot;范围",
            "当前发布版本",
        ):
            self.assertContains(response, value, html=False)
        self.assertNotIn('<script>alert("history")</script>', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertContains(response, "恢复此版本")
        self.assertContains(response, "恢复不会修改历史记录")

    def test_list_and_detail_escape_version_text_fields(self):
        ArticleVersion.objects.filter(pk=self.saved.pk).update(
            title="<script>alert('title')</script>",
            summary='<img src=x onerror="alert(1)">',
            change_summary="<b>change</b>",
        )
        history = self.get_as(self.owner)
        detail = self.get_as(self.owner, "history_detail", version=self.saved)
        for response in (history, detail):
            html = response.content.decode()
            self.assertNotIn("<script>alert('title')</script>", html)
            self.assertNotIn('<img src=x onerror="alert(1)">', html)
            self.assertNotIn("<b>change</b>", html)
        self.assertContains(history, "&lt;script&gt;", html=False)
        self.assertContains(detail, "&lt;img", html=False)
        self.assertContains(detail, "&lt;b&gt;change&lt;/b&gt;", html=False)

    def test_draft_detail_is_viewable_without_restore_button(self):
        response = self.get_as(self.owner, "history_detail", version=self.draft)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "当前工作草稿")
        self.assertNotContains(response, "恢复此版本")

    def test_cross_article_missing_and_unauthorized_detail_are_404(self):
        for actor, version in (
            (self.owner, self.other_version),
            (self.owner, uuid4()),
            (self.other_editor, self.saved),
        ):
            with self.subTest(actor=actor.username, version=version):
                response = self.get_as(actor, "history_detail", version=version)
                self.assertEqual(response.status_code, 404)

    def test_history_gets_do_not_write_any_database_state(self):
        article_before = Article.objects.values().get(pk=self.article.pk)
        versions_before = list(
            ArticleVersion.objects.filter(article=self.article).order_by("pk").values()
        )
        review_count = ReviewRecord.objects.count()

        list_response = self.get_as(self.owner)
        detail_response = self.get_as(self.owner, "history_detail", version=self.published)

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(Article.objects.values().get(pk=self.article.pk), article_before)
        self.assertEqual(
            list(ArticleVersion.objects.filter(article=self.article).order_by("pk").values()),
            versions_before,
        )
        self.assertEqual(ReviewRecord.objects.count(), review_count)

    def test_manage_list_has_real_history_link_only(self):
        client = Client()
        client.force_login(self.owner)
        response = client.get(reverse("knowledge_manage:list"))
        expected = reverse("knowledge_manage:history", args=[self.article.kb_no])
        self.assertContains(response, f'href="{expected}"')
        self.assertContains(response, "版本历史")
        self.assertNotContains(response, "预览")
