"""Task 12E-03：创建成功后的最小 working DRAFT 落地页合同。"""

from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountStatus, User
from apps.accounts.roles import (
    ROLE_EDITOR,
    ROLE_KNOWLEDGE_ADMIN,
    ROLE_REVIEWER,
    SYSTEM_ROLE_BY_CODE,
)
from apps.knowledge.manage_readers import (
    ManageWorkingArticleDetail,
    get_manage_working_article_detail,
)
from apps.knowledge.models import (
    Article,
    ArticleStatus,
    ArticleType,
    ArticleVersion,
    AudiencePolicy,
    Category,
    KnowledgeSpace,
    VersionStatus,
)


class ManageArticleEditPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0, stdout=StringIO())
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)

        cls.article_owner = cls.make_user("edit-page-owner", editor_group)
        cls.space_owner = cls.make_user("edit-page-space-owner", editor_group)
        cls.other_editor = cls.make_user("edit-page-other-editor", editor_group)
        cls.admin = cls.make_user("edit-page-admin", admin_group)
        cls.employee = cls.make_user("edit-page-employee")
        cls.reviewer = cls.make_user("edit-page-reviewer", reviewer_group)

        cls.space = KnowledgeSpace.objects.create(
            code="edit-page-space",
            name="编辑落地空间",
            space_type="employee",
            owner=cls.space_owner,
            default_audience_policy=AudiencePolicy.RESTRICTED,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="edit-page-category",
            name="编辑落地分类",
        )
        cls.article = cls.make_article(
            "KB-310001",
            owner=cls.article_owner,
            title="OLD-COMPAT-TITLE",
        )
        source = ArticleVersion.objects.create(
            article=cls.article,
            version_no=1,
            status=VersionStatus.SAVED,
            title="历史来源",
            summary="历史摘要",
            change_summary="历史说明",
            created_by=cls.article_owner,
        )
        draft = ArticleVersion.objects.create(
            article=cls.article,
            version_no=2,
            status=VersionStatus.DRAFT,
            lock_version=7,
            title="REAL-DRAFT-TITLE",
            summary="当前草稿摘要",
            applicable_scope={"说明": "中文范围", "nested": {"value": 1}},
            body_plaintext='<script>alert("draft")</script>\n<img src=x>\n<b>正文</b>',
            change_summary="当前草稿说明",
            restored_from_version=source,
            created_by=cls.article_owner,
        )
        Article.objects.filter(pk=cls.article.pk).update(latest_working_version=draft)

        cls.other_space = KnowledgeSpace.objects.create(
            code="edit-page-other-space",
            name="其他编辑空间",
            space_type="employee",
            owner=cls.other_editor,
        )
        cls.other_category = Category.objects.create(
            space=cls.other_space,
            code="edit-page-other-category",
            name="其他编辑分类",
        )
        cls.other_article = cls.make_article(
            "KB-310002",
            owner=cls.other_editor,
            title="其他兼容标题",
            space=cls.other_space,
            category=cls.other_category,
        )
        other_draft = ArticleVersion.objects.create(
            article=cls.other_article,
            version_no=1,
            status=VersionStatus.DRAFT,
            title="其他秘密草稿",
            summary="其他摘要",
            body_plaintext="其他正文",
            change_summary="其他说明",
            created_by=cls.other_editor,
        )
        Article.objects.filter(pk=cls.other_article.pk).update(latest_working_version=other_draft)

        cls.no_working_article = cls.make_article(
            "KB-310003",
            owner=cls.article_owner,
            title="无草稿兼容标题",
        )
        cls.non_draft_article = cls.make_article(
            "KB-310004",
            owner=cls.article_owner,
            title="错误指针兼容标题",
        )
        saved = ArticleVersion.objects.create(
            article=cls.non_draft_article,
            version_no=1,
            status=VersionStatus.SAVED,
            title="错误指针版本",
            summary="错误摘要",
            body_plaintext="错误正文",
            change_summary="错误说明",
            created_by=cls.article_owner,
        )
        Article.objects.filter(pk=cls.non_draft_article.pk).update(latest_working_version=saved)

    @classmethod
    def make_user(cls, username, group=None, **kwargs):
        user = User.objects.create_user(username=username, **kwargs)
        if group is not None:
            user.groups.add(group)
        return user

    @classmethod
    def make_article(cls, kb_no, *, owner, title, space=None, category=None):
        return Article.objects.create(
            kb_no=kb_no,
            title=title,
            space=space or cls.space,
            category=category or cls.category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.RESTRICTED,
            owner=owner,
            article_status=ArticleStatus.ACTIVE,
            created_by=owner,
            updated_by=owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )

    def get_as(self, actor, article=None):
        client = Client()
        client.force_login(actor)
        target = article or self.article
        return client.get(reverse("knowledge_manage:edit", args=[target.kb_no]))

    def test_reader_returns_safe_working_draft_dto(self):
        detail = get_manage_working_article_detail(
            actor=self.article_owner,
            kb_no=self.article.kb_no,
        )

        self.assertIsInstance(detail, ManageWorkingArticleDetail)
        self.assertEqual(detail.title, "REAL-DRAFT-TITLE")
        self.assertEqual(detail.version_no, 2)
        self.assertEqual(detail.lock_version, 7)
        self.assertEqual(detail.restored_from_version_no, 1)
        self.assertFalse(hasattr(detail, "save"))

    def test_owner_space_owner_and_admin_can_open(self):
        for actor in (self.article_owner, self.space_owner, self.admin):
            with self.subTest(actor=actor.username):
                response = self.get_as(actor)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_non_management_roles_staff_and_superuser_are_403(self):
        staff = self.make_user("edit-page-staff", is_staff=True)
        superuser = User.objects.create_superuser(
            username="edit-page-superuser",
            email="",
            password="not-used-in-test",
        )
        for actor in (self.employee, self.reviewer, staff, superuser):
            with self.subTest(actor=actor.username):
                self.assertEqual(self.get_as(actor).status_code, 403)

    def test_inactive_and_business_inactive_are_401(self):
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        inactive = self.make_user("edit-page-inactive", editor_group, is_active=False)
        disabled = self.make_user(
            "edit-page-disabled",
            editor_group,
            account_status=AccountStatus.DISABLED,
        )
        for actor in (inactive, disabled):
            with self.subTest(actor=actor.username):
                self.assertEqual(self.get_as(actor).status_code, 401)

    def test_unauthorized_missing_and_invalid_working_are_same_safe_404(self):
        unauthorized = self.get_as(self.other_editor)
        client = Client()
        client.force_login(self.article_owner)
        missing = client.get(reverse("knowledge_manage:edit", args=["KB-999999"]))
        no_working = self.get_as(self.article_owner, self.no_working_article)
        non_draft = self.get_as(self.article_owner, self.non_draft_article)

        for response in (unauthorized, missing, no_working, non_draft):
            with self.subTest(status=response.status_code):
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_page_uses_draft_title_and_escapes_plaintext_body(self):
        response = self.get_as(self.article_owner)

        self.assertContains(response, "REAL-DRAFT-TITLE")
        self.assertNotContains(response, "OLD-COMPAT-TITLE")
        self.assertContains(response, "&lt;script&gt;", html=False)
        self.assertContains(response, "&lt;img src=x&gt;", html=False)
        self.assertContains(response, "&lt;b&gt;正文&lt;/b&gt;", html=False)
        self.assertNotContains(response, '<script>alert("draft")</script>', html=False)

    def test_page_formats_scope_and_shows_read_only_version_metadata(self):
        response = self.get_as(self.article_owner)

        self.assertContains(response, "&quot;说明&quot;: &quot;中文范围&quot;", html=False)
        self.assertContains(response, "当前为草稿")
        self.assertContains(response, "v2")
        self.assertContains(response, "锁版本 7")
        self.assertContains(response, "恢复自 v1")
        self.assertContains(response, self.space.name)
        self.assertContains(response, self.category.name)
        self.assertContains(response, str(self.article_owner))

    def test_page_is_get_only_and_contains_no_write_or_task13_controls(self):
        client = Client()
        client.force_login(self.article_owner)
        url = reverse("knowledge_manage:edit", args=[self.article.kb_no])

        response = client.post(url)
        page = client.get(url)

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "GET")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertNotContains(page, "<form", html=False)
        self.assertNotContains(page, "保存版本")
        self.assertNotContains(page, "提交审核")
        self.assertNotContains(page, "发布")
