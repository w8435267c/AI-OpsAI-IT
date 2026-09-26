"""Task 9A：空间、分类与文章受众的安全 Admin 维护入口。"""

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.admin_helpers import build_change_post_data
from apps.knowledge.admin import ArticleAudienceAdmin, CategoryAdmin, KnowledgeSpaceAdmin
from apps.knowledge.models import (
    Article,
    ArticleAudience,
    ArticleType,
    AudienceEffect,
    AudiencePolicy,
    AudienceType,
    Category,
    KnowledgeSpace,
    SpaceType,
)

User = get_user_model()


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class KnowledgeAdminMaintenanceTests(TestCase):
    """知识管理员可维护基础对象，稳定身份和受众证据不可伪造。"""

    @classmethod
    def setUpTestData(cls):
        call_command("create_dev_users")
        cls.admin_user = User.objects.get(username="dev_knowledge_admin")
        cls.target = User.objects.create_user(username="audience-target")
        cls.other_creator = User.objects.create_user(username="original-rule-creator")
        cls.space = KnowledgeSpace.objects.create(
            code="TASK9A",
            name="Task 9A 空间",
            space_type=SpaceType.EMPLOYEE,
            owner=cls.admin_user,
        )
        cls.category = Category.objects.create(
            space=cls.space, code="TASK9A-CAT", name="Task 9A 分类"
        )
        cls.article = Article.objects.create(
            kb_no="KB-920001",
            title="Task 9A 受众测试",
            space=cls.space,
            category=cls.category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.RESTRICTED,
            owner=cls.admin_user,
            created_by=cls.admin_user,
            updated_by=cls.admin_user,
            review_due_at=timezone.now() + timedelta(days=30),
        )
        cls.rule = ArticleAudience.objects.create(
            article=cls.article,
            audience_type=AudienceType.USER,
            effect=AudienceEffect.ALLOW,
            user=cls.target,
            created_by=cls.other_creator,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin_user)

    @staticmethod
    def _add_url(model):
        return reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_add")

    @staticmethod
    def _change_url(obj):
        return reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk])

    def test_space_and_category_stable_codes_readonly_after_creation(self):
        request = RequestFactory().get("/admin/")
        request.user = self.admin_user
        space_form = KnowledgeSpaceAdmin(KnowledgeSpace, admin.site).get_form(
            request, obj=self.space
        )
        category_form = CategoryAdmin(Category, admin.site).get_form(request, obj=self.category)
        self.assertNotIn("code", space_form.base_fields)
        self.assertNotIn("code", category_form.base_fields)

    def test_space_allowed_fields_change_but_code_does_not(self):
        model_admin = KnowledgeSpaceAdmin(KnowledgeSpace, admin.site)
        data = build_change_post_data(
            model_admin,
            self.admin_user,
            self.space,
            name="Task 9A 新名称",
            code="FORGED-CODE",
        )
        response = self.client.post(self._change_url(self.space), data)
        self.assertEqual(response.status_code, 302)
        self.space.refresh_from_db()
        self.assertEqual(self.space.name, "Task 9A 新名称")
        self.assertEqual(self.space.code, "TASK9A")

    def test_category_space_and_code_do_not_change(self):
        other_space = KnowledgeSpace.objects.create(
            code="TASK9A-OTHER",
            name="其他空间",
            space_type=SpaceType.EMPLOYEE,
            owner=self.admin_user,
        )
        model_admin = CategoryAdmin(Category, admin.site)
        data = build_change_post_data(
            model_admin,
            self.admin_user,
            self.category,
            name="允许修改的新分类名",
            code="FORGED-CATEGORY-CODE",
            space=other_space.pk,
        )
        response = self.client.post(self._change_url(self.category), data)
        self.assertEqual(response.status_code, 302)
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "允许修改的新分类名")
        self.assertEqual(self.category.code, "TASK9A-CAT")
        self.assertEqual(self.category.space, self.space)

    def test_category_cycle_rejected_without_partial_change(self):
        child = Category.objects.create(
            space=self.space,
            code="TASK9A-CHILD",
            name="子分类",
            parent=self.category,
        )
        model_admin = CategoryAdmin(Category, admin.site)
        data = build_change_post_data(
            model_admin,
            self.admin_user,
            self.category,
            name="不得保存的循环",
            parent=child.pk,
        )
        response = self.client.post(self._change_url(self.category), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("循环", str(response.context["adminform"].form.errors))
        self.category.refresh_from_db()
        self.assertIsNone(self.category.parent_id)
        self.assertEqual(self.category.name, "Task 9A 分类")

    def test_knowledge_admin_can_add_legal_audience_with_server_creator(self):
        response = self.client.post(
            self._add_url(ArticleAudience),
            {
                "article": self.article.pk,
                "audience_type": AudienceType.USER,
                "effect": AudienceEffect.DENY,
                "department": "",
                "user_group": "",
                "user": self.admin_user.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        rule = ArticleAudience.objects.get(
            article=self.article,
            audience_type=AudienceType.USER,
            effect=AudienceEffect.DENY,
            user=self.admin_user,
        )
        self.assertEqual(rule.created_by, self.admin_user)

    def test_audience_creator_cannot_be_forged_on_change(self):
        model_admin = ArticleAudienceAdmin(ArticleAudience, admin.site)
        data = build_change_post_data(
            model_admin,
            self.admin_user,
            self.rule,
            effect=AudienceEffect.DENY,
            created_by=self.admin_user.pk,
        )
        response = self.client.post(self._change_url(self.rule), data)
        self.assertEqual(response.status_code, 302)
        self.rule.refresh_from_db()
        self.assertEqual(self.rule.effect, AudienceEffect.DENY)
        self.assertEqual(self.rule.created_by, self.other_creator)

    def test_invalid_audience_policy_combination_rejected(self):
        Article.objects.filter(pk=self.article.pk).update(
            audience_policy=AudiencePolicy.ALL_EMPLOYEES
        )
        response = self.client.post(
            self._add_url(ArticleAudience),
            {
                "article": self.article.pk,
                "audience_type": AudienceType.USER,
                "effect": AudienceEffect.ALLOW,
                "department": "",
                "user_group": "",
                "user": self.admin_user.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("audience_type", response.context["adminform"].form.errors)
        self.assertFalse(
            ArticleAudience.objects.filter(
                article=self.article,
                audience_type=AudienceType.USER,
                effect=AudienceEffect.ALLOW,
                user=self.admin_user,
            ).exists()
        )

    def test_knowledge_admin_cannot_delete_audience_rule(self):
        response = self.client.post(
            reverse("admin:knowledge_articleaudience_delete", args=[self.rule.pk]),
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ArticleAudience.objects.filter(pk=self.rule.pk).exists())
