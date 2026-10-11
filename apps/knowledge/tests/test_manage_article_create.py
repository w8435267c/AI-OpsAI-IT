"""Task 12E-03：管理侧 Article 创建表单与页面合同。"""

from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth.models import Group, Permission
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
from apps.knowledge.manage_forms import ArticleCreateForm
from apps.knowledge.models import (
    Article,
    ArticleType,
    ArticleVersion,
    AudiencePolicy,
    Category,
    KnowledgeNumberCounter,
    KnowledgeSpace,
    VersionStatus,
)
from apps.knowledge.services import ArticleCreationError


class ManageArticleCreateBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0, stdout=StringIO())
        cls.editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        cls.admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)
        cls.reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)

        cls.editor = cls.make_user("create-page-editor", cls.editor_group)
        cls.other_editor = cls.make_user("create-page-other-editor", cls.editor_group)
        cls.admin = cls.make_user("create-page-admin", cls.admin_group)
        cls.employee = cls.make_user("create-page-employee")
        cls.reviewer = cls.make_user("create-page-reviewer", cls.reviewer_group)
        cls.active_owner = cls.make_user("create-page-active-owner")
        cls.inactive_owner = cls.make_user("create-page-inactive-owner", is_active=False)
        cls.disabled_owner = cls.make_user(
            "create-page-disabled-owner",
            account_status=AccountStatus.DISABLED,
        )

        cls.editor_space = cls.make_space("create-editor", cls.editor)
        cls.editor_category = cls.make_category(cls.editor_space, "create-editor")
        cls.other_space = cls.make_space("create-other", cls.other_editor)
        cls.other_category = cls.make_category(cls.other_space, "create-other")
        cls.inactive_space = cls.make_space("create-inactive", cls.editor, is_active=False)
        cls.inactive_category = cls.make_category(cls.inactive_space, "create-inactive")
        cls.inactive_category.is_active = False
        cls.inactive_category.save(update_fields=["is_active"])

    @classmethod
    def make_user(cls, username, group=None, **kwargs):
        user = User.objects.create_user(username=username, **kwargs)
        if group is not None:
            user.groups.add(group)
        return user

    @classmethod
    def make_space(cls, code, owner, *, is_active=True):
        return KnowledgeSpace.objects.create(
            code=code,
            name=f"空间 {code}",
            space_type="employee",
            owner=owner,
            default_audience_policy=AudiencePolicy.RESTRICTED,
            is_active=is_active,
        )

    @classmethod
    def make_category(cls, space, code):
        return Category.objects.create(
            space=space,
            code=code,
            name=f"分类 {code}",
        )

    def valid_data(self, **overrides):
        data = {
            "space": str(self.editor_space.pk),
            "category": str(self.editor_category.pk),
            "article_type": ArticleType.GUIDE,
            "title": "新建知识标题",
            "summary": "新建知识摘要",
            "applicable_scope": '{"说明": "中文范围"}',
            "body_text": "第一步：检查网络。",
            "change_summary": "创建首个草稿",
            "audience_policy": AudiencePolicy.ALL_EMPLOYEES,
            "effective_at": "",
            "review_due_at": (timezone.now() + timedelta(days=180)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        data.update(overrides)
        return data


class ArticleCreateFormTests(ManageArticleCreateBase):
    def test_fields_are_explicit_and_editor_cannot_choose_owner(self):
        form = ArticleCreateForm(actor=self.editor)

        self.assertEqual(
            list(form.fields),
            [
                "space",
                "category",
                "article_type",
                "title",
                "summary",
                "applicable_scope",
                "body_text",
                "change_summary",
                "audience_policy",
                "effective_at",
                "review_due_at",
            ],
        )
        forbidden = {
            "kb_no",
            "version_no",
            "status",
            "lock_version",
            "latest_working_version",
            "current_published_version",
            "created_by",
            "updated_by",
            "submitted_by",
            "submitted_at",
            "published_at",
            "restored_from_version",
        }
        self.assertTrue(forbidden.isdisjoint(form.fields))

    def test_admin_can_choose_only_active_business_owner(self):
        form = ArticleCreateForm(actor=self.admin)

        self.assertIn("owner", form.fields)
        owners = form.fields["owner"].queryset
        self.assertIn(self.active_owner, owners)
        self.assertIn(self.admin, owners)
        self.assertNotIn(self.inactive_owner, owners)
        self.assertNotIn(self.disabled_owner, owners)

    def test_space_and_category_choices_follow_creation_contract(self):
        editor_form = ArticleCreateForm(actor=self.editor)
        admin_form = ArticleCreateForm(actor=self.admin)

        self.assertEqual(list(editor_form.fields["space"].queryset), [self.editor_space])
        self.assertEqual(
            list(editor_form.fields["category"].queryset),
            [self.editor_category],
        )
        self.assertIn(self.editor_space, admin_form.fields["space"].queryset)
        self.assertIn(self.other_space, admin_form.fields["space"].queryset)
        self.assertNotIn(self.inactive_space, admin_form.fields["space"].queryset)
        self.assertIn(self.other_category, admin_form.fields["category"].queryset)
        self.assertNotIn(self.inactive_category, admin_form.fields["category"].queryset)

    def test_model_choices_are_reused(self):
        form = ArticleCreateForm(actor=self.admin)

        self.assertEqual(list(form.fields["article_type"].choices), list(ArticleType.choices))
        self.assertEqual(
            list(form.fields["audience_policy"].choices)[1:],
            list(AudiencePolicy.choices),
        )

    def test_applicable_scope_accepts_empty_and_nested_objects(self):
        empty = ArticleCreateForm(actor=self.editor, data=self.valid_data(applicable_scope=""))
        nested = ArticleCreateForm(
            actor=self.editor,
            data=self.valid_data(applicable_scope='{"outer": {"inner": [1, 2]}}'),
        )

        self.assertTrue(empty.is_valid(), empty.errors)
        self.assertEqual(empty.cleaned_data["applicable_scope"], {})
        self.assertTrue(nested.is_valid(), nested.errors)
        self.assertEqual(nested.cleaned_data["applicable_scope"]["outer"]["inner"], [1, 2])

    def test_applicable_scope_rejects_non_object_json_and_invalid_json(self):
        for value in ("[]", '"abc"', "123", "true", "null", "{invalid"):
            with self.subTest(value=value):
                form = ArticleCreateForm(
                    actor=self.editor,
                    data=self.valid_data(applicable_scope=value),
                )
                self.assertFalse(form.is_valid())
                self.assertIn("applicable_scope", form.errors)

    def test_applicable_scope_keeps_chinese_and_invalid_raw_input(self):
        initial_form = ArticleCreateForm(
            actor=self.editor,
            initial={"applicable_scope": {"说明": "中文范围"}},
        )
        invalid_form = ArticleCreateForm(
            actor=self.editor,
            data=self.valid_data(applicable_scope="{中文-invalid"),
        )
        invalid_form.is_valid()

        self.assertIn("中文范围", initial_form["applicable_scope"].value())
        self.assertNotIn("\\u", initial_form["applicable_scope"].value())
        self.assertEqual(invalid_form["applicable_scope"].value(), "{中文-invalid")

    def test_space_category_mismatch_is_a_friendly_form_error(self):
        form = ArticleCreateForm(
            actor=self.admin,
            data=self.valid_data(
                space=str(self.editor_space.pk),
                category=str(self.other_category.pk),
                owner=str(self.active_owner.pk),
            ),
        )

        self.assertFalse(form.is_valid())
        self.assertIn("所选分类不属于该知识空间", form.errors["category"])


class ArticleCreateViewTests(ManageArticleCreateBase):
    def test_authorized_editor_and_admin_get_page_with_no_store(self):
        for actor in (self.editor, self.admin):
            with self.subTest(actor=actor.username):
                client = Client()
                client.force_login(actor)
                response = client.get(reverse("knowledge_manage:create"))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_invalid_account_and_non_management_roles_are_rejected(self):
        inactive = self.make_user("create-page-inactive", self.editor_group, is_active=False)
        disabled = self.make_user(
            "create-page-business-disabled",
            self.editor_group,
            account_status=AccountStatus.DISABLED,
        )
        staff = self.make_user("create-page-staff", is_staff=True)
        superuser = User.objects.create_superuser(
            username="create-page-superuser",
            email="",
            password="not-used-in-test",
        )

        for actor, expected in (
            (self.employee, 403),
            (self.reviewer, 403),
            (staff, 403),
            (superuser, 403),
            (inactive, 401),
            (disabled, 401),
        ):
            with self.subTest(actor=actor.username):
                client = Client()
                client.force_login(actor)
                response = client.get(reverse("knowledge_manage:create"))
                self.assertEqual(response.status_code, expected)
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_missing_creation_model_permission_is_403(self):
        permission = Permission.objects.get(
            content_type__app_label="knowledge",
            codename="add_articleversion",
        )
        self.editor_group.permissions.remove(permission)
        try:
            client = Client()
            client.force_login(self.editor)
            response = client.get(reverse("knowledge_manage:create"))
            self.assertEqual(response.status_code, 403)
        finally:
            self.editor_group.permissions.add(permission)

    def test_csrf_is_required_and_valid_token_creates_with_303(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.editor)
        url = reverse("knowledge_manage:create")

        missing = client.post(url, self.valid_data())
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(Article.objects.count(), 0)

        get_response = client.get(url)
        token = client.cookies["csrftoken"].value
        response = client.post(url, self.valid_data(csrfmiddlewaretoken=token))

        article = Article.objects.get()
        draft = ArticleVersion.objects.get()
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response["Location"],
            reverse("knowledge_manage:edit", args=[article.kb_no]),
        )
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(article.latest_working_version_id, draft.pk)
        self.assertIsNone(article.current_published_version_id)
        self.assertEqual(draft.status, VersionStatus.DRAFT)
        self.assertEqual(draft.version_no, 1)
        self.assertEqual(article.owner, self.editor)

    def test_client_authoritative_field_forgery_is_ignored(self):
        client = Client()
        client.force_login(self.editor)

        response = client.post(
            reverse("knowledge_manage:create"),
            self.valid_data(
                kb_no="KB-999999",
                version_no="99",
                status=VersionStatus.PUBLISHED,
                lock_version="999",
                owner=str(self.active_owner.pk),
            ),
        )

        article = Article.objects.get()
        draft = ArticleVersion.objects.get()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(article.kb_no, "KB-000001")
        self.assertEqual(article.owner, self.editor)
        self.assertEqual(draft.version_no, 1)
        self.assertEqual(draft.status, VersionStatus.DRAFT)
        self.assertEqual(draft.lock_version, 1)

    def test_admin_can_select_active_owner_in_any_active_space(self):
        client = Client()
        client.force_login(self.admin)

        response = client.post(
            reverse("knowledge_manage:create"),
            self.valid_data(
                space=str(self.other_space.pk),
                category=str(self.other_category.pk),
                owner=str(self.active_owner.pk),
            ),
        )

        article = Article.objects.get()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(article.owner, self.active_owner)
        self.assertEqual(article.space, self.other_space)

    def test_invalid_form_preserves_input_without_creating_or_consuming_number(self):
        client = Client()
        client.force_login(self.editor)
        counter_before = KnowledgeNumberCounter.objects.get(pk=1).next_value

        response = client.post(
            reverse("knowledge_manage:create"),
            self.valid_data(title="", applicable_scope="{invalid"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertContains(response, "{invalid")
        self.assertEqual(Article.objects.count(), 0)
        self.assertEqual(ArticleVersion.objects.count(), 0)
        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, counter_before)

    def test_service_errors_are_mapped_without_internal_details(self):
        cases = (
            ("ARTICLE_CREATE_PERMISSION_DENIED", 403),
            ("ARTICLE_CREATE_INVALID_INPUT", 200),
            ("SPACE_CATEGORY_MISMATCH", 200),
            ("KNOWLEDGE_NUMBER_COUNTER_MISSING", 503),
            ("KB_NUMBER_EXHAUSTED", 503),
            ("COUNTER_OUT_OF_SYNC", 503),
            ("MODEL_CONSISTENCY_FAILED", 503),
            ("DATABASE_WRITE_FAILED", 503),
        )
        for code, expected_status in cases:
            with self.subTest(code=code):
                client = Client()
                client.force_login(self.editor)
                with mock.patch(
                    "apps.knowledge.manage_views.create_article",
                    side_effect=ArticleCreationError(
                        code,
                        "安全公开提示，不包含数据库内部信息。",
                    ),
                ):
                    response = client.post(
                        reverse("knowledge_manage:create"),
                        self.valid_data(),
                    )
                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(response["Cache-Control"], "private, no-store")
                self.assertNotContains(response, "traceback", status_code=expected_status)
                self.assertNotContains(response, "constraint", status_code=expected_status)
                self.assertNotContains(response, "connection", status_code=expected_status)

    def test_list_has_real_create_link(self):
        client = Client()
        client.force_login(self.editor)

        response = client.get(reverse("knowledge_manage:list"))

        self.assertContains(response, reverse("knowledge_manage:create"))
        self.assertContains(response, "新建知识")
