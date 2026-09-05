"""知识库 Admin 权限边界：审核记录不可篡改、版本受 Service 保护、文章生命周期字段只读。"""

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.accounts.tests.admin_helpers import build_change_post_data
from apps.knowledge.admin import ArticleAdmin, ArticleVersionAdmin
from apps.knowledge.models import Article, ArticleVersion, Category, KnowledgeSpace, ReviewRecord

User = get_user_model()


def _create_article_chain(owner, reviewer):
    """创建 空间→分类→文章→版本→审核记录 的测试数据链。"""
    space = KnowledgeSpace.objects.create(
        name="保护测试空间",
        code="PROTECT-SPACE",
        space_type=KnowledgeSpace._meta.get_field("space_type").choices[0][0],
        owner=owner,
    )
    category = Category.objects.create(name="保护测试分类", code="PROTECT-CAT", space=space)
    article = Article.objects.create(
        kb_no="KB-910001",
        title="保护测试文章",
        space=space,
        category=category,
        article_type=Article._meta.get_field("article_type").choices[0][0],
        audience_policy=Article._meta.get_field("audience_policy").choices[0][0],
        owner=owner,
        created_by=owner,
        updated_by=owner,
        review_due_at=timezone.now() + timedelta(days=30),
    )
    version = ArticleVersion.objects.create(
        article=article,
        version_no=1,
        status=ArticleVersion._meta.get_field("status").choices[0][0],
        title="保护测试版本",
        summary="保护测试摘要",
        applicable_scope={},
        created_by=owner,
    )
    review = ReviewRecord.objects.create(
        article_version=version,
        review_type=ReviewRecord._meta.get_field("review_type").choices[0][0],
        reviewer=reviewer,
        decision=ReviewRecord._meta.get_field("decision").choices[0][0],
        comment="原始审核意见",
    )
    return space, category, article, version, review


class _BaseKnowledgeAdminProtectionTests(TestCase):
    """共享数据链与客户端构造。"""

    @classmethod
    def setUpTestData(cls):
        call_command("create_dev_users")
        cls.admin_user = User.objects.get(username="dev_knowledge_admin")
        cls.reviewer = User.objects.get(username="dev_reviewer")
        cls.superuser = User.objects.create_superuser(username="ops_root", password="RootPw2026")
        cls.space, cls.category, cls.article, cls.version, cls.review = _create_article_chain(
            cls.admin_user, cls.reviewer
        )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        return client


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class ReviewRecordAdminProtectionTests(_BaseKnowledgeAdminProtectionTests):
    """ReviewRecordAdmin：任何人（含超级管理员）都只能只读，禁止后台增改删。"""

    def test_admin_can_view_readonly(self):
        response = self._client(self.admin_user).get(
            f"/admin/knowledge/reviewrecord/{self.review.pk}/change/"
        )
        self.assertEqual(response.status_code, 200)

    def test_admin_cannot_add(self):
        response = self._client(self.admin_user).get("/admin/knowledge/reviewrecord/add/")
        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_change_decision_or_comment(self):
        other_decision = [
            c[0]
            for c in ReviewRecord._meta.get_field("decision").choices
            if c[0] != self.review.decision
        ][0]
        response = self._client(self.admin_user).post(
            f"/admin/knowledge/reviewrecord/{self.review.pk}/change/",
            {"decision": other_decision, "comment": "被篡改的审核意见"},
        )
        self.assertEqual(response.status_code, 403)
        self.review.refresh_from_db()
        self.assertNotEqual(self.review.decision, other_decision)
        self.assertEqual(self.review.comment, "原始审核意见")

    def test_admin_cannot_delete(self):
        response = self._client(self.admin_user).post(
            f"/admin/knowledge/reviewrecord/{self.review.pk}/delete/", {"post": "yes"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ReviewRecord.objects.filter(pk=self.review.pk).exists())

    def test_reviewer_cannot_change(self):
        # 审核员 is_staff=False，连后台入口都会被重定向到登录页，
        # 更不可能改写审核记录。
        response = self._client(self.reviewer).post(
            f"/admin/knowledge/reviewrecord/{self.review.pk}/change/",
            {"comment": "审核员篡改"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)
        self.review.refresh_from_db()
        self.assertEqual(self.review.comment, "原始审核意见")

    def test_superuser_cannot_change_via_admin(self):
        # 超级管理员也不得通过普通 Admin 页面改写审核记录；
        # 记录只能由正式审核 Service 在事务中创建。
        response = self._client(self.superuser).post(
            f"/admin/knowledge/reviewrecord/{self.review.pk}/change/",
            {"comment": "超级管理员篡改"},
        )
        self.assertEqual(response.status_code, 403)
        self.review.refresh_from_db()
        self.assertEqual(self.review.comment, "原始审核意见")


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class ArticleVersionAdminProtectionTests(_BaseKnowledgeAdminProtectionTests):
    """ArticleVersionAdmin：非超级管理员只读；超级管理员保留开发期 break-glass。"""

    def test_admin_can_view_version(self):
        response = self._client(self.admin_user).get(
            f"/admin/knowledge/articleversion/{self.version.pk}/change/"
        )
        self.assertEqual(response.status_code, 200)

    def test_admin_cannot_change_version(self):
        version_admin = ArticleVersionAdmin(ArticleVersion, admin.site)
        data = build_change_post_data(
            version_admin,
            self.admin_user,
            self.version,
            title="被篡改的版本标题",
            summary="被篡改的摘要",
            change_summary="篡改说明",
        )
        response = self._client(self.admin_user).post(
            f"/admin/knowledge/articleversion/{self.version.pk}/change/", data
        )
        self.assertEqual(response.status_code, 403)
        self.version.refresh_from_db()
        self.assertEqual(self.version.title, "保护测试版本")
        self.assertEqual(self.version.summary, "保护测试摘要")

    def test_admin_cannot_add_or_delete_version(self):
        response = self._client(self.admin_user).get("/admin/knowledge/articleversion/add/")
        self.assertEqual(response.status_code, 403)
        response = self._client(self.admin_user).post(
            f"/admin/knowledge/articleversion/{self.version.pk}/delete/", {"post": "yes"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ArticleVersion.objects.filter(pk=self.version.pk).exists())

    def test_superuser_break_glass_change_allowed(self):
        # 开发期 break-glass：超级管理员保留修改能力（报告中明示，
        # 该能力绝不授予知识库管理员）。
        version_admin = ArticleVersionAdmin(ArticleVersion, admin.site)
        data = build_change_post_data(
            version_admin,
            self.superuser,
            self.version,
            title="应急修正的版本标题",
            change_summary="应急修正说明",
        )
        response = self._client(self.superuser).post(
            f"/admin/knowledge/articleversion/{self.version.pk}/change/", data
        )
        self.assertEqual(response.status_code, 302)
        self.version.refresh_from_db()
        self.assertEqual(self.version.title, "应急修正的版本标题")


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class ArticleAdminLifecycleProtectionTests(_BaseKnowledgeAdminProtectionTests):
    """ArticleAdmin：生命周期字段只读，新增保持关闭。"""

    def test_article_add_still_disabled(self):
        response = self._client(self.admin_user).get("/admin/knowledge/article/add/")
        self.assertEqual(response.status_code, 403)

    def test_lifecycle_fields_excluded_from_form(self):
        request = RequestFactory().get("/admin/dummy/")
        request.user = self.admin_user
        form_cls = ArticleAdmin(Article, admin.site).get_form(request, obj=self.article)
        for field in (
            "kb_no",
            "article_status",
            "current_published_version",
            "latest_working_version",
            "created_by",
            "updated_by",
        ):
            self.assertNotIn(field, form_cls.base_fields, f"字段 {field} 不应出现在可编辑表单中")

    def test_lifecycle_fields_readonly_via_post(self):
        # 直接 POST 伪造编号/状态/版本指针：即使表单提交成功也不得写入。
        other_status = [
            c[0]
            for c in Article._meta.get_field("article_status").choices
            if c[0] != self.article.article_status
        ][0]
        article_admin = ArticleAdmin(Article, admin.site)
        data = build_change_post_data(
            article_admin,
            self.admin_user,
            self.article,
            kb_no="KB-999999",
            article_status=other_status,
            current_published_version=self.version.pk,
            latest_working_version=self.version.pk,
        )
        response = self._client(self.admin_user).post(
            f"/admin/knowledge/article/{self.article.pk}/change/", data
        )
        self.assertEqual(response.status_code, 302)
        self.article.refresh_from_db()
        self.assertEqual(self.article.kb_no, "KB-910001")
        self.assertNotEqual(self.article.article_status, other_status)
        self.assertIsNone(self.article.current_published_version_id)
        self.assertIsNone(self.article.latest_working_version_id)
