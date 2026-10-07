"""Task 12C：Article 与首个 DRAFT 原子创建 Service。"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import AnonymousUser, Group
from django.core.management import call_command
from django.db import DatabaseError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import AccountStatus, User
from apps.accounts.roles import ROLE_EDITOR, ROLE_KNOWLEDGE_ADMIN, SYSTEM_ROLE_BY_CODE
from apps.knowledge.content import build_plaintext_body
from apps.knowledge.models import (
    Article,
    ArticleStatus,
    ArticleType,
    ArticleVersion,
    AudiencePolicy,
    Category,
    KnowledgeNumberCounter,
    KnowledgeSpace,
    ReviewRecord,
    VersionStatus,
)
from apps.knowledge.readers import employee_visible_articles, get_employee_article_detail
from apps.knowledge.services import ArticleCreationError, create_article
from apps.search.readers import search_employee_articles


class PlaintextBodyTests(SimpleTestCase):
    def test_builds_authoritative_body_and_matching_plaintext(self):
        body_text = "第一步：检查网络。\n<script>alert(1)</script>"

        body, body_plaintext = build_plaintext_body(body_text)

        self.assertEqual(body, {"format": "opsai.plaintext/1", "text": body_text})
        self.assertEqual(body_plaintext, body_text)

    def test_rejects_non_string_and_blank_body(self):
        for value in (None, {"text": "正文"}, "", "  \r\n  "):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_plaintext_body(value)


class ArticleCreationServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0)

        cls.editor = User.objects.create_user(username="task12c-editor")
        cls.editor.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name))
        cls.admin = User.objects.create_user(username="task12c-admin")
        cls.admin.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name))
        cls.employee = User.objects.create_user(username="task12c-employee")
        cls.other_owner = User.objects.create_user(username="task12c-other-owner")

        cls.space = KnowledgeSpace.objects.create(
            code="task12c-space",
            name="Task 12C 空间",
            space_type="employee",
            owner=cls.editor,
            default_audience_policy=AudiencePolicy.RESTRICTED,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="task12c-category",
            name="Task 12C 分类",
        )
        cls.admin_space = KnowledgeSpace.objects.create(
            code="task12c-admin-space",
            name="Task 12C 管理员空间",
            space_type="it_internal",
            owner=cls.other_owner,
        )
        cls.admin_category = Category.objects.create(
            space=cls.admin_space,
            code="task12c-admin-category",
            name="Task 12C 管理员分类",
        )

    def create_kwargs(self, **overrides):
        values = {
            "actor": self.editor,
            "space": self.space,
            "category": self.category,
            "article_type": ArticleType.GUIDE,
            "title": "VPN 无法连接处理",
            "summary": "检查网络与客户端配置。",
            "applicable_scope": {"systems": ["Windows 11"]},
            "body_text": "第一步：检查网络。\n第二步：重新连接。",
            "change_summary": "创建初始草稿",
            "review_due_at": timezone.now() + timedelta(days=180),
        }
        values.update(overrides)
        return values

    def assert_error(self, code, **overrides):
        with self.assertRaises(ArticleCreationError) as caught:
            create_article(**self.create_kwargs(**overrides))
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_creates_article_and_initial_draft_as_one_complete_result(self):
        article, draft = create_article(**self.create_kwargs())

        article.refresh_from_db()
        draft.refresh_from_db()
        counter = KnowledgeNumberCounter.objects.get(pk=1)

        self.assertEqual(article.kb_no, "KB-000001")
        self.assertEqual(counter.next_value, 2)
        self.assertEqual(article.article_status, ArticleStatus.ACTIVE)
        self.assertEqual(article.created_by, self.editor)
        self.assertEqual(article.updated_by, self.editor)
        self.assertEqual(article.owner, self.editor)
        self.assertEqual(article.audience_policy, self.space.default_audience_policy)
        self.assertIsNone(article.current_published_version)
        self.assertEqual(article.latest_working_version, draft)
        self.assertEqual(draft.article, article)
        self.assertEqual(draft.version_no, 1)
        self.assertEqual(draft.status, VersionStatus.DRAFT)
        self.assertEqual(draft.lock_version, 1)
        self.assertIsNone(draft.restored_from_version)
        self.assertIsNone(draft.submitted_by)
        self.assertIsNone(draft.submitted_at)
        self.assertIsNone(draft.published_at)
        self.assertEqual(
            draft.body,
            {
                "format": "opsai.plaintext/1",
                "text": "第一步：检查网络。\n第二步：重新连接。",
            },
        )
        self.assertEqual(draft.body_plaintext, draft.body["text"])
        self.assertEqual(ReviewRecord.objects.count(), 0)
        self.assertFalse(ArticleVersion.objects.filter(status=VersionStatus.SAVED).exists())

    def test_caller_cannot_supply_authoritative_or_derived_body_fields(self):
        for forbidden in ("body", "body_plaintext"):
            with self.subTest(forbidden=forbidden), self.assertRaises(TypeError):
                create_article(**self.create_kwargs(**{forbidden: "绕过内容"}))
        self.assertEqual(Article.objects.count(), 0)
        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, 1)

    def test_missing_counter_fails_closed(self):
        KnowledgeNumberCounter.objects.filter(pk=1).delete()

        self.assert_error("KNOWLEDGE_NUMBER_COUNTER_MISSING")

        self.assertEqual(Article.objects.count(), 0)
        self.assertEqual(ArticleVersion.objects.count(), 0)

    def test_exhausted_counter_fails_closed(self):
        KnowledgeNumberCounter.objects.filter(pk=1).update(next_value=1_000_000)

        self.assert_error("KB_NUMBER_EXHAUSTED")

        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, 1_000_000)
        self.assertEqual(Article.objects.count(), 0)

    def test_last_six_digit_number_is_allocated_then_counter_marks_exhaustion(self):
        KnowledgeNumberCounter.objects.filter(pk=1).update(next_value=999_999)

        article, _draft = create_article(**self.create_kwargs())

        self.assertEqual(article.kb_no, "KB-999999")
        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, 1_000_000)

    def test_counter_drift_fails_without_searching_for_next_number(self):
        Article.objects.create(
            kb_no="KB-000001",
            title="既有文章",
            space=self.space,
            category=self.category,
            article_type=ArticleType.GUIDE,
            owner=self.editor,
            created_by=self.editor,
            updated_by=self.editor,
            review_due_at=timezone.now() + timedelta(days=30),
        )

        self.assert_error("COUNTER_OUT_OF_SYNC")

        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, 1)
        self.assertFalse(Article.objects.filter(kb_no="KB-000002").exists())

    def test_category_must_belong_to_space(self):
        self.assert_error(
            "SPACE_CATEGORY_MISMATCH",
            category=self.admin_category,
        )

    def test_space_and_category_must_be_active(self):
        self.space.is_active = False
        self.space.save(update_fields=["is_active"])
        self.assert_error("ARTICLE_CREATE_INVALID_INPUT")

        self.space.is_active = True
        self.space.save(update_fields=["is_active"])
        self.category.is_active = False
        self.category.save(update_fields=["is_active"])
        self.assert_error("ARTICLE_CREATE_INVALID_INPUT")

    def test_actor_must_be_authenticated_saved_and_active(self):
        self.assert_error("ARTICLE_CREATE_PERMISSION_DENIED", actor=AnonymousUser())
        self.assert_error(
            "ARTICLE_CREATE_PERMISSION_DENIED",
            actor=User(username="unsaved-task12c"),
        )

        inactive = User.objects.create_user(username="inactive-task12c", is_active=False)
        inactive.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name))
        self.assert_error("ARTICLE_CREATE_PERMISSION_DENIED", actor=inactive)

        disabled = User.objects.create_user(
            username="disabled-task12c",
            account_status=AccountStatus.DISABLED,
        )
        disabled.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name))
        self.assert_error("ARTICLE_CREATE_PERMISSION_DENIED", actor=disabled)

    def test_role_model_permissions_staff_and_superuser_are_all_checked(self):
        self.assert_error("ARTICLE_CREATE_PERMISSION_DENIED", actor=self.employee)

        staff = User.objects.create_user(username="staff-only-task12c", is_staff=True)
        self.assert_error("ARTICLE_CREATE_PERMISSION_DENIED", actor=staff)

        superuser = User.objects.create_superuser(
            username="superuser-only-task12c",
            email="",
            password="not-used-in-service-test",
        )
        self.assert_error("ARTICLE_CREATE_PERMISSION_DENIED", actor=superuser)

        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        editor_group.permissions.remove(editor_group.permissions.get(codename="add_articleversion"))
        editor_without_permission = User.objects.create_user(
            username="editor-without-permission-task12c"
        )
        editor_without_permission.groups.add(editor_group)
        self.assert_error(
            "ARTICLE_CREATE_PERMISSION_DENIED",
            actor=editor_without_permission,
        )

    def test_editor_is_limited_to_owned_space_and_owner_is_forced_to_actor(self):
        self.assert_error(
            "ARTICLE_CREATE_PERMISSION_DENIED",
            space=self.admin_space,
            category=self.admin_category,
        )

        article, _draft = create_article(**self.create_kwargs(owner=self.other_owner))
        self.assertEqual(article.owner, self.editor)

    def test_administrator_can_create_in_active_space_for_active_owner(self):
        article, draft = create_article(
            **self.create_kwargs(
                actor=self.admin,
                space=self.admin_space,
                category=self.admin_category,
                owner=self.other_owner,
                audience_policy=AudiencePolicy.IT_ONLY,
            )
        )

        self.assertEqual(article.owner, self.other_owner)
        self.assertEqual(article.audience_policy, AudiencePolicy.IT_ONLY)
        self.assertEqual(draft.created_by, self.admin)

    def test_administrator_defaults_owner_to_actor_and_rejects_inactive_owner(self):
        article, _draft = create_article(
            **self.create_kwargs(
                actor=self.admin,
                space=self.admin_space,
                category=self.admin_category,
            )
        )
        self.assertEqual(article.owner, self.admin)

        inactive_owner = User.objects.create_user(
            username="inactive-owner-task12c",
            is_active=False,
        )
        self.assert_error(
            "ARTICLE_CREATE_INVALID_INPUT",
            actor=self.admin,
            space=self.admin_space,
            category=self.admin_category,
            owner=inactive_owner,
        )

    def test_obviously_invalid_input_is_rejected_before_counter_changes(self):
        invalid_cases = (
            {"article_type": "unknown"},
            {"audience_policy": "unknown"},
            {"title": "x" * 61},
            {"summary": "x" * 501},
            {"change_summary": "x" * 501},
            {"applicable_scope": []},
            {"body_text": None},
            {"body_text": "   "},
            {"review_due_at": None},
        )
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                self.assert_error("ARTICLE_CREATE_INVALID_INPUT", **overrides)
        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, 1)
        self.assertEqual(Article.objects.count(), 0)

    def test_draft_save_failure_rolls_back_article_draft_and_counter(self):
        KnowledgeNumberCounter.objects.filter(pk=1).update(next_value=100)

        with mock.patch.object(
            ArticleVersion,
            "save",
            side_effect=DatabaseError("secret SQL connection detail"),
        ):
            error = self.assert_error("DATABASE_WRITE_FAILED")

        self.assertEqual(Article.objects.count(), 0)
        self.assertEqual(ArticleVersion.objects.count(), 0)
        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, 100)
        public_error = str(error).lower()
        for secret in ("secret", "sql", "connection", "sqlite", "constraint"):
            self.assertNotIn(secret, public_error)

    def test_prevalidation_database_failure_is_also_safely_wrapped(self):
        with mock.patch.object(
            User.objects,
            "get",
            side_effect=DatabaseError("secret SQL connection detail"),
        ):
            error = self.assert_error("DATABASE_WRITE_FAILED")

        public_error = str(error).lower()
        for secret in ("secret", "sql", "connection", "sqlite", "constraint"):
            self.assertNotIn(secret, public_error)
        self.assertEqual(Article.objects.count(), 0)
        self.assertEqual(KnowledgeNumberCounter.objects.get(pk=1).next_value, 1)

    def test_new_draft_is_invisible_to_employee_readers_and_search(self):
        article, _draft = create_article(
            **self.create_kwargs(audience_policy=AudiencePolicy.ALL_EMPLOYEES)
        )

        self.assertNotIn(article, employee_visible_articles(self.employee))
        self.assertIsNone(get_employee_article_detail(self.employee, article.kb_no))
        self.assertNotIn(
            article,
            search_employee_articles(self.employee, "VPN 无法连接处理"),
        )
