"""Task 12E-05：管理编辑器 autosave HTTP 合同。"""

from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO
from unittest import mock

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
from apps.knowledge.services import (
    ARTICLE_VERSION_WRITE_INVALID_INPUT,
    ARTICLE_VERSION_WRITE_PERMISSION_DENIED,
    DATABASE_WRITE_FAILED,
    DRAFT_CONFLICT,
    DRAFT_NOT_CURRENT,
    INVALID_DRAFT_STATE,
    MODEL_CONSISTENCY_FAILED,
    ArticleVersionWriteError,
)


class ManageArticleAutosaveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0, stdout=StringIO())
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)
        reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)

        cls.owner = cls.make_user("autosave-owner", editor_group)
        cls.space_owner = cls.make_user("autosave-space-owner", editor_group)
        cls.other_editor = cls.make_user("autosave-other-editor", editor_group)
        cls.admin = cls.make_user("autosave-admin", admin_group)
        cls.employee = cls.make_user("autosave-employee")
        cls.reviewer = cls.make_user("autosave-reviewer", reviewer_group)

        cls.space = KnowledgeSpace.objects.create(
            code="autosave-space",
            name="自动保存空间",
            space_type="employee",
            owner=cls.space_owner,
            default_audience_policy=AudiencePolicy.RESTRICTED,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="autosave-category",
            name="自动保存分类",
        )
        cls.article = cls.make_article("KB-320001", owner=cls.owner)
        cls.published = ArticleVersion.objects.create(
            article=cls.article,
            version_no=1,
            status=VersionStatus.PUBLISHED,
            title="员工可见正式标题",
            summary="员工可见正式摘要",
            body_plaintext="员工可见正式正文",
            change_summary="正式版本",
            created_by=cls.owner,
            submitted_by=cls.owner,
            submitted_at=timezone.now(),
            published_at=timezone.now(),
        )
        cls.draft = ArticleVersion.objects.create(
            article=cls.article,
            version_no=2,
            status=VersionStatus.DRAFT,
            lock_version=7,
            title="初始草稿标题",
            summary="初始草稿摘要",
            applicable_scope={"system": "Windows"},
            body_plaintext="初始草稿正文",
            change_summary="初始版本说明",
            created_by=cls.owner,
        )
        Article.objects.filter(pk=cls.article.pk).update(
            latest_working_version=cls.draft,
            current_published_version=cls.published,
        )

        cls.other_space = KnowledgeSpace.objects.create(
            code="autosave-other-space",
            name="其他自动保存空间",
            space_type="employee",
            owner=cls.other_editor,
        )
        cls.other_category = Category.objects.create(
            space=cls.other_space,
            code="autosave-other-category",
            name="其他分类",
        )
        cls.other_article = cls.make_article(
            "KB-320002",
            owner=cls.other_editor,
            space=cls.other_space,
            category=cls.other_category,
        )
        cls.other_draft = ArticleVersion.objects.create(
            article=cls.other_article,
            version_no=1,
            status=VersionStatus.DRAFT,
            title="其他草稿",
            summary="其他摘要",
            body_plaintext="其他正文",
            change_summary="其他说明",
            created_by=cls.other_editor,
        )
        Article.objects.filter(pk=cls.other_article.pk).update(
            latest_working_version=cls.other_draft
        )

    @classmethod
    def make_user(cls, username, group=None, **kwargs):
        user = User.objects.create_user(username=username, **kwargs)
        if group is not None:
            user.groups.add(group)
        return user

    @classmethod
    def make_article(cls, kb_no, *, owner, space=None, category=None):
        return Article.objects.create(
            kb_no=kb_no,
            title=f"兼容标题 {kb_no}",
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

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse("knowledge_manage:autosave", args=[self.article.kb_no])

    def payload(self, **overrides):
        payload = {
            "draft_id": str(self.draft.pk),
            "expected_lock_version": 7,
            "title": "自动保存后的标题",
            "summary": "自动保存后的摘要",
            "applicable_scope": {"system": "Linux", "nested": {"value": 1}},
            "body_text": "自动保存后的正文",
            "change_summary": "自动保存后的版本说明",
        }
        payload.update(overrides)
        return payload

    def post_json(self, payload=None, *, client=None, url=None):
        return (client or self.client).post(
            url or self.url,
            data=json.dumps(self.payload() if payload is None else payload),
            content_type="application/json",
        )

    def assert_error(self, response, *, status, code):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], code)
        self.assertIsInstance(body["error"]["message"], str)

    def test_endpoint_is_post_only_with_allow_and_no_store(self):
        for method in ("get", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url)
                self.assert_error(
                    response,
                    status=405,
                    code="METHOD_NOT_ALLOWED",
                )
                self.assertEqual(response["Allow"], "POST")

    def test_json_boundary_rejects_wrong_content_empty_malformed_and_non_object(self):
        cases = (
            ("wrong-content-type", {}, None),
            ("empty", b"", "application/json"),
            ("malformed", b"{invalid", "application/json"),
            ("array", b"[]", "application/json"),
            ("string", b'"value"', "application/json"),
            ("number", b"1", "application/json"),
            ("null", b"null", "application/json"),
        )
        for label, data, content_type in cases:
            with self.subTest(label=label):
                kwargs = {"data": data}
                if content_type is not None:
                    kwargs["content_type"] = content_type
                response = self.client.post(self.url, **kwargs)
                self.assert_error(response, status=400, code="INVALID_JSON")

    def test_unknown_or_forbidden_top_level_fields_are_rejected(self):
        for field in ("version_no", "status", "lock_version", "owner", "extra"):
            with self.subTest(field=field):
                response = self.post_json(self.payload(**{field: "forbidden"}))
                self.assert_error(response, status=400, code="UNKNOWN_FIELDS")

    def test_identity_fields_are_required_and_strict(self):
        cases = (
            ({"draft_id": None}, "INVALID_REQUEST"),
            ({"draft_id": "not-a-uuid"}, "INVALID_REQUEST"),
            ({"expected_lock_version": None}, "INVALID_REQUEST"),
            ({"expected_lock_version": 0}, "INVALID_REQUEST"),
            ({"expected_lock_version": -1}, "INVALID_REQUEST"),
            ({"expected_lock_version": True}, "INVALID_REQUEST"),
            ({"expected_lock_version": 1.5}, "INVALID_REQUEST"),
            ({"expected_lock_version": "7"}, "INVALID_REQUEST"),
        )
        for overrides, code in cases:
            with self.subTest(overrides=overrides):
                payload = self.payload(**overrides)
                response = self.post_json(payload)
                self.assert_error(response, status=400, code=code)

        for missing in ("draft_id", "expected_lock_version"):
            with self.subTest(missing=missing):
                payload = self.payload()
                payload.pop(missing)
                response = self.post_json(payload)
                self.assert_error(response, status=400, code="INVALID_REQUEST")

    def test_content_validation_reuses_five_field_contract(self):
        cases = (
            {"title": "题" * 61},
            {"body_text": "   "},
            {"applicable_scope": []},
            {"applicable_scope": None},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                response = self.post_json(self.payload(**overrides))
                self.assert_error(response, status=400, code="INVALID_CONTENT")

    def test_success_updates_same_draft_and_preserves_article_history_and_pointers(self):
        article_before = Article.objects.get(pk=self.article.pk)
        version_count = ArticleVersion.objects.count()
        review_count = ReviewRecord.objects.count()

        response = self.post_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["draft"]["id"], str(self.draft.pk))
        self.assertEqual(body["draft"]["version_no"], 2)
        self.assertEqual(body["draft"]["lock_version"], 8)
        self.assertTrue(body["draft"]["updated_at"])

        draft = ArticleVersion.objects.get(pk=self.draft.pk)
        article = Article.objects.get(pk=self.article.pk)
        self.assertEqual(ArticleVersion.objects.count(), version_count)
        self.assertEqual(ReviewRecord.objects.count(), review_count)
        self.assertEqual(draft.status, VersionStatus.DRAFT)
        self.assertEqual(draft.lock_version, 8)
        self.assertEqual(draft.title, "自动保存后的标题")
        self.assertEqual(draft.summary, "自动保存后的摘要")
        self.assertEqual(draft.applicable_scope, {"system": "Linux", "nested": {"value": 1}})
        self.assertEqual(draft.body_plaintext, "自动保存后的正文")
        self.assertEqual(draft.change_summary, "自动保存后的版本说明")
        self.assertEqual(article.latest_working_version_id, self.draft.pk)
        self.assertEqual(article.current_published_version_id, self.published.pk)
        self.assertEqual(article.updated_at, article_before.updated_at)
        self.assertEqual(article.title, article_before.title)

    def test_new_article_v1_draft_is_updated_without_creating_v2(self):
        article = self.make_article("KB-320003", owner=self.owner)
        draft = ArticleVersion.objects.create(
            article=article,
            version_no=1,
            status=VersionStatus.DRAFT,
            title="v1 标题",
            summary="v1 摘要",
            body_plaintext="v1 正文",
            change_summary="v1 说明",
            created_by=self.owner,
        )
        Article.objects.filter(pk=article.pk).update(latest_working_version=draft)
        url = reverse("knowledge_manage:autosave", args=[article.kb_no])
        payload = self.payload(draft_id=str(draft.pk), expected_lock_version=1)

        response = self.post_json(payload, url=url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(article.versions.count(), 1)
        draft.refresh_from_db()
        self.assertEqual(draft.version_no, 1)
        self.assertEqual(draft.lock_version, 2)

    def test_edit_refresh_reads_autosaved_content_and_new_lock_token(self):
        saved = self.post_json(self.payload(title="刷新后的草稿标题"))

        self.assertEqual(saved.status_code, 200)
        refreshed = self.client.get(reverse("knowledge_manage:edit", args=[self.article.kb_no]))
        self.assertEqual(refreshed.status_code, 200)
        self.assertContains(refreshed, 'value="刷新后的草稿标题"')
        self.assertContains(refreshed, 'data-version-no="2"')
        self.assertContains(refreshed, 'name="expected_lock_version"')
        self.assertContains(refreshed, 'value="8"')

    def test_two_window_stale_token_returns_409_without_overwriting_first_write(self):
        first = self.post_json(self.payload(title="窗口 A 标题"))
        stale = self.post_json(self.payload(title="窗口 B 标题"))

        self.assertEqual(first.status_code, 200)
        self.assert_error(stale, status=409, code=DRAFT_CONFLICT)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.lock_version, 8)
        self.assertEqual(self.draft.title, "窗口 A 标题")

    def test_wrong_or_noncurrent_draft_is_safe(self):
        cases = (
            (self.published.pk, DRAFT_NOT_CURRENT, 409),
            (self.other_draft.pk, "DRAFT_NOT_FOUND_OR_INACCESSIBLE", 404),
        )
        for draft_id, code, status in cases:
            with self.subTest(code=code):
                response = self.post_json(self.payload(draft_id=str(draft_id)))
                self.assert_error(response, status=status, code=code)

    def test_role_account_and_object_boundaries(self):
        staff = self.make_user("autosave-staff", is_staff=True)
        superuser = User.objects.create_superuser(
            username="autosave-superuser", email="", password="unused"
        )
        disabled = self.make_user(
            "autosave-disabled",
            Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name),
            account_status=AccountStatus.DISABLED,
        )
        inactive = self.make_user(
            "autosave-inactive",
            Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name),
            is_active=False,
        )
        for actor in (self.employee, self.reviewer, staff, superuser):
            with self.subTest(actor=actor.username):
                client = Client()
                client.force_login(actor)
                self.assert_error(
                    self.post_json(client=client),
                    status=403,
                    code="PERMISSION_DENIED",
                )
        for actor in (inactive, disabled):
            with self.subTest(actor=actor.username):
                client = Client()
                client.force_login(actor)
                self.assert_error(
                    self.post_json(client=client),
                    status=401,
                    code="ACCOUNT_INACTIVE",
                )

        client = Client()
        client.force_login(self.other_editor)
        self.assert_error(
            self.post_json(client=client),
            status=404,
            code="DRAFT_NOT_FOUND_OR_INACCESSIBLE",
        )

    def test_owner_space_owner_and_admin_can_autosave(self):
        for index, actor in enumerate((self.owner, self.space_owner, self.admin), start=1):
            with self.subTest(actor=actor.username):
                self.draft.refresh_from_db()
                client = Client()
                client.force_login(actor)
                response = self.post_json(
                    self.payload(
                        expected_lock_version=self.draft.lock_version,
                        title=f"授权保存 {index}",
                    ),
                    client=client,
                )
                self.assertEqual(response.status_code, 200)

    def test_csrf_is_required_and_valid_token_allows_autosave(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        missing = self.post_json(client=client)
        self.assertEqual(missing.status_code, 403)

        edit = client.get(reverse("knowledge_manage:edit", args=[self.article.kb_no]))
        self.assertEqual(edit.status_code, 200)
        token = client.cookies["csrftoken"].value
        valid = client.post(
            self.url,
            data=json.dumps(self.payload()),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(valid.status_code, 200)

    def test_known_service_errors_have_safe_http_mapping(self):
        cases = (
            (ARTICLE_VERSION_WRITE_PERMISSION_DENIED, 403),
            (ARTICLE_VERSION_WRITE_INVALID_INPUT, 400),
            (DRAFT_NOT_CURRENT, 409),
            (INVALID_DRAFT_STATE, 409),
            (MODEL_CONSISTENCY_FAILED, 409),
            (DATABASE_WRITE_FAILED, 503),
        )
        for code, status in cases:
            with self.subTest(code=code):
                error = ArticleVersionWriteError(code, "安全公开消息")
                with mock.patch("apps.knowledge.manage_views.autosave_draft", side_effect=error):
                    response = self.post_json()
                self.assert_error(response, status=status, code=code)

    def test_database_internal_details_are_not_exposed(self):
        error = ArticleVersionWriteError(
            DATABASE_WRITE_FAILED,
            "草稿保存失败，请稍后重试。",
        )
        error.__cause__ = RuntimeError("SECRET SQL constraint kb_private_dsn")
        with mock.patch("apps.knowledge.manage_views.autosave_draft", side_effect=error):
            response = self.post_json()

        self.assert_error(response, status=503, code=DATABASE_WRITE_FAILED)
        rendered = response.content.decode().lower()
        for secret in ("secret", "sql", "constraint", "dsn"):
            self.assertNotIn(secret, rendered)
