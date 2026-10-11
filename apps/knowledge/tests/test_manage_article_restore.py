"""Task 12E-07：管理侧历史 Restore HTTP 与完整版本链合同。"""

from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO
from unittest import mock
from uuid import uuid4

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
from apps.search.readers import search_employee_articles


class ManageArticleRestoreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0, stdout=StringIO())
        cls.editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        cls.admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)
        cls.reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)
        cls.owner = cls.make_user("restore-ui-owner", cls.editor_group)
        cls.space_owner = cls.make_user("restore-ui-space-owner", cls.editor_group)
        cls.other_editor = cls.make_user("restore-ui-other-editor", cls.editor_group)
        cls.admin = cls.make_user("restore-ui-admin", cls.admin_group)
        cls.employee = cls.make_user("restore-ui-employee")
        cls.reviewer = cls.make_user("restore-ui-reviewer", cls.reviewer_group)

        cls.space = KnowledgeSpace.objects.create(
            code="restore-ui-space",
            name="恢复页面空间",
            space_type="employee",
            owner=cls.space_owner,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="restore-ui-category",
            name="恢复页面分类",
        )
        cls.article = cls.make_article("KB-350001", cls.owner)
        cls.saved_source = cls.make_version(
            cls.article, 1, VersionStatus.SAVED, marker="SAVED-SOURCE"
        )
        cls.published = cls.make_version(
            cls.article, 2, VersionStatus.PUBLISHED, marker="PUBLISHED-AUTHORITY"
        )
        cls.high_history = cls.make_version(
            cls.article, 10, VersionStatus.SUPERSEDED, marker="HIGH-HISTORY"
        )
        cls.lineage_source = cls.make_version(
            cls.article, 4, VersionStatus.REJECTED, marker="OLD-LINEAGE"
        )
        cls.draft = ArticleVersion.objects.create(
            article=cls.article,
            version_no=5,
            status=VersionStatus.DRAFT,
            lock_version=7,
            title="数据库当前草稿标题",
            summary="数据库当前草稿摘要",
            applicable_scope={"db": "current"},
            body={"format": "opsai.plaintext/1", "text": "数据库当前草稿正文"},
            body_plaintext="数据库当前草稿正文",
            change_summary="数据库当前草稿说明",
            restored_from_version=cls.lineage_source,
            created_by=cls.owner,
        )
        Article.objects.filter(pk=cls.article.pk).update(
            latest_working_version=cls.draft,
            current_published_version=cls.published,
        )

        cls.other_space = KnowledgeSpace.objects.create(
            code="restore-ui-other-space",
            name="其他恢复空间",
            space_type="employee",
            owner=cls.other_editor,
        )
        cls.other_category = Category.objects.create(
            space=cls.other_space,
            code="restore-ui-other-category",
            name="其他恢复分类",
        )
        cls.other_article = cls.make_article(
            "KB-350002",
            cls.other_editor,
            space=cls.other_space,
            category=cls.other_category,
        )
        cls.other_source = cls.make_version(
            cls.other_article, 1, VersionStatus.SAVED, marker="OTHER-SECRET"
        )
        cls.other_draft = cls.make_version(
            cls.other_article, 2, VersionStatus.DRAFT, marker="OTHER-DRAFT"
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
    def make_article(cls, kb_no, owner, *, space=None, category=None):
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

    @classmethod
    def make_version(cls, article, version_no, status, *, marker):
        workflow = {}
        if status not in (VersionStatus.DRAFT, VersionStatus.SAVED):
            workflow.update(submitted_by=article.owner, submitted_at=timezone.now())
        if status == VersionStatus.PUBLISHED:
            workflow["published_at"] = timezone.now()
        return ArticleVersion.objects.create(
            article=article,
            version_no=version_no,
            status=status,
            lock_version=3,
            title=f"{marker} 标题",
            summary=f"{marker} 摘要",
            applicable_scope={"marker": marker},
            body={"format": "historical/1", "marker": marker},
            body_plaintext=f"{marker} 正文",
            change_summary=f"{marker} 说明",
            created_by=article.owner,
            **workflow,
        )

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse(
            "knowledge_manage:restore",
            args=[self.article.kb_no, self.saved_source.pk],
        )

    def payload(self, **overrides):
        data = {
            "draft_id": str(self.draft.pk),
            "expected_lock_version": "7",
            "title": "页面提交的当前标题",
            "summary": "页面提交的当前摘要",
            "applicable_scope": json.dumps(
                {"页面": "完整快照", "nested": {"value": 1}}, ensure_ascii=False
            ),
            "body_text": "页面提交的当前正文",
            "change_summary": "页面提交的当前说明",
        }
        data.update(overrides)
        return data

    @staticmethod
    def snapshot(version):
        return {
            "id": version.pk,
            "version_no": version.version_no,
            "status": version.status,
            "lock_version": version.lock_version,
            "title": version.title,
            "summary": version.summary,
            "applicable_scope": version.applicable_scope,
            "body": version.body,
            "body_plaintext": version.body_plaintext,
            "change_summary": version.change_summary,
            "restored_from_version_id": version.restored_from_version_id,
            "created_by_id": version.created_by_id,
            "submitted_by_id": version.submitted_by_id,
            "created_at": version.created_at,
            "updated_at": version.updated_at,
            "submitted_at": version.submitted_at,
            "published_at": version.published_at,
        }

    def test_restore_is_post_only_with_allow_and_no_store(self):
        for method in ("get", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "POST")
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_detail_form_contains_page_time_current_snapshot_and_url_source(self):
        detail_url = reverse(
            "knowledge_manage:history_detail",
            args=[self.article.kb_no, self.saved_source.pk],
        )
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        for name, value in (
            ("draft_id", self.draft.pk),
            ("expected_lock_version", 7),
            ("title", "数据库当前草稿标题"),
            ("summary", "数据库当前草稿摘要"),
            ("body_text", "数据库当前草稿正文"),
            ("change_summary", "数据库当前草稿说明"),
        ):
            self.assertContains(response, f'name="{name}"')
            self.assertContains(response, str(value))
        self.assertContains(response, f'action="{self.url}"')
        for forbidden in (
            "version_no",
            "status",
            "latest_working_version",
            "current_published_version",
            "restored_from_version",
        ):
            self.assertNotContains(response, f'name="{forbidden}"')

    def test_restore_success_obeys_atomic_version_contract(self):
        source_before = self.snapshot(self.saved_source)
        version_count = ArticleVersion.objects.filter(article=self.article).count()
        review_count = ReviewRecord.objects.count()

        response = self.client.post(self.url, data=self.payload())

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response["Location"], reverse("knowledge_manage:edit", args=[self.article.kb_no])
        )
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.article.refresh_from_db()
        self.draft.refresh_from_db()
        self.saved_source.refresh_from_db()
        new_draft = self.article.latest_working_version
        self.assertEqual(self.draft.status, VersionStatus.SAVED)
        self.assertEqual(self.draft.title, "页面提交的当前标题")
        self.assertEqual(self.draft.summary, "页面提交的当前摘要")
        self.assertEqual(self.draft.applicable_scope["页面"], "完整快照")
        self.assertEqual(self.draft.body_plaintext, "页面提交的当前正文")
        self.assertEqual(self.draft.change_summary, "页面提交的当前说明")
        self.assertEqual(self.draft.restored_from_version_id, self.lineage_source.pk)
        self.assertEqual(new_draft.status, VersionStatus.DRAFT)
        self.assertEqual(new_draft.version_no, 11)
        self.assertEqual(new_draft.lock_version, 1)
        self.assertEqual(new_draft.title, self.saved_source.title)
        self.assertEqual(new_draft.summary, self.saved_source.summary)
        self.assertEqual(new_draft.applicable_scope, self.saved_source.applicable_scope)
        self.assertEqual(new_draft.body, self.saved_source.body)
        self.assertEqual(new_draft.body_plaintext, self.saved_source.body_plaintext)
        self.assertEqual(new_draft.restored_from_version_id, self.saved_source.pk)
        self.assertEqual(new_draft.change_summary, "从版本 v1 恢复")
        self.assertEqual(self.article.current_published_version_id, self.published.pk)
        self.assertEqual(
            ArticleVersion.objects.filter(article=self.article).count(), version_count + 1
        )
        self.assertEqual(ReviewRecord.objects.count(), review_count)
        self.assertEqual(self.snapshot(self.saved_source), source_before)
        self.assertEqual(
            ArticleVersion.objects.filter(article=self.article, status=VersionStatus.DRAFT).count(),
            1,
        )

    def test_all_service_allowed_source_statuses_succeed(self):
        for index, status in enumerate(
            (
                VersionStatus.SAVED,
                VersionStatus.IN_REVIEW,
                VersionStatus.REJECTED,
                VersionStatus.PUBLISHED,
                VersionStatus.SUPERSEDED,
            ),
            start=10,
        ):
            with self.subTest(status=status):
                article = self.make_article(f"KB-35{index:04d}", self.owner)
                source = self.make_version(article, 3, status, marker=f"SOURCE-{status}")
                draft = self.make_version(article, 8, VersionStatus.DRAFT, marker="CURRENT")
                Article.objects.filter(pk=article.pk).update(latest_working_version=draft)
                url = reverse("knowledge_manage:restore", args=[article.kb_no, source.pk])
                response = self.client.post(
                    url,
                    data=self.payload(draft_id=str(draft.pk), expected_lock_version="3"),
                )
                self.assertEqual(response.status_code, 303)

    def test_draft_cross_article_and_missing_sources_are_safe_404_without_writes(self):
        before = ArticleVersion.objects.count()
        cases = (
            (
                self.draft.pk,
                reverse(
                    "knowledge_manage:restore",
                    args=[self.article.kb_no, self.draft.pk],
                ),
            ),
            (
                self.other_source.pk,
                reverse(
                    "knowledge_manage:restore",
                    args=[self.article.kb_no, self.other_source.pk],
                ),
            ),
            (
                uuid4(),
                reverse("knowledge_manage:restore", args=[self.article.kb_no, uuid4()]),
            ),
        )
        for _source_id, url in cases:
            with self.subTest(url=url):
                response = self.client.post(url, data=self.payload())
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response["Cache-Control"], "private, no-store")
                self.assertEqual(ArticleVersion.objects.count(), before)

    def test_invalid_and_unknown_form_fields_are_400_without_writes(self):
        before = list(ArticleVersion.objects.filter(article=self.article).values())
        cases = (
            self.payload(draft_id="not-a-uuid"),
            self.payload(expected_lock_version="0"),
            self.payload(title="   "),
            self.payload(applicable_scope="[]"),
            self.payload(version_no="999"),
            {key: value for key, value in self.payload().items() if key != "change_summary"},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                response = self.client.post(self.url, data=payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response["Cache-Control"], "private, no-store")
                self.assertEqual(
                    list(ArticleVersion.objects.filter(article=self.article).values()), before
                )

    def test_stale_token_is_409_and_does_not_refresh_token_or_partially_write(self):
        ArticleVersion.objects.filter(pk=self.draft.pk).update(lock_version=8)
        before = list(ArticleVersion.objects.filter(article=self.article).values())

        response = self.client.post(self.url, data=self.payload(expected_lock_version="7"))

        self.assertEqual(response.status_code, 409)
        self.assertContains(
            response,
            "当前草稿已发生变化，请刷新后重新确认恢复操作。",
            status_code=409,
        )
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(list(ArticleVersion.objects.filter(article=self.article).values()), before)

    def test_two_restore_windows_create_only_one_new_draft(self):
        first = self.client.post(self.url, data=self.payload())
        second = self.client.post(self.url, data=self.payload())
        self.article.refresh_from_db()

        self.assertEqual(first.status_code, 303)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(
            ArticleVersion.objects.filter(article=self.article, status=VersionStatus.DRAFT).count(),
            1,
        )
        self.assertEqual(self.article.latest_working_version.version_no, 11)

    def test_permissions_and_object_access_are_enforced(self):
        staff = self.make_user("restore-ui-staff", is_staff=True)
        superuser = User.objects.create_superuser(
            username="restore-ui-superuser", email="", password="unused"
        )
        inactive = self.make_user("restore-ui-inactive", self.editor_group, is_active=False)
        disabled = self.make_user(
            "restore-ui-disabled",
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
            (self.other_editor, 404),
        ):
            with self.subTest(actor=actor.username):
                client = Client()
                client.force_login(actor)
                self.assertEqual(client.post(self.url, data=self.payload()).status_code, status)

    def test_owner_space_owner_and_admin_can_restore_authorized_articles(self):
        for index, actor in enumerate((self.owner, self.space_owner, self.admin), start=30):
            with self.subTest(actor=actor.username):
                article = self.make_article(f"KB-35{index:04d}", self.owner)
                source = self.make_version(
                    article, 1, VersionStatus.SAVED, marker=f"ROLE-{actor.username}"
                )
                draft = self.make_version(article, 2, VersionStatus.DRAFT, marker="ROLE-CURRENT")
                Article.objects.filter(pk=article.pk).update(latest_working_version=draft)
                client = Client()
                client.force_login(actor)
                response = client.post(
                    reverse("knowledge_manage:restore", args=[article.kb_no, source.pk]),
                    data=self.payload(
                        draft_id=str(draft.pk), expected_lock_version=str(draft.lock_version)
                    ),
                )
                self.assertEqual(response.status_code, 303)

    def test_csrf_is_required_and_valid_token_enters_restore(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        missing = client.post(self.url, data=self.payload())
        self.assertEqual(missing.status_code, 403)

        detail_url = reverse(
            "knowledge_manage:history_detail",
            args=[self.article.kb_no, self.saved_source.pk],
        )
        page = client.get(detail_url)
        token = page.cookies["csrftoken"].value
        accepted = client.post(
            self.url,
            data=self.payload(csrfmiddlewaretoken=token),
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(accepted.status_code, 303)

    def test_restore_then_edit_and_autosave_use_new_draft_only(self):
        source_before = self.snapshot(self.saved_source)
        restore_response = self.client.post(self.url, data=self.payload())
        self.assertEqual(restore_response.status_code, 303)
        self.article.refresh_from_db()
        new_draft = self.article.latest_working_version

        edit = self.client.get(restore_response["Location"])
        self.assertContains(edit, f'value="{new_draft.pk}"')
        self.assertContains(edit, self.saved_source.title)

        autosave_url = reverse("knowledge_manage:autosave", args=[self.article.kb_no])
        autosave_payload = {
            "draft_id": str(new_draft.pk),
            "expected_lock_version": new_draft.lock_version,
            "title": "恢复后继续编辑",
            "summary": "恢复后摘要",
            "applicable_scope": {"after": "restore"},
            "body_text": "恢复后自动保存正文",
            "change_summary": "恢复后自动保存",
        }
        autosave = self.client.post(
            autosave_url,
            data=json.dumps(autosave_payload, ensure_ascii=False),
            content_type="application/json",
        )
        old_autosave = self.client.post(
            autosave_url,
            data=json.dumps(
                {**autosave_payload, "draft_id": str(self.draft.pk)}, ensure_ascii=False
            ),
            content_type="application/json",
        )
        self.assertEqual(autosave.status_code, 200)
        self.assertIn(old_autosave.status_code, (404, 409))
        new_draft.refresh_from_db()
        self.draft.refresh_from_db()
        self.saved_source.refresh_from_db()
        self.assertEqual(new_draft.title, "恢复后继续编辑")
        self.assertEqual(self.draft.status, VersionStatus.SAVED)
        self.assertEqual(self.snapshot(self.saved_source), source_before)

    def test_published_authority_and_employee_readers_remain_isolated(self):
        response = self.client.post(
            reverse(
                "knowledge_manage:restore",
                args=[self.article.kb_no, self.published.pk],
            ),
            data=self.payload(),
        )
        self.assertEqual(response.status_code, 303)
        self.article.refresh_from_db()
        self.assertEqual(self.article.current_published_version_id, self.published.pk)
        detail = get_employee_article_detail(self.employee, self.article.kb_no)
        self.assertEqual(detail.title, self.published.title)
        self.assertEqual(
            list(
                search_employee_articles(self.employee, "PUBLISHED-AUTHORITY").values_list(
                    "pk", flat=True
                )
            ),
            [self.article.pk],
        )
        self.assertFalse(search_employee_articles(self.employee, "数据库当前草稿").exists())

    def test_complete_create_autosave_save_history_restore_autosave_chain(self):
        self.client.force_login(self.space_owner)
        create = self.client.post(
            reverse("knowledge_manage:create"),
            data={
                "space": str(self.space.pk),
                "category": str(self.category.pk),
                "article_type": ArticleType.GUIDE,
                "title": "完整链新建标题",
                "summary": "完整链新建摘要",
                "applicable_scope": '{"chain": "create"}',
                "body_text": "完整链初始正文",
                "change_summary": "完整链创建",
                "audience_policy": AudiencePolicy.ALL_EMPLOYEES,
                "effective_at": "",
                "review_due_at": (timezone.now() + timedelta(days=180)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            },
        )
        self.assertEqual(create.status_code, 303)
        article = Article.objects.get(title="完整链新建标题")
        draft = article.latest_working_version

        autosave_url = reverse("knowledge_manage:autosave", args=[article.kb_no])
        save_url = reverse("knowledge_manage:save", args=[article.kb_no])
        working_payload = {
            "draft_id": str(draft.pk),
            "expected_lock_version": draft.lock_version,
            "title": "完整链自动保存标题",
            "summary": "完整链自动保存摘要",
            "applicable_scope": {"chain": "autosave"},
            "body_text": "完整链自动保存正文",
            "change_summary": "完整链自动保存",
        }
        autosave = self.client.post(
            autosave_url,
            data=json.dumps(working_payload, ensure_ascii=False),
            content_type="application/json",
        )
        self.assertEqual(autosave.status_code, 200)
        working_payload["expected_lock_version"] = autosave.json()["draft"]["lock_version"]
        manual = self.client.post(
            save_url,
            data=json.dumps(working_payload, ensure_ascii=False),
            content_type="application/json",
        )
        self.assertEqual(manual.status_code, 200)
        saved_id = manual.json()["saved"]["id"]
        saved = ArticleVersion.objects.get(pk=saved_id)
        saved_before = self.snapshot(saved)
        next_draft = ArticleVersion.objects.get(pk=manual.json()["draft"]["id"])

        history = self.client.get(reverse("knowledge_manage:history", args=[article.kb_no]))
        detail = self.client.get(
            reverse("knowledge_manage:history_detail", args=[article.kb_no, saved.pk])
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(detail.status_code, 200)

        restore = self.client.post(
            reverse("knowledge_manage:restore", args=[article.kb_no, saved.pk]),
            data={
                "draft_id": str(next_draft.pk),
                "expected_lock_version": str(next_draft.lock_version),
                "title": next_draft.title,
                "summary": next_draft.summary,
                "applicable_scope": json.dumps(next_draft.applicable_scope, ensure_ascii=False),
                "body_text": next_draft.body_plaintext,
                "change_summary": next_draft.change_summary,
            },
        )
        self.assertEqual(restore.status_code, 303)
        article.refresh_from_db()
        restored = article.latest_working_version
        self.assertEqual(restored.restored_from_version_id, saved.pk)
        self.assertEqual(self.snapshot(saved), saved_before)
        self.assertEqual(article.current_published_version_id, None)
        self.assertEqual(
            ArticleVersion.objects.filter(article=article, status=VersionStatus.DRAFT).count(),
            1,
        )

        after_restore = self.client.post(
            autosave_url,
            data=json.dumps(
                {
                    "draft_id": str(restored.pk),
                    "expected_lock_version": restored.lock_version,
                    "title": "完整链恢复后标题",
                    "summary": restored.summary,
                    "applicable_scope": restored.applicable_scope,
                    "body_text": restored.body_plaintext,
                    "change_summary": "完整链恢复后继续编辑",
                },
                ensure_ascii=False,
            ),
            content_type="application/json",
        )
        self.assertEqual(after_restore.status_code, 200)

    def test_known_restore_service_failures_have_safe_html_mapping(self):
        from apps.knowledge.services import ArticleVersionWriteError

        cases = (
            ("ARTICLE_VERSION_WRITE_PERMISSION_DENIED", 403),
            ("ARTICLE_VERSION_WRITE_INVALID_INPUT", 400),
            ("DRAFT_NOT_FOUND_OR_INACCESSIBLE", 404),
            ("RESTORE_SOURCE_INVALID", 404),
            ("RESTORE_SOURCE_WRONG_ARTICLE", 404),
            ("DRAFT_NOT_CURRENT", 409),
            ("DRAFT_CONFLICT", 409),
            ("INVALID_DRAFT_STATE", 409),
            ("VERSION_NUMBER_CONFLICT", 409),
            ("MODEL_CONSISTENCY_FAILED", 409),
            ("DATABASE_WRITE_FAILED", 503),
            ("UNKNOWN", 503),
        )
        for code, status in cases:
            with self.subTest(code=code):
                with mock.patch(
                    "apps.knowledge.manage_views.restore_article_version",
                    side_effect=ArticleVersionWriteError(code, "不应泄漏的内部详情"),
                ):
                    response = self.client.post(self.url, data=self.payload())
                self.assertEqual(response.status_code, status)
                self.assertEqual(response["Cache-Control"], "private, no-store")
                self.assertNotContains(
                    response,
                    "不应泄漏的内部详情",
                    status_code=status,
                )
