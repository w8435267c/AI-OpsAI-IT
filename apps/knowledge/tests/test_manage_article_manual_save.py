"""Task 12E-06：管理编辑器 Manual Save HTTP 与版本切换合同。"""

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
from apps.knowledge.readers import get_employee_article_detail
from apps.knowledge.services import (
    ARTICLE_VERSION_WRITE_INVALID_INPUT,
    ARTICLE_VERSION_WRITE_PERMISSION_DENIED,
    DATABASE_WRITE_FAILED,
    DRAFT_CONFLICT,
    DRAFT_NOT_CURRENT,
    INVALID_DRAFT_STATE,
    MODEL_CONSISTENCY_FAILED,
    VERSION_NUMBER_CONFLICT,
    ArticleVersionWriteError,
)


class ManageArticleManualSaveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0, stdout=StringIO())
        cls.editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        cls.admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)
        cls.reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)

        cls.owner = cls.make_user("manual-save-owner", cls.editor_group)
        cls.space_owner = cls.make_user("manual-save-space-owner", cls.editor_group)
        cls.other_editor = cls.make_user("manual-save-other-editor", cls.editor_group)
        cls.admin = cls.make_user("manual-save-admin", cls.admin_group)
        cls.employee = cls.make_user("manual-save-employee")
        cls.reviewer = cls.make_user("manual-save-reviewer", cls.reviewer_group)

        cls.space = KnowledgeSpace.objects.create(
            code="manual-save-space",
            name="手动保存空间",
            space_type="employee",
            owner=cls.space_owner,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="manual-save-category",
            name="手动保存分类",
        )
        cls.article = cls.make_article("KB-330001", owner=cls.owner)
        cls.published = ArticleVersion.objects.create(
            article=cls.article,
            version_no=5,
            status=VersionStatus.PUBLISHED,
            title="员工可见正式标题",
            summary="员工可见正式摘要",
            applicable_scope={"published": True},
            body_plaintext="员工可见正式正文",
            change_summary="正式版本",
            created_by=cls.owner,
            submitted_by=cls.owner,
            submitted_at=timezone.now(),
            published_at=timezone.now(),
        )
        cls.high_history = ArticleVersion.objects.create(
            article=cls.article,
            version_no=10,
            status=VersionStatus.SAVED,
            title="高位历史标题",
            summary="高位历史摘要",
            body_plaintext="高位历史正文",
            change_summary="高位历史说明",
            created_by=cls.owner,
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
            code="manual-save-other-space",
            name="其他手动保存空间",
            space_type="employee",
            owner=cls.other_editor,
        )
        cls.other_category = Category.objects.create(
            space=cls.other_space,
            code="manual-save-other-category",
            name="其他分类",
        )
        cls.other_article = cls.make_article(
            "KB-330002",
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
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            owner=owner,
            article_status=ArticleStatus.ACTIVE,
            created_by=owner,
            updated_by=owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse("knowledge_manage:save", args=[self.article.kb_no])

    def payload(self, **overrides):
        payload = {
            "draft_id": str(self.draft.pk),
            "expected_lock_version": 7,
            "title": "手动保存后的标题",
            "summary": "手动保存后的摘要",
            "applicable_scope": {"system": "Linux", "nested": {"value": 1}},
            "body_text": "手动保存后的正文",
            "change_summary": "本次保存的版本说明",
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
                self.assert_error(response, status=405, code="METHOD_NOT_ALLOWED")
                self.assertEqual(response["Allow"], "POST")

    def test_json_boundary_rejects_invalid_bodies(self):
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

    def test_unknown_and_missing_fields_are_rejected(self):
        for field in (
            "version_no",
            "status",
            "lock_version",
            "owner",
            "space",
            "published_at",
        ):
            with self.subTest(unknown=field):
                response = self.post_json(self.payload(**{field: "forbidden"}))
                self.assert_error(response, status=400, code="UNKNOWN_FIELDS")

        for field in self.payload():
            with self.subTest(missing=field):
                payload = self.payload()
                payload.pop(field)
                response = self.post_json(payload)
                self.assert_error(response, status=400, code="INVALID_REQUEST")

    def test_identity_and_content_validation_reuse_strict_contract(self):
        identity_cases = (
            {"draft_id": None},
            {"draft_id": "not-a-uuid"},
            {"expected_lock_version": None},
            {"expected_lock_version": 0},
            {"expected_lock_version": -1},
            {"expected_lock_version": True},
            {"expected_lock_version": 1.5},
            {"expected_lock_version": "7"},
        )
        for overrides in identity_cases:
            with self.subTest(identity=overrides):
                self.assert_error(
                    self.post_json(self.payload(**overrides)),
                    status=400,
                    code="INVALID_REQUEST",
                )

        for overrides in (
            {"title": "题" * 61},
            {"summary": "   "},
            {"body_text": "   "},
            {"change_summary": "   "},
            {"applicable_scope": []},
            {"applicable_scope": None},
        ):
            with self.subTest(content=overrides):
                self.assert_error(
                    self.post_json(self.payload(**overrides)),
                    status=400,
                    code="INVALID_CONTENT",
                )

    def test_success_freezes_old_row_and_returns_complete_new_draft(self):
        version_count = ArticleVersion.objects.count()
        review_count = ReviewRecord.objects.count()

        response = self.post_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(
            body["saved"],
            {
                "id": str(self.draft.pk),
                "version_no": 2,
                "status": VersionStatus.SAVED,
                "lock_version": 8,
            },
        )
        self.assertNotEqual(body["draft"]["id"], str(self.draft.pk))
        self.assertEqual(body["draft"]["version_no"], 11)
        self.assertEqual(body["draft"]["status"], VersionStatus.DRAFT)
        self.assertEqual(body["draft"]["status_label"], "草稿")
        self.assertEqual(body["draft"]["lock_version"], 1)
        self.assertEqual(body["draft"]["title"], "手动保存后的标题")
        self.assertEqual(body["draft"]["summary"], "手动保存后的摘要")
        self.assertEqual(
            body["draft"]["applicable_scope"],
            {"system": "Linux", "nested": {"value": 1}},
        )
        self.assertEqual(body["draft"]["body_text"], "手动保存后的正文")
        self.assertEqual(
            body["draft"]["change_summary"],
            "基于已保存版本 v2 继续编辑",
        )
        self.assertIsNone(body["draft"]["restored_from_version_no"])
        self.assertTrue(body["draft"]["updated_at"])

        old_draft = ArticleVersion.objects.get(pk=self.draft.pk)
        new_draft = ArticleVersion.objects.get(pk=body["draft"]["id"])
        article = Article.objects.get(pk=self.article.pk)
        self.assertEqual(old_draft.status, VersionStatus.SAVED)
        self.assertEqual(old_draft.lock_version, 8)
        self.assertEqual(old_draft.title, "手动保存后的标题")
        self.assertEqual(old_draft.summary, "手动保存后的摘要")
        self.assertEqual(old_draft.applicable_scope, body["draft"]["applicable_scope"])
        self.assertEqual(old_draft.body_plaintext, "手动保存后的正文")
        self.assertEqual(old_draft.change_summary, "本次保存的版本说明")
        self.assertEqual(new_draft.status, VersionStatus.DRAFT)
        self.assertEqual(new_draft.version_no, 11)
        self.assertEqual(new_draft.lock_version, 1)
        self.assertEqual(new_draft.title, old_draft.title)
        self.assertEqual(new_draft.summary, old_draft.summary)
        self.assertEqual(new_draft.applicable_scope, old_draft.applicable_scope)
        self.assertEqual(new_draft.body_plaintext, old_draft.body_plaintext)
        self.assertEqual(new_draft.change_summary, body["draft"]["change_summary"])
        self.assertIsNone(new_draft.restored_from_version_id)
        self.assertEqual(ArticleVersion.objects.count(), version_count + 1)
        self.assertEqual(ReviewRecord.objects.count(), review_count)
        self.assertEqual(article.latest_working_version_id, new_draft.pk)
        self.assertEqual(article.current_published_version_id, self.published.pk)

    def test_manual_save_keeps_employee_on_published_version(self):
        before = get_employee_article_detail(self.employee, self.article.kb_no)

        response = self.post_json()

        after = get_employee_article_detail(self.employee, self.article.kb_no)
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(before)
        self.assertEqual(after, before)
        self.assertEqual(after.title, "员工可见正式标题")
        self.assertNotEqual(after.title, response.json()["draft"]["title"])

    def test_stale_manual_request_is_409_without_half_product(self):
        first = self.post_json()
        version_count = ArticleVersion.objects.count()
        second = self.post_json()

        self.assertEqual(first.status_code, 200)
        self.assert_error(second, status=409, code=DRAFT_NOT_CURRENT)
        self.assertEqual(ArticleVersion.objects.count(), version_count)
        self.assertEqual(
            ArticleVersion.objects.filter(
                article=self.article,
                status=VersionStatus.DRAFT,
            ).count(),
            1,
        )
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, VersionStatus.SAVED)
        self.assertEqual(self.draft.title, "手动保存后的标题")

    def test_stale_token_is_409_without_any_version_change(self):
        version_count = ArticleVersion.objects.count()

        response = self.post_json(self.payload(expected_lock_version=6))

        self.assert_error(response, status=409, code=DRAFT_CONFLICT)
        self.assertEqual(ArticleVersion.objects.count(), version_count)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, VersionStatus.DRAFT)
        self.assertEqual(self.draft.lock_version, 7)
        self.assertEqual(self.draft.title, "初始草稿标题")
        self.article.refresh_from_db()
        self.assertEqual(self.article.latest_working_version_id, self.draft.pk)

    def test_old_draft_autosave_fails_and_new_draft_autosave_succeeds(self):
        manual = self.post_json()
        self.assertEqual(manual.status_code, 200)
        draft = manual.json()["draft"]

        old_autosave = self.client.post(
            reverse("knowledge_manage:autosave", args=[self.article.kb_no]),
            data=json.dumps(self.payload(expected_lock_version=8)),
            content_type="application/json",
        )
        self.assert_error(old_autosave, status=409, code=DRAFT_NOT_CURRENT)

        new_payload = self.payload(
            draft_id=draft["id"],
            expected_lock_version=draft["lock_version"],
            title="新草稿继续自动保存",
            change_summary="新草稿自动保存说明",
        )
        new_autosave = self.client.post(
            reverse("knowledge_manage:autosave", args=[self.article.kb_no]),
            data=json.dumps(new_payload),
            content_type="application/json",
        )
        self.assertEqual(new_autosave.status_code, 200)
        self.assertEqual(new_autosave.json()["draft"]["id"], draft["id"])
        self.assertEqual(new_autosave.json()["draft"]["lock_version"], 2)
        new_draft = ArticleVersion.objects.get(pk=draft["id"])
        self.assertEqual(new_draft.title, "新草稿继续自动保存")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, VersionStatus.SAVED)
        self.assertEqual(self.draft.title, "手动保存后的标题")

    def test_edit_refresh_reads_new_working_draft_contract(self):
        manual = self.post_json()
        draft = manual.json()["draft"]

        response = self.client.get(reverse("knowledge_manage:edit", args=[self.article.kb_no]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{draft["id"]}"')
        self.assertContains(response, 'data-version-no="11"')
        self.assertContains(response, 'value="1"')
        self.assertContains(response, "基于已保存版本 v2 继续编辑")
        self.assertNotContains(response, f'value="{self.draft.pk}"')

    def test_role_account_and_object_boundaries(self):
        staff = self.make_user("manual-save-staff", is_staff=True)
        superuser = User.objects.create_superuser(
            username="manual-save-superuser", email="", password="unused"
        )
        disabled = self.make_user(
            "manual-save-disabled",
            self.editor_group,
            account_status=AccountStatus.DISABLED,
        )
        inactive = self.make_user(
            "manual-save-inactive",
            self.editor_group,
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

    def test_owner_space_owner_and_admin_can_manual_save(self):
        for index, actor in enumerate((self.owner, self.space_owner, self.admin), start=1):
            with self.subTest(actor=actor.username):
                article = self.make_article(f"KB-3301{index:02d}", owner=self.owner)
                draft = ArticleVersion.objects.create(
                    article=article,
                    version_no=1,
                    status=VersionStatus.DRAFT,
                    title="授权草稿",
                    summary="授权摘要",
                    body_plaintext="授权正文",
                    change_summary="授权说明",
                    created_by=self.owner,
                )
                Article.objects.filter(pk=article.pk).update(latest_working_version=draft)
                client = Client()
                client.force_login(actor)
                response = self.post_json(
                    self.payload(
                        draft_id=str(draft.pk),
                        expected_lock_version=1,
                        title=f"授权保存 {index}",
                    ),
                    client=client,
                    url=reverse("knowledge_manage:save", args=[article.kb_no]),
                )
                self.assertEqual(response.status_code, 200)

    def test_csrf_is_required_and_valid_token_allows_manual_save(self):
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
        self.assertEqual(valid["Cache-Control"], "private, no-store")

    def test_known_service_errors_have_safe_http_mapping(self):
        cases = (
            (ARTICLE_VERSION_WRITE_PERMISSION_DENIED, 403),
            (ARTICLE_VERSION_WRITE_INVALID_INPUT, 400),
            (DRAFT_NOT_CURRENT, 409),
            (DRAFT_CONFLICT, 409),
            (INVALID_DRAFT_STATE, 409),
            (VERSION_NUMBER_CONFLICT, 409),
            (MODEL_CONSISTENCY_FAILED, 409),
            (DATABASE_WRITE_FAILED, 503),
        )
        for code, status in cases:
            with self.subTest(code=code):
                error = ArticleVersionWriteError(code, "安全公开消息")
                with mock.patch("apps.knowledge.manage_views.manual_save_draft", side_effect=error):
                    response = self.post_json()
                self.assert_error(response, status=status, code=code)

    def test_database_internal_details_are_not_exposed(self):
        error = ArticleVersionWriteError(
            DATABASE_WRITE_FAILED,
            "版本保存失败，请稍后重试。",
        )
        error.__cause__ = RuntimeError("SECRET SQL constraint kb_private_dsn")
        with mock.patch("apps.knowledge.manage_views.manual_save_draft", side_effect=error):
            response = self.post_json()

        self.assert_error(response, status=503, code=DATABASE_WRITE_FAILED)
        rendered = response.content.decode().lower()
        for secret in ("secret", "sql", "constraint", "dsn"):
            self.assertNotIn(secret, rendered)

    def test_http_create_autosave_manual_and_new_autosave_complete_chain(self):
        chain_space = KnowledgeSpace.objects.create(
            code="manual-chain-space",
            name="完整链空间",
            space_type="employee",
            owner=self.owner,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        chain_category = Category.objects.create(
            space=chain_space,
            code="manual-chain-category",
            name="完整链分类",
        )
        create_response = self.client.post(
            reverse("knowledge_manage:create"),
            {
                "space": str(chain_space.pk),
                "category": str(chain_category.pk),
                "article_type": ArticleType.GUIDE,
                "title": "完整链初始标题",
                "summary": "完整链初始摘要",
                "applicable_scope": '{"stage": "create"}',
                "body_text": "完整链初始正文",
                "change_summary": "创建首个草稿",
                "audience_policy": AudiencePolicy.ALL_EMPLOYEES,
                "effective_at": "",
                "review_due_at": (timezone.now() + timedelta(days=180)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            },
        )
        self.assertEqual(create_response.status_code, 303)
        article = (
            Article.objects.exclude(pk=self.article.pk).exclude(pk=self.other_article.pk).get()
        )
        draft_v1 = article.latest_working_version
        self.assertEqual(draft_v1.version_no, 1)

        autosave_payload = self.payload(
            draft_id=str(draft_v1.pk),
            expected_lock_version=1,
            title="完整链自动保存标题",
            body_text="完整链自动保存正文",
        )
        autosave = self.client.post(
            reverse("knowledge_manage:autosave", args=[article.kb_no]),
            data=json.dumps(autosave_payload),
            content_type="application/json",
        )
        self.assertEqual(autosave.status_code, 200)
        self.assertEqual(autosave.json()["draft"]["lock_version"], 2)

        manual_payload = {
            **autosave_payload,
            "expected_lock_version": 2,
            "title": "完整链手动保存标题",
            "body_text": "完整链手动保存正文",
            "change_summary": "完整链冻结 v1",
        }
        manual = self.client.post(
            reverse("knowledge_manage:save", args=[article.kb_no]),
            data=json.dumps(manual_payload),
            content_type="application/json",
        )
        self.assertEqual(manual.status_code, 200)
        draft_v2_payload = manual.json()["draft"]
        self.assertEqual(draft_v2_payload["version_no"], 2)
        self.assertEqual(draft_v2_payload["lock_version"], 1)

        continued_payload = {
            **manual_payload,
            "draft_id": draft_v2_payload["id"],
            "expected_lock_version": draft_v2_payload["lock_version"],
            "title": "完整链新草稿继续编辑",
            "change_summary": "完整链新草稿说明",
        }
        continued = self.client.post(
            reverse("knowledge_manage:autosave", args=[article.kb_no]),
            data=json.dumps(continued_payload),
            content_type="application/json",
        )
        self.assertEqual(continued.status_code, 200)

        article.refresh_from_db()
        draft_v1.refresh_from_db()
        draft_v2 = ArticleVersion.objects.get(pk=draft_v2_payload["id"])
        self.assertEqual(draft_v1.status, VersionStatus.SAVED)
        self.assertEqual(draft_v1.title, "完整链手动保存标题")
        self.assertEqual(draft_v2.status, VersionStatus.DRAFT)
        self.assertEqual(draft_v2.lock_version, 2)
        self.assertEqual(draft_v2.title, "完整链新草稿继续编辑")
        self.assertEqual(article.latest_working_version_id, draft_v2.pk)
        self.assertIsNone(article.current_published_version_id)
        self.assertEqual(
            ArticleVersion.objects.filter(
                article=article,
                status=VersionStatus.DRAFT,
            ).count(),
            1,
        )
