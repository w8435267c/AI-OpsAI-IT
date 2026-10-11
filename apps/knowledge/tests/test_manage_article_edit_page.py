"""Task 12E-03：创建成功后的最小 working DRAFT 落地页合同。"""

from datetime import timedelta
from io import StringIO
from pathlib import Path

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
from apps.knowledge.manage_forms import ArticleDraftForm
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
    ReviewRecord,
    VersionStatus,
)


class ArticleDraftFormTests(SimpleTestCase):
    def valid_data(self, **overrides):
        data = {
            "title": "当前草稿标题",
            "summary": "当前草稿摘要",
            "applicable_scope": '{"note": "中文", "nested": {"value": 1}}',
            "body_text": "当前草稿正文",
            "change_summary": "当前版本说明",
        }
        data.update(overrides)
        return data

    def test_field_whitelist_is_exactly_the_five_working_content_fields(self):
        form = ArticleDraftForm()

        self.assertEqual(
            list(form.fields),
            [
                "title",
                "summary",
                "applicable_scope",
                "body_text",
                "change_summary",
            ],
        )
        forbidden = {
            "space",
            "category",
            "owner",
            "article_type",
            "audience_policy",
            "effective_at",
            "review_due_at",
            "kb_no",
            "draft_id",
            "version_no",
            "status",
            "lock_version",
            "expected_lock_version",
            "latest_working_version",
            "current_published_version",
            "submitted_by",
            "submitted_at",
            "published_at",
            "restored_from_version",
        }
        self.assertTrue(forbidden.isdisjoint(form.fields))

    def test_valid_content_and_json_objects_are_accepted(self):
        cases = (
            ("empty", "{}", {}),
            ("nested", '{"nested": {"value": 1}}', {"nested": {"value": 1}}),
            ("chinese", '{"说明": "中文范围"}', {"说明": "中文范围"}),
        )
        for label, raw_scope, expected_scope in cases:
            with self.subTest(label=label):
                form = ArticleDraftForm(data=self.valid_data(applicable_scope=raw_scope))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["applicable_scope"], expected_scope)

    def test_non_object_and_malformed_json_are_rejected(self):
        cases = (
            ("list", "[]"),
            ("string", '"abc"'),
            ("number", "123"),
            ("boolean", "true"),
            ("null", "null"),
            ("malformed", "{invalid"),
        )
        for label, raw_scope in cases:
            with self.subTest(label=label):
                form = ArticleDraftForm(data=self.valid_data(applicable_scope=raw_scope))
                self.assertFalse(form.is_valid())
                self.assertIn("applicable_scope", form.errors)

    def test_scope_initial_value_is_pretty_json_without_unicode_escaping(self):
        form = ArticleDraftForm(initial={"applicable_scope": {"说明": "中文"}})

        self.assertEqual(
            form["applicable_scope"].value(),
            '{\n  "说明": "中文"\n}',
        )

    def test_lengths_and_required_rules_match_the_write_service(self):
        form = ArticleDraftForm()
        self.assertEqual(form.fields["title"].max_length, 60)
        self.assertEqual(form.fields["summary"].max_length, 500)
        self.assertEqual(form.fields["change_summary"].max_length, 500)
        self.assertIsNone(form.fields["body_text"].max_length)

        valid = ArticleDraftForm(
            data=self.valid_data(
                title="标" * 60,
                summary="摘" * 500,
                change_summary="改" * 500,
            )
        )
        self.assertTrue(valid.is_valid(), valid.errors)

        for field, value in (
            ("title", "标" * 61),
            ("title", " " + "标" * 60),
            ("summary", "摘" * 501),
            ("change_summary", "改" * 501),
            ("title", "   "),
            ("summary", "   "),
            ("body_text", "   "),
            ("change_summary", "   "),
        ):
            with self.subTest(field=field, length=len(value)):
                invalid = ArticleDraftForm(data=self.valid_data(**{field: value}))
                self.assertFalse(invalid.is_valid())
                self.assertIn(field, invalid.errors)


class KnowledgeEditorJavaScriptContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = (Path(settings.BASE_DIR) / "static" / "js" / "knowledge_editor.js").read_text(
            encoding="utf-8"
        )

    def test_debounce_and_single_flight_state_are_explicit(self):
        self.assertIn("const DEBOUNCE_MS = 2000", self.source)
        self.assertIn("let debounceTimer", self.source)
        self.assertIn("let inFlight = false", self.source)
        self.assertIn("let dirty = false", self.source)
        self.assertIn("let blocked = false", self.source)
        self.assertIn("if (blocked || inFlight || !dirty)", self.source)

    def test_request_is_full_json_snapshot_with_csrf(self):
        for field in (
            "draft_id",
            "expected_lock_version",
            "title",
            "summary",
            "applicable_scope",
            "body_text",
            "change_summary",
        ):
            with self.subTest(field=field):
                self.assertIn(field, self.source)
        self.assertIn('"Content-Type": "application/json"', self.source)
        self.assertIn('"X-CSRFToken": csrfToken.value', self.source)
        self.assertIn("JSON.stringify(snapshot)", self.source)

    def test_success_uses_server_token_and_validates_draft_identity(self):
        self.assertIn("payload.draft.id !== snapshot.draft_id", self.source)
        self.assertIn("payload.draft.version_no !== pageVersion", self.source)
        self.assertIn(
            "lockVersion.value = String(payload.draft.lock_version)",
            self.source,
        )
        self.assertNotIn("expected_lock_version +=", self.source)
        self.assertNotIn("lockVersion.value++", self.source)

    def test_conflict_network_and_server_failures_block_without_retry(self):
        self.assertIn("response.status === 409", self.source)
        self.assertIn("response.status >= 500", self.source)
        self.assertIn("catch (error)", self.source)
        self.assertIn("blockAutosave", self.source)
        self.assertNotIn("fetchWithRetry", self.source)

    def test_scope_requires_a_plain_json_object_before_fetch(self):
        self.assertIn("JSON.parse(scope.value)", self.source)
        self.assertIn("Array.isArray(parsedScope)", self.source)
        self.assertIn("parsedScope === null", self.source)
        self.assertIn("适用范围不是有效的 JSON 对象", self.source)

    def test_browser_storage_html_injection_and_unload_writes_are_absent(self):
        for forbidden in (
            "localStorage",
            "sessionStorage",
            "IndexedDB",
            "indexedDB",
            "innerHTML",
            "beforeunload",
            "sendBeacon",
            "eval(",
            "new Function",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)
        self.assertIn("status.textContent = message", self.source)


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
        cls.source = ArticleVersion.objects.create(
            article=cls.article,
            version_no=1,
            status=VersionStatus.SAVED,
            title="历史来源",
            summary="历史摘要",
            change_summary="历史说明",
            created_by=cls.article_owner,
        )
        cls.draft = ArticleVersion.objects.create(
            article=cls.article,
            version_no=2,
            status=VersionStatus.DRAFT,
            lock_version=7,
            title="REAL-DRAFT-TITLE",
            summary="当前草稿摘要",
            applicable_scope={"说明": "中文范围", "nested": {"value": 1}},
            body_plaintext='<script>alert("draft")</script>\n<img src=x>\n<b>正文</b>',
            change_summary="当前草稿说明",
            restored_from_version=cls.source,
            created_by=cls.article_owner,
        )
        Article.objects.filter(pk=cls.article.pk).update(latest_working_version=cls.draft)

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
        cls.other_draft = ArticleVersion.objects.create(
            article=cls.other_article,
            version_no=1,
            status=VersionStatus.DRAFT,
            title="其他秘密草稿",
            summary="其他摘要",
            body_plaintext="其他正文",
            change_summary="其他说明",
            created_by=cls.other_editor,
        )
        Article.objects.filter(pk=cls.other_article.pk).update(
            latest_working_version=cls.other_draft
        )

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

        self.assertContains(response, 'name="title"')
        self.assertContains(response, 'value="REAL-DRAFT-TITLE"')
        self.assertNotContains(response, "OLD-COMPAT-TITLE")
        self.assertContains(response, "&lt;script&gt;", html=False)
        self.assertContains(response, "&lt;img src=x&gt;", html=False)
        self.assertContains(response, "&lt;b&gt;正文&lt;/b&gt;", html=False)
        self.assertNotContains(response, '<script>alert("draft")</script>', html=False)

    def test_page_renders_browser_version_contract_and_draft_fields(self):
        response = self.get_as(self.article_owner)

        self.assertContains(response, 'id="knowledge-editor"')
        self.assertContains(response, f'data-kb-no="{self.article.kb_no}"')
        self.assertContains(response, 'data-version-no="2"')
        self.assertContains(response, 'name="draft_id"')
        self.assertContains(response, f'value="{self.draft.pk}"')
        self.assertContains(response, 'name="expected_lock_version"')
        self.assertContains(response, 'value="7"')
        for field_name in (
            "title",
            "summary",
            "applicable_scope",
            "body_text",
            "change_summary",
        ):
            with self.subTest(field_name=field_name):
                self.assertContains(response, f'name="{field_name}"')

        for forbidden_name in (
            "version_no",
            "status",
            "lock_version",
            "owner",
            "space",
            "category",
        ):
            with self.subTest(forbidden_name=forbidden_name):
                self.assertNotContains(response, f'name="{forbidden_name}"')

        self.assertContains(response, "&quot;说明&quot;: &quot;中文范围&quot;", html=False)
        self.assertContains(response, "当前为草稿")
        self.assertContains(response, "v2")
        self.assertContains(response, "锁版本 7")
        self.assertContains(response, "恢复自 v1")
        self.assertContains(response, self.space.name)
        self.assertContains(response, self.category.name)
        self.assertContains(response, str(self.article_owner))

    def test_page_is_get_only_for_every_write_method(self):
        client = Client()
        client.force_login(self.article_owner)
        url = reverse("knowledge_manage:edit", args=[self.article.kb_no])

        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(client, method)(url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "GET")
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_page_loads_autosave_contract_without_future_controls(self):
        page = self.get_as(self.article_owner)
        autosave_url = reverse("knowledge_manage:autosave", args=[self.article.kb_no])

        self.assertNotContains(page, "<form", html=False)
        self.assertNotContains(page, 'type="submit"', html=False)
        self.assertNotContains(page, "<button", html=False)
        self.assertContains(
            page,
            f'data-autosave-url="{autosave_url}"',
        )
        self.assertContains(page, 'name="csrfmiddlewaretoken"')
        self.assertContains(page, 'id="autosave-status"')
        self.assertContains(page, 'aria-live="polite"')
        self.assertContains(page, "未修改")
        self.assertContains(page, 'id="autosave-reload"')
        self.assertContains(page, "js/knowledge_editor.js")
        self.assertNotContains(page, "保存版本")
        self.assertNotContains(page, "提交审核")
        self.assertNotContains(page, "发布")
        self.assertNotContains(page, "预览")
        self.assertNotContains(page, "当前阶段尚未接入保存功能")

    def test_all_editable_values_are_loaded_from_same_working_draft(self):
        ArticleVersion.objects.filter(pk=self.draft.pk).update(
            body={"format": "opsai.plaintext/1", "text": "结构化字段不直接展示"},
        )

        response = self.get_as(self.article_owner)

        self.assertContains(response, 'value="REAL-DRAFT-TITLE"')
        self.assertContains(response, "当前草稿摘要")
        self.assertContains(response, "当前草稿说明")
        self.assertContains(
            response, "&lt;script&gt;alert(&quot;draft&quot;)&lt;/script&gt;", html=False
        )
        self.assertNotContains(response, "结构化字段不直接展示")

    def test_cross_article_working_pointer_is_safe_404(self):
        Article.objects.filter(pk=self.article.pk).update(latest_working_version=self.other_draft)

        response = self.get_as(self.article_owner)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_refresh_reads_the_new_current_draft_tokens_from_database(self):
        ArticleVersion.objects.filter(pk=self.draft.pk).update(status=VersionStatus.SAVED)
        next_draft = ArticleVersion.objects.create(
            article=self.article,
            version_no=3,
            status=VersionStatus.DRAFT,
            lock_version=1,
            title="刷新后的新草稿",
            summary="刷新后的摘要",
            applicable_scope={},
            body_plaintext="刷新后的正文",
            change_summary="刷新后的说明",
            created_by=self.article_owner,
        )
        Article.objects.filter(pk=self.article.pk).update(latest_working_version=next_draft)

        response = self.get_as(self.article_owner)

        self.assertContains(response, f'value="{next_draft.pk}"')
        self.assertContains(response, 'data-version-no="3"')
        self.assertContains(response, 'name="expected_lock_version"')
        self.assertContains(response, 'value="1"')
        self.assertContains(response, 'value="刷新后的新草稿"')
        self.assertNotContains(response, f'value="{self.draft.pk}"')

    def test_xss_payloads_are_escaped_inside_editor_fields(self):
        ArticleVersion.objects.filter(pk=self.draft.pk).update(
            title="<script>alert(1)</script>",
            summary="<img src=x onerror=alert(1)>",
            applicable_scope={"x": "<script>alert(2)</script>"},
            body_plaintext="<b>not html</b>",
            change_summary="<script>alert(3)</script>",
        )

        response = self.get_as(self.article_owner)
        html = response.content.decode()

        for raw_payload in (
            "<script>alert(1)</script>",
            "<img src=x onerror=alert(1)>",
            "<script>alert(2)</script>",
            "<b>not html</b>",
            "<script>alert(3)</script>",
        ):
            with self.subTest(raw_payload=raw_payload):
                self.assertNotIn(raw_payload, html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertIn("&lt;b&gt;not html&lt;/b&gt;", html)

    def test_get_editor_performs_no_database_writes(self):
        article_before = Article.objects.get(pk=self.article.pk)
        draft_before = ArticleVersion.objects.get(pk=self.draft.pk)
        article_snapshot = {
            "updated_at": article_before.updated_at,
            "latest_working_version_id": article_before.latest_working_version_id,
            "current_published_version_id": article_before.current_published_version_id,
        }
        draft_snapshot = {
            "title": draft_before.title,
            "summary": draft_before.summary,
            "applicable_scope": draft_before.applicable_scope,
            "body": draft_before.body,
            "body_plaintext": draft_before.body_plaintext,
            "change_summary": draft_before.change_summary,
            "lock_version": draft_before.lock_version,
            "updated_at": draft_before.updated_at,
        }
        version_count = ArticleVersion.objects.count()
        review_count = ReviewRecord.objects.count()

        response = self.get_as(self.article_owner)

        self.assertEqual(response.status_code, 200)
        article_after = Article.objects.get(pk=self.article.pk)
        draft_after = ArticleVersion.objects.get(pk=self.draft.pk)
        self.assertEqual(ArticleVersion.objects.count(), version_count)
        self.assertEqual(ReviewRecord.objects.count(), review_count)
        self.assertEqual(
            {
                "updated_at": article_after.updated_at,
                "latest_working_version_id": article_after.latest_working_version_id,
                "current_published_version_id": article_after.current_published_version_id,
            },
            article_snapshot,
        )
        self.assertEqual(
            {
                "title": draft_after.title,
                "summary": draft_after.summary,
                "applicable_scope": draft_after.applicable_scope,
                "body": draft_after.body,
                "body_plaintext": draft_after.body_plaintext,
                "change_summary": draft_after.change_summary,
                "lock_version": draft_after.lock_version,
                "updated_at": draft_after.updated_at,
            },
            draft_snapshot,
        )
