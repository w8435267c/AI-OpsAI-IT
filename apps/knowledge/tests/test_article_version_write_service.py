"""Task 12D-02：ArticleVersion 当前草稿 autosave CAS Service。"""

from datetime import timedelta
from unittest import mock
from uuid import uuid4

from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError
from django.db.models.query import QuerySet
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import AccountStatus, User
from apps.accounts.roles import ROLE_EDITOR, ROLE_KNOWLEDGE_ADMIN, SYSTEM_ROLE_BY_CODE
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
from apps.knowledge.readers import employee_visible_articles, get_employee_article_detail
from apps.knowledge.services import (
    ArticleCreationError,
    ArticleVersionWriteError,
    KnowledgeServiceError,
    autosave_draft,
    manual_save_draft,
)
from apps.search.readers import search_employee_articles


class ArticleVersionWriteServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0)
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)

        cls.article_owner = User.objects.create_user(username="task12d-article-owner")
        cls.article_owner.groups.add(editor_group)
        cls.space_owner = User.objects.create_user(username="task12d-space-owner")
        cls.space_owner.groups.add(editor_group)
        cls.other_editor = User.objects.create_user(username="task12d-other-editor")
        cls.other_editor.groups.add(editor_group)
        cls.admin = User.objects.create_user(username="task12d-admin")
        cls.admin.groups.add(admin_group)
        cls.employee = User.objects.create_user(username="task12d-employee")

        cls.space = KnowledgeSpace.objects.create(
            code="task12d-space",
            name="Task 12D 空间",
            space_type="employee",
            owner=cls.space_owner,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="task12d-category",
            name="Task 12D 分类",
        )
        cls.article = Article.objects.create(
            kb_no="KB-120002",
            title="发布标题保持不变",
            space=cls.space,
            category=cls.category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            owner=cls.article_owner,
            created_by=cls.article_owner,
            updated_by=cls.space_owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )
        cls.draft = ArticleVersion.objects.create(
            article=cls.article,
            version_no=1,
            status=VersionStatus.DRAFT,
            lock_version=1,
            title="旧草稿标题",
            summary="旧摘要",
            applicable_scope={"systems": ["Windows 10"]},
            body={"format": "opsai.plaintext/1", "text": "旧正文"},
            body_plaintext="旧正文",
            change_summary="旧版本说明",
            created_by=cls.article_owner,
        )
        Article.objects.filter(pk=cls.article.pk).update(latest_working_version=cls.draft)

    def autosave_kwargs(self, **overrides):
        values = {
            "actor": self.article_owner,
            "article": self.article,
            "draft_id": self.draft.pk,
            "expected_lock_version": 1,
            "title": "新草稿标题",
            "summary": "新摘要",
            "applicable_scope": {"systems": ["Windows 11"], "devices": ["PC"]},
            "body_text": "第一步：检查网络。",
            "change_summary": "更新排障步骤",
        }
        values.update(overrides)
        return values

    def assert_write_error(self, code, **overrides):
        with self.assertRaises(ArticleVersionWriteError) as caught:
            autosave_draft(**self.autosave_kwargs(**overrides))
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def manual_save_kwargs(self, **overrides):
        values = self.autosave_kwargs()
        values.update(overrides)
        return values

    def assert_manual_error(self, code, **overrides):
        with self.assertRaises(ArticleVersionWriteError) as caught:
            manual_save_draft(**self.manual_save_kwargs(**overrides))
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def make_article_version(self, *, status=VersionStatus.DRAFT, current=True, suffix=None):
        suffix = suffix or f"{Article.objects.count() + 1:06d}"
        article = Article.objects.create(
            kb_no=f"KB-{suffix}",
            title=f"状态测试 {status}",
            space=self.space,
            category=self.category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.RESTRICTED,
            owner=self.article_owner,
            created_by=self.article_owner,
            updated_by=self.article_owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )
        submitted_fields = {}
        if status not in (VersionStatus.DRAFT, VersionStatus.SAVED):
            submitted_fields = {
                "submitted_by": self.article_owner,
                "submitted_at": timezone.now(),
            }
        if status == VersionStatus.PUBLISHED:
            submitted_fields["published_at"] = timezone.now()
        version = ArticleVersion.objects.create(
            article=article,
            version_no=1,
            status=status,
            title="受保护版本",
            summary="受保护摘要",
            change_summary="受保护说明",
            created_by=self.article_owner,
            **submitted_fields,
        )
        if current:
            Article.objects.filter(pk=article.pk).update(latest_working_version=version)
        article.refresh_from_db()
        return article, version

    def test_common_error_contract_keeps_article_creation_compatibility(self):
        self.assertTrue(issubclass(ArticleCreationError, KnowledgeServiceError))
        self.assertTrue(issubclass(ArticleVersionWriteError, KnowledgeServiceError))

        error = ArticleCreationError("EXISTING_CODE", "原有公开消息")

        self.assertEqual(error.code, "EXISTING_CODE")
        self.assertEqual(error.public_message, "原有公开消息")
        self.assertEqual(str(error), "原有公开消息")

    def test_autosave_updates_current_draft_in_place_and_returns_new_token(self):
        before_count = ArticleVersion.objects.count()
        old_updated_at = timezone.now() - timedelta(days=1)
        ArticleVersion.objects.filter(pk=self.draft.pk).update(updated_at=old_updated_at)

        result = autosave_draft(**self.autosave_kwargs())

        self.assertIsInstance(result, ArticleVersion)
        self.assertEqual(result.pk, self.draft.pk)
        self.assertEqual(ArticleVersion.objects.count(), before_count)
        self.assertEqual(result.version_no, 1)
        self.assertEqual(result.status, VersionStatus.DRAFT)
        self.assertEqual(result.lock_version, 2)
        self.assertEqual(result.title, "新草稿标题")
        self.assertEqual(result.summary, "新摘要")
        self.assertEqual(
            result.applicable_scope,
            {"systems": ["Windows 11"], "devices": ["PC"]},
        )
        self.assertEqual(
            result.body,
            {"format": "opsai.plaintext/1", "text": "第一步：检查网络。"},
        )
        self.assertEqual(result.body_plaintext, "第一步：检查网络。")
        self.assertEqual(result.change_summary, "更新排障步骤")
        self.assertGreater(result.updated_at, old_updated_at)

    def test_new_token_succeeds_and_old_token_conflict_preserves_first_result(self):
        first = autosave_draft(**self.autosave_kwargs())
        second = autosave_draft(
            **self.autosave_kwargs(
                expected_lock_version=first.lock_version,
                title="第二次标题",
                body_text="第二次正文",
            )
        )
        self.assertEqual(second.lock_version, 3)
        self.assertEqual(second.title, "第二次标题")

        error = self.assert_write_error(
            "DRAFT_CONFLICT",
            expected_lock_version=1,
            title="过期写入标题",
            body_text="过期写入正文",
        )

        second.refresh_from_db()
        self.assertEqual(second.lock_version, 3)
        self.assertEqual(second.title, "第二次标题")
        self.assertEqual(second.body_plaintext, "第二次正文")
        self.assertNotIn("sql", error.public_message.lower())

    def test_autosave_does_not_modify_article_or_either_pointer(self):
        published = ArticleVersion.objects.create(
            article=self.article,
            version_no=2,
            status=VersionStatus.PUBLISHED,
            title="正式标题",
            summary="正式摘要",
            body_plaintext="正式正文",
            change_summary="正式版本",
            created_by=self.article_owner,
            submitted_by=self.article_owner,
            submitted_at=timezone.now(),
            published_at=timezone.now(),
        )
        Article.objects.filter(pk=self.article.pk).update(current_published_version=published)
        self.article.refresh_from_db()
        before = {
            "title": self.article.title,
            "updated_by_id": self.article.updated_by_id,
            "updated_at": self.article.updated_at,
            "latest_working_version_id": self.article.latest_working_version_id,
            "current_published_version_id": self.article.current_published_version_id,
        }

        autosave_draft(**self.autosave_kwargs())

        self.article.refresh_from_db()
        self.assertEqual(
            {
                "title": self.article.title,
                "updated_by_id": self.article.updated_by_id,
                "updated_at": self.article.updated_at,
                "latest_working_version_id": self.article.latest_working_version_id,
                "current_published_version_id": self.article.current_published_version_id,
            },
            before,
        )

    def test_autosave_uses_cas_update_without_pessimistic_lock(self):
        original_update = QuerySet.update
        version_update_calls = []

        def recording_update(queryset, **kwargs):
            if queryset.model is ArticleVersion:
                version_update_calls.append(kwargs)
            return original_update(queryset, **kwargs)

        with (
            mock.patch.object(QuerySet, "select_for_update", side_effect=AssertionError),
            mock.patch.object(QuerySet, "update", autospec=True, side_effect=recording_update),
        ):
            result = autosave_draft(**self.autosave_kwargs())

        self.assertEqual(result.lock_version, 2)
        self.assertEqual(len(version_update_calls), 1)
        self.assertIn("lock_version", version_update_calls[0])
        self.assertIn("updated_at", version_update_calls[0])

    def test_all_non_draft_states_are_immutable(self):
        statuses = (
            VersionStatus.SAVED,
            VersionStatus.IN_REVIEW,
            VersionStatus.REJECTED,
            VersionStatus.PUBLISHED,
            VersionStatus.SUPERSEDED,
        )
        for index, status in enumerate(statuses, start=200100):
            with self.subTest(status=status):
                article, version = self.make_article_version(
                    status=status,
                    suffix=f"{index:06d}",
                )
                self.assert_write_error(
                    "INVALID_DRAFT_STATE",
                    article=article,
                    draft_id=version.pk,
                )
                version.refresh_from_db()
                self.assertEqual(version.title, "受保护版本")
                self.assertEqual(version.lock_version, 1)

    def test_non_current_draft_is_rejected(self):
        Article.objects.filter(pk=self.article.pk).update(latest_working_version=None)

        self.assert_write_error("DRAFT_NOT_CURRENT")

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.title, "旧草稿标题")
        self.assertEqual(self.draft.lock_version, 1)

    def test_wrong_article_and_missing_draft_do_not_leak_existence(self):
        other_article, other_draft = self.make_article_version(suffix="200200")

        wrong_article = self.assert_write_error(
            "DRAFT_NOT_FOUND_OR_INACCESSIBLE",
            draft_id=other_draft.pk,
        )
        missing = self.assert_write_error(
            "DRAFT_NOT_FOUND_OR_INACCESSIBLE",
            draft_id=uuid4(),
        )

        self.assertNotEqual(other_article.pk, self.article.pk)
        self.assertEqual(wrong_article.public_message, missing.public_message)

    def test_editor_owner_space_owner_and_admin_are_authorized(self):
        first = autosave_draft(**self.autosave_kwargs(actor=self.article_owner))
        second = autosave_draft(
            **self.autosave_kwargs(
                actor=self.space_owner,
                expected_lock_version=first.lock_version,
            )
        )
        third = autosave_draft(
            **self.autosave_kwargs(
                actor=self.admin,
                expected_lock_version=second.lock_version,
            )
        )

        self.assertEqual((first.lock_version, second.lock_version, third.lock_version), (2, 3, 4))

    def test_editor_without_object_permission_is_rejected(self):
        self.assert_write_error(
            "DRAFT_NOT_FOUND_OR_INACCESSIBLE",
            actor=self.other_editor,
        )
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.lock_version, 1)

    def test_employee_staff_and_superuser_cannot_bypass_writer_role(self):
        staff = User.objects.create_user(username="task12d-staff-only", is_staff=True)
        superuser = User.objects.create_superuser(
            username="task12d-superuser-only",
            email="",
            password="not-used-in-service-test",
        )

        for actor in (self.employee, staff, superuser):
            with self.subTest(actor=actor.username):
                self.assert_write_error("ARTICLE_VERSION_WRITE_PERMISSION_DENIED", actor=actor)

    def test_saved_authenticated_active_business_account_is_required(self):
        inactive = User.objects.create_user(username="task12d-inactive", is_active=False)
        inactive.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name))
        disabled = User.objects.create_user(
            username="task12d-disabled",
            account_status=AccountStatus.DISABLED,
        )
        disabled.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name))

        for actor in (
            AnonymousUser(),
            User(username="task12d-unsaved"),
            inactive,
            disabled,
        ):
            with self.subTest(actor=actor):
                self.assert_write_error("ARTICLE_VERSION_WRITE_PERMISSION_DENIED", actor=actor)

    def test_missing_required_model_permission_is_rejected(self):
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        permission = Permission.objects.get(
            content_type__app_label="knowledge",
            codename="change_articleversion",
        )
        editor_group.permissions.remove(permission)
        actor = User.objects.create_user(username="task12d-missing-model-permission")
        actor.groups.add(editor_group)

        self.assert_write_error("ARTICLE_VERSION_WRITE_PERMISSION_DENIED", actor=actor)

    def test_article_must_be_saved_and_belong_to_active_space(self):
        unsaved_article = Article()
        self.assert_write_error(
            "DRAFT_NOT_FOUND_OR_INACCESSIBLE",
            article=unsaved_article,
        )

        KnowledgeSpace.objects.filter(pk=self.space.pk).update(is_active=False)
        self.assert_write_error("ARTICLE_VERSION_WRITE_INVALID_INPUT")

    def test_invalid_content_and_lock_token_are_rejected_before_write(self):
        invalid_cases = (
            {"expected_lock_version": None},
            {"expected_lock_version": 0},
            {"expected_lock_version": -1},
            {"expected_lock_version": True},
            {"expected_lock_version": "1"},
            {"title": None},
            {"title": ""},
            {"title": "x" * 61},
            {"summary": None},
            {"summary": "x" * 501},
            {"applicable_scope": []},
            {"applicable_scope": {"invalid": {1, 2}}},
            {"body_text": None},
            {"body_text": "   \r\n"},
            {"change_summary": None},
            {"change_summary": "x" * 501},
        )
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                self.assert_write_error("ARTICLE_VERSION_WRITE_INVALID_INPUT", **overrides)

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.lock_version, 1)
        self.assertEqual(self.draft.title, "旧草稿标题")

    def test_caller_cannot_supply_protected_version_fields(self):
        forbidden_values = {
            "body": {},
            "body_plaintext": "绕过正文",
            "status": VersionStatus.SAVED,
            "version_no": 99,
            "lock_version": 99,
            "created_by": self.admin,
            "submitted_by": self.admin,
            "submitted_at": timezone.now(),
            "published_at": timezone.now(),
            "restored_from_version": self.draft,
        }
        for field, value in forbidden_values.items():
            with self.subTest(field=field), self.assertRaises(TypeError):
                autosave_draft(**self.autosave_kwargs(**{field: value}))

    def test_html_shaped_body_is_stored_as_plain_text(self):
        body_text = "<script>alert(1)</script>"

        result = autosave_draft(**self.autosave_kwargs(body_text=body_text))

        self.assertEqual(
            result.body,
            {"format": "opsai.plaintext/1", "text": body_text},
        )
        self.assertEqual(result.body_plaintext, body_text)

    def test_database_failure_uses_safe_public_error(self):
        with mock.patch.object(
            QuerySet,
            "update",
            side_effect=DatabaseError("secret SQL sqlite constraint detail"),
        ):
            error = self.assert_write_error("DATABASE_WRITE_FAILED")

        public_error = error.public_message.lower()
        for secret in ("secret", "sql", "sqlite", "constraint"):
            self.assertNotIn(secret, public_error)

    def test_autosaved_draft_remains_invisible_to_employee_readers_and_search(self):
        published = ArticleVersion.objects.create(
            article=self.article,
            version_no=2,
            status=VersionStatus.PUBLISHED,
            title="员工可见正式标题",
            summary="员工可见正式摘要",
            body_plaintext="员工可见正式正文",
            change_summary="正式版本",
            created_by=self.article_owner,
            submitted_by=self.article_owner,
            submitted_at=timezone.now(),
            published_at=timezone.now(),
        )
        Article.objects.filter(pk=self.article.pk).update(current_published_version=published)
        draft_only_marker = "task12d-autosave-draft-only-marker"

        autosave_draft(
            **self.autosave_kwargs(
                title=draft_only_marker,
                summary=draft_only_marker,
                body_text=draft_only_marker,
            )
        )

        visible = employee_visible_articles(self.employee)
        detail = get_employee_article_detail(self.employee, self.article.kb_no)
        self.assertIn(self.article, visible)
        self.assertEqual(detail.title, "员工可见正式标题")
        self.assertNotIn(
            self.article,
            search_employee_articles(self.employee, draft_only_marker),
        )
        self.assertIn(
            self.article,
            search_employee_articles(self.employee, "员工可见正式标题"),
        )

    def test_manual_save_freezes_current_draft_and_creates_next_draft(self):
        published = ArticleVersion.objects.create(
            article=self.article,
            version_no=5,
            status=VersionStatus.PUBLISHED,
            title="员工正式标题",
            summary="员工正式摘要",
            body={"format": "opsai.plaintext/1", "text": "员工正式正文"},
            body_plaintext="员工正式正文",
            change_summary="正式发布",
            created_by=self.article_owner,
            submitted_by=self.article_owner,
            submitted_at=timezone.now(),
            published_at=timezone.now(),
        )
        Article.objects.filter(pk=self.article.pk).update(
            current_published_version=published,
            updated_by=self.article_owner,
            updated_at=timezone.now() - timedelta(days=1),
        )
        self.article.refresh_from_db()
        old_article_updated_at = self.article.updated_at
        old_draft_pk = self.draft.pk
        before_review_count = ReviewRecord.objects.count()

        saved, new_draft = manual_save_draft(**self.manual_save_kwargs(actor=self.space_owner))

        self.assertEqual(saved.pk, old_draft_pk)
        self.assertEqual(saved.status, VersionStatus.SAVED)
        self.assertEqual(saved.version_no, 1)
        self.assertEqual(saved.lock_version, 2)
        self.assertEqual(saved.title, "新草稿标题")
        self.assertEqual(saved.summary, "新摘要")
        self.assertEqual(
            saved.applicable_scope,
            {"systems": ["Windows 11"], "devices": ["PC"]},
        )
        self.assertEqual(
            saved.body,
            {"format": "opsai.plaintext/1", "text": "第一步：检查网络。"},
        )
        self.assertEqual(saved.body_plaintext, "第一步：检查网络。")
        self.assertEqual(saved.change_summary, "更新排障步骤")
        self.assertEqual(saved.created_by, self.article_owner)
        self.assertIsNone(saved.restored_from_version)
        self.assertIsNone(saved.submitted_by)
        self.assertIsNone(saved.submitted_at)
        self.assertIsNone(saved.published_at)

        self.assertNotEqual(new_draft.pk, saved.pk)
        self.assertEqual(new_draft.article, self.article)
        self.assertEqual(new_draft.version_no, 6)
        self.assertEqual(new_draft.status, VersionStatus.DRAFT)
        self.assertEqual(new_draft.lock_version, 1)
        for field in ("title", "summary", "applicable_scope", "body", "body_plaintext"):
            with self.subTest(field=field):
                self.assertEqual(getattr(new_draft, field), getattr(saved, field))
        self.assertEqual(new_draft.created_by, self.space_owner)
        self.assertIsNone(new_draft.restored_from_version)
        self.assertIsNone(new_draft.submitted_by)
        self.assertIsNone(new_draft.submitted_at)
        self.assertIsNone(new_draft.published_at)
        self.assertEqual(new_draft.change_summary, "基于已保存版本 v1 继续编辑")

        self.article.refresh_from_db()
        self.assertEqual(self.article.latest_working_version, new_draft)
        self.assertEqual(self.article.updated_by, self.space_owner)
        self.assertGreater(self.article.updated_at, old_article_updated_at)
        self.assertEqual(self.article.title, "发布标题保持不变")
        self.assertEqual(self.article.current_published_version, published)
        self.assertEqual(ReviewRecord.objects.count(), before_review_count)
        self.assertEqual(ArticleVersion.objects.filter(article=self.article).count(), 3)
        self.assertEqual(
            list(
                ArticleVersion.objects.filter(article=self.article)
                .order_by("version_no")
                .values_list("version_no", "status")
            ),
            [
                (1, VersionStatus.SAVED),
                (5, VersionStatus.PUBLISHED),
                (6, VersionStatus.DRAFT),
            ],
        )

        detail = get_employee_article_detail(self.employee, self.article.kb_no)
        self.assertEqual(detail.title, "员工正式标题")
        self.assertNotIn(
            self.article,
            search_employee_articles(self.employee, "新草稿标题"),
        )
        self.assertIn(
            self.article,
            search_employee_articles(self.employee, "员工正式标题"),
        )

    def test_manual_save_uses_max_version_number_not_current_draft_number(self):
        ArticleVersion.objects.create(
            article=self.article,
            version_no=9,
            status=VersionStatus.SAVED,
            title="高位历史版本",
            summary="高位历史摘要",
            change_summary="高位历史",
            created_by=self.article_owner,
        )

        saved, new_draft = manual_save_draft(**self.manual_save_kwargs())

        self.assertEqual(saved.version_no, 1)
        self.assertEqual(new_draft.version_no, 10)

    def test_manual_save_stale_token_rolls_back_everything(self):
        self.article.refresh_from_db()
        before_article = {
            "latest_working_version_id": self.article.latest_working_version_id,
            "current_published_version_id": self.article.current_published_version_id,
            "updated_by_id": self.article.updated_by_id,
            "updated_at": self.article.updated_at,
        }
        before_version_count = ArticleVersion.objects.count()

        self.assert_manual_error("DRAFT_CONFLICT", expected_lock_version=2)

        self.draft.refresh_from_db()
        self.article.refresh_from_db()
        self.assertEqual(self.draft.status, VersionStatus.DRAFT)
        self.assertEqual(self.draft.lock_version, 1)
        self.assertEqual(self.draft.title, "旧草稿标题")
        self.assertEqual(ArticleVersion.objects.count(), before_version_count)
        self.assertEqual(
            {
                "latest_working_version_id": self.article.latest_working_version_id,
                "current_published_version_id": self.article.current_published_version_id,
                "updated_by_id": self.article.updated_by_id,
                "updated_at": self.article.updated_at,
            },
            before_article,
        )

    def test_manual_save_rejects_non_current_non_draft_wrong_and_missing_draft(self):
        Article.objects.filter(pk=self.article.pk).update(latest_working_version=None)
        self.assert_manual_error("DRAFT_NOT_CURRENT")

        Article.objects.filter(pk=self.article.pk).update(latest_working_version=self.draft)
        ArticleVersion.objects.filter(pk=self.draft.pk).update(status=VersionStatus.SAVED)
        self.assert_manual_error("INVALID_DRAFT_STATE")

        other_article, other_draft = self.make_article_version(suffix="200300")
        wrong = self.assert_manual_error(
            "DRAFT_NOT_FOUND_OR_INACCESSIBLE",
            draft_id=other_draft.pk,
        )
        missing = self.assert_manual_error(
            "DRAFT_NOT_FOUND_OR_INACCESSIBLE",
            draft_id=uuid4(),
        )
        self.assertNotEqual(other_article.pk, self.article.pk)
        self.assertEqual(wrong.public_message, missing.public_message)

    def test_manual_save_rejects_repeated_use_of_frozen_draft(self):
        saved, _new_draft = manual_save_draft(**self.manual_save_kwargs())

        self.assert_manual_error(
            "DRAFT_NOT_CURRENT",
            draft_id=saved.pk,
            expected_lock_version=saved.lock_version,
        )

        saved.refresh_from_db()
        self.assertEqual(saved.status, VersionStatus.SAVED)
        self.assertEqual(saved.title, "新草稿标题")

    def test_manual_save_authorizes_owner_space_owner_and_admin(self):
        cases = (
            (self.article_owner, "200401"),
            (self.space_owner, "200402"),
            (self.admin, "200403"),
        )
        for actor, suffix in cases:
            with self.subTest(actor=actor.username):
                article, draft = self.make_article_version(suffix=suffix)
                saved, new_draft = manual_save_draft(
                    **self.manual_save_kwargs(
                        actor=actor,
                        article=article,
                        draft_id=draft.pk,
                    )
                )
                self.assertEqual(saved.status, VersionStatus.SAVED)
                self.assertEqual(new_draft.created_by, actor)

    def test_manual_save_rejects_unauthorized_and_invalid_accounts(self):
        staff = User.objects.create_user(username="task12d-manual-staff", is_staff=True)
        superuser = User.objects.create_superuser(
            username="task12d-manual-superuser",
            email="",
            password="not-used-in-service-test",
        )
        inactive = User.objects.create_user(username="task12d-manual-inactive", is_active=False)
        inactive.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name))
        disabled = User.objects.create_user(
            username="task12d-manual-disabled",
            account_status=AccountStatus.DISABLED,
        )
        disabled.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name))

        cases = (
            (self.other_editor, "DRAFT_NOT_FOUND_OR_INACCESSIBLE"),
            (self.employee, "ARTICLE_VERSION_WRITE_PERMISSION_DENIED"),
            (staff, "ARTICLE_VERSION_WRITE_PERMISSION_DENIED"),
            (superuser, "ARTICLE_VERSION_WRITE_PERMISSION_DENIED"),
            (inactive, "ARTICLE_VERSION_WRITE_PERMISSION_DENIED"),
            (disabled, "ARTICLE_VERSION_WRITE_PERMISSION_DENIED"),
        )
        for actor, code in cases:
            with self.subTest(actor=actor.username):
                self.assert_manual_error(code, actor=actor)

    def test_manual_save_requires_add_articleversion_permission(self):
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        editor_group.permissions.remove(
            Permission.objects.get(
                content_type__app_label="knowledge",
                codename="add_articleversion",
            )
        )
        actor = User.objects.create_user(username="task12d-manual-missing-add")
        actor.groups.add(editor_group)

        self.assert_manual_error("ARTICLE_VERSION_WRITE_PERMISSION_DENIED", actor=actor)

    def test_manual_save_validates_complete_content_and_token_before_transaction(self):
        invalid_cases = (
            {"expected_lock_version": None},
            {"expected_lock_version": 0},
            {"expected_lock_version": -1},
            {"expected_lock_version": True},
            {"expected_lock_version": "1"},
            {"title": None},
            {"title": "x" * 61},
            {"summary": None},
            {"summary": "x" * 501},
            {"applicable_scope": []},
            {"applicable_scope": {"invalid": {1}}},
            {"body_text": None},
            {"body_text": "  \r\n"},
            {"change_summary": None},
            {"change_summary": "x" * 501},
        )
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                self.assert_manual_error("ARTICLE_VERSION_WRITE_INVALID_INPUT", **overrides)

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, VersionStatus.DRAFT)
        self.assertEqual(self.draft.lock_version, 1)
        self.assertEqual(ArticleVersion.objects.filter(article=self.article).count(), 1)

    def test_manual_save_version_number_conflict_fails_closed_without_retry(self):
        original_save = ArticleVersion.save
        new_draft_save_attempts = []

        def fail_new_draft(instance, *args, **kwargs):
            if instance.pk != self.draft.pk and instance.status == VersionStatus.DRAFT:
                new_draft_save_attempts.append(instance.version_no)
                raise IntegrityError("secret kb_ver_article_no_uniq SQL constraint")
            return original_save(instance, *args, **kwargs)

        with mock.patch.object(ArticleVersion, "save", autospec=True, side_effect=fail_new_draft):
            error = self.assert_manual_error("VERSION_NUMBER_CONFLICT")

        self.assertEqual(new_draft_save_attempts, [2])
        self.assertNotIn("sql", error.public_message.lower())
        self.assertNotIn("constraint", error.public_message.lower())
        self.draft.refresh_from_db()
        self.article.refresh_from_db()
        self.assertEqual(self.draft.status, VersionStatus.DRAFT)
        self.assertEqual(self.draft.lock_version, 1)
        self.assertEqual(self.article.latest_working_version, self.draft)
        self.assertEqual(ArticleVersion.objects.filter(article=self.article).count(), 1)

    def test_manual_save_new_draft_failure_rolls_back_all_changes(self):
        original_save = ArticleVersion.save

        def fail_new_draft(instance, *args, **kwargs):
            if instance.pk != self.draft.pk and instance.status == VersionStatus.DRAFT:
                raise DatabaseError("secret connection failure after SAVED")
            return original_save(instance, *args, **kwargs)

        with mock.patch.object(ArticleVersion, "save", autospec=True, side_effect=fail_new_draft):
            error = self.assert_manual_error("DATABASE_WRITE_FAILED")

        self.assertNotIn("connection", error.public_message.lower())
        self.draft.refresh_from_db()
        self.article.refresh_from_db()
        self.assertEqual(self.draft.status, VersionStatus.DRAFT)
        self.assertEqual(self.draft.lock_version, 1)
        self.assertEqual(self.draft.title, "旧草稿标题")
        self.assertEqual(self.article.latest_working_version, self.draft)
        self.assertEqual(self.article.updated_by, self.space_owner)
        self.assertEqual(ArticleVersion.objects.filter(article=self.article).count(), 1)

    def test_manual_save_article_pointer_failure_rolls_back_new_draft_and_saved(self):
        original_save = Article.save

        def fail_pointer_save(instance, *args, **kwargs):
            if kwargs.get("update_fields") and "latest_working_version" in kwargs["update_fields"]:
                raise DatabaseError("secret SQL pointer write failure")
            return original_save(instance, *args, **kwargs)

        with mock.patch.object(Article, "save", autospec=True, side_effect=fail_pointer_save):
            error = self.assert_manual_error("DATABASE_WRITE_FAILED")

        self.assertNotIn("sql", error.public_message.lower())
        self.draft.refresh_from_db()
        self.article.refresh_from_db()
        self.assertEqual(self.draft.status, VersionStatus.DRAFT)
        self.assertEqual(self.draft.lock_version, 1)
        self.assertEqual(self.draft.title, "旧草稿标题")
        self.assertEqual(self.article.latest_working_version, self.draft)
        self.assertEqual(self.article.updated_by, self.space_owner)
        self.assertEqual(ArticleVersion.objects.filter(article=self.article).count(), 1)
