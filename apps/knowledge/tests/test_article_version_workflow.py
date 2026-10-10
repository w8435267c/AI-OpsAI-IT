"""Task 12D-05：ArticleVersion 完整 SQLite 工作流综合验收。"""

from datetime import timedelta

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import ROLE_EDITOR, SYSTEM_ROLE_BY_CODE
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
    ArticleVersionWriteError,
    autosave_draft,
    create_article,
    manual_save_draft,
    restore_article_version,
)
from apps.knowledge.version_readers import get_article_version_history
from apps.search.readers import search_employee_articles


class ArticleVersionWorkflowTests(TestCase):
    """串联 Task 12C/12D Service，验证跨阶段版本链不变量。"""

    version_snapshot_fields = (
        "id",
        "article_id",
        "version_no",
        "status",
        "lock_version",
        "title",
        "summary",
        "applicable_scope",
        "body",
        "body_plaintext",
        "change_summary",
        "created_by_id",
        "restored_from_version_id",
        "submitted_by_id",
        "submitted_at",
        "published_at",
        "created_at",
        "updated_at",
    )
    article_stable_fields = (
        "kb_no",
        "title",
        "space_id",
        "category_id",
        "article_type",
        "audience_policy",
        "owner_id",
        "article_status",
        "effective_at",
        "review_due_at",
        "current_published_version_id",
        "created_by_id",
        "created_at",
    )

    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0)
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)

        cls.editor = User.objects.create_user(username="task12d05-editor")
        cls.editor.groups.add(editor_group)
        cls.employee = User.objects.create_user(username="task12d05-employee")
        cls.space = KnowledgeSpace.objects.create(
            code="task12d05-space",
            name="Task 12D-05 空间",
            space_type="employee",
            owner=cls.editor,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="task12d05-category",
            name="Task 12D-05 分类",
        )

    def create_workflow_article(self, *, title, body_text):
        return create_article(
            actor=self.editor,
            space=self.space,
            category=self.category,
            article_type=ArticleType.GUIDE,
            title=title,
            summary=f"{title} 摘要",
            applicable_scope={"workflow": "task12d05"},
            body_text=body_text,
            change_summary="建立综合验收文章",
            review_due_at=timezone.now() + timedelta(days=180),
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )

    def version_snapshot(self, version):
        return ArticleVersion.objects.values(*self.version_snapshot_fields).get(pk=version.pk)

    def article_stable_snapshot(self, article):
        return Article.objects.values(*self.article_stable_fields).get(pk=article.pk)

    def assert_global_invariants(self, article, *, expected_review_count=0):
        article.refresh_from_db()
        versions = list(
            ArticleVersion.objects.filter(article=article)
            .select_related("restored_from_version")
            .order_by("version_no")
        )
        version_numbers = [version.version_no for version in versions]
        self.assertTrue(
            all(
                isinstance(number, int) and not isinstance(number, bool) and number > 0
                for number in version_numbers
            )
        )
        self.assertEqual(len(version_numbers), len(set(version_numbers)))
        self.assertEqual({version.article_id for version in versions}, {article.pk})

        drafts = [version for version in versions if version.status == VersionStatus.DRAFT]
        self.assertLessEqual(len(drafts), 1)
        if article.latest_working_version_id is None:
            self.assertEqual(drafts, [])
        else:
            self.assertEqual(len(drafts), 1)
            self.assertEqual(article.latest_working_version_id, drafts[0].pk)
            self.assertEqual(drafts[0].article_id, article.pk)

        if article.current_published_version_id is not None:
            article.current_published_version.refresh_from_db()
            self.assertEqual(article.current_published_version.article_id, article.pk)
            self.assertEqual(article.current_published_version.status, VersionStatus.PUBLISHED)

        for version in versions:
            if version.restored_from_version_id is not None:
                self.assertEqual(version.restored_from_version.article_id, article.pk)
            if version.status == VersionStatus.SAVED:
                self.assertNotEqual(version.pk, article.latest_working_version_id)
            if version.status in (VersionStatus.DRAFT, VersionStatus.SAVED):
                self.assertIsNone(version.submitted_by_id)
                self.assertIsNone(version.submitted_at)
                self.assertIsNone(version.published_at)

        self.assertEqual(
            ReviewRecord.objects.filter(article_version__article=article).count(),
            expected_review_count,
        )
        return versions

    def assert_employee_hidden(self, article, *search_terms):
        category_base = Article.objects.filter(category_id=article.category_id)
        self.assertFalse(employee_visible_articles(self.employee).filter(pk=article.pk).exists())
        self.assertFalse(
            employee_visible_articles(self.employee, base=category_base)
            .filter(pk=article.pk)
            .exists()
        )
        self.assertIsNone(get_employee_article_detail(self.employee, article.kb_no))
        for term in search_terms:
            with self.subTest(hidden_search_term=term):
                self.assertFalse(
                    search_employee_articles(self.employee, term).filter(pk=article.pk).exists()
                )

    def assert_employee_sees_published_only(self, article, *, work_marker):
        category_base = Article.objects.filter(category_id=article.category_id)
        self.assertTrue(employee_visible_articles(self.employee).filter(pk=article.pk).exists())
        self.assertTrue(
            employee_visible_articles(self.employee, base=category_base)
            .filter(pk=article.pk)
            .exists()
        )

        detail = get_employee_article_detail(self.employee, article.kb_no)
        self.assertIsNotNone(detail)
        self.assertEqual(detail.title, "Workflow-B Published 标题")
        self.assertEqual(detail.summary, "Workflow-B Published 摘要")
        self.assertEqual(detail.body_text, "Workflow-B Published 正文唯一关键词")
        self.assertEqual(detail.applicable_scope, {"published": True})
        self.assertTrue(
            search_employee_articles(self.employee, "Published 正文唯一关键词")
            .filter(pk=article.pk)
            .exists()
        )
        self.assertFalse(
            search_employee_articles(self.employee, work_marker).filter(pk=article.pk).exists()
        )

    def autosave_without_article_write(
        self,
        *,
        article,
        draft,
        expected_lock_version,
        title,
        body_text,
    ):
        article_before = Article.objects.values().get(pk=article.pk)
        result = autosave_draft(
            actor=self.editor,
            article=article,
            draft_id=draft.pk,
            expected_lock_version=expected_lock_version,
            title=title,
            summary=f"{title} 摘要",
            applicable_scope={"stage": title},
            body_text=body_text,
            change_summary=f"autosave {title}",
        )
        self.assertEqual(Article.objects.values().get(pk=article.pk), article_before)
        return result

    def assert_history_reader_is_read_only(self, article):
        article_before = Article.objects.values().get(pk=article.pk)
        versions_before = list(
            ArticleVersion.objects.filter(article=article).order_by("pk").values()
        )
        review_count_before = ReviewRecord.objects.count()

        history = list(get_article_version_history(actor=self.editor, article=article))

        self.assertEqual(Article.objects.values().get(pk=article.pk), article_before)
        self.assertEqual(
            list(ArticleVersion.objects.filter(article=article).order_by("pk").values()),
            versions_before,
        )
        self.assertEqual(ReviewRecord.objects.count(), review_count_before)
        return history

    def make_published_fixture(self):
        article, published = self.create_workflow_article(
            title="Workflow-B Published 标题",
            body_text="Workflow-B Published 正文唯一关键词",
        )
        published_at = timezone.now() - timedelta(hours=1)
        ArticleVersion.objects.filter(pk=published.pk).update(
            status=VersionStatus.PUBLISHED,
            title="Workflow-B Published 标题",
            summary="Workflow-B Published 摘要",
            applicable_scope={"published": True},
            body={
                "format": "opsai.plaintext/1",
                "text": "Workflow-B Published 正文唯一关键词",
            },
            body_plaintext="Workflow-B Published 正文唯一关键词",
            change_summary="测试夹具中的既有正式版本",
            submitted_by=self.editor,
            submitted_at=published_at,
            published_at=published_at,
        )
        published.refresh_from_db()
        draft = ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status=VersionStatus.DRAFT,
            lock_version=1,
            title="Workflow-B v2 初始工作关键词",
            summary="Workflow-B v2 初始摘要",
            applicable_scope={"working": 2},
            body={"format": "opsai.plaintext/1", "text": "Workflow-B v2 初始正文"},
            body_plaintext="Workflow-B v2 初始正文",
            change_summary="测试夹具中的初始工作版本",
            created_by=self.editor,
        )
        Article.objects.filter(pk=article.pk).update(
            current_published_version=published,
            latest_working_version=draft,
        )
        article.refresh_from_db()
        return article, published, draft

    def test_unpublished_article_complete_workflow_preserves_chain_and_employee_isolation(self):
        article, draft_v1 = self.create_workflow_article(
            title="Workflow-A 初始标题",
            body_text="Workflow-A 初始正文",
        )
        stable_article = self.article_stable_snapshot(article)
        self.assert_employee_hidden(article, "Workflow-A 初始标题")
        self.assert_global_invariants(article)

        draft_v1 = self.autosave_without_article_write(
            article=article,
            draft=draft_v1,
            expected_lock_version=1,
            title="Workflow-A Draft-A",
            body_text="Workflow-A Draft-A 正文",
        )
        saved_v1, draft_v2 = manual_save_draft(
            actor=self.editor,
            article=article,
            draft_id=draft_v1.pk,
            expected_lock_version=2,
            title="Workflow-A Saved-A",
            summary="Workflow-A Saved-A 摘要",
            applicable_scope={"stage": "saved-a"},
            body_text="Workflow-A Saved-A 正文唯一关键词",
            change_summary="第一次手动保存",
        )
        saved_v1_snapshot = self.version_snapshot(saved_v1)
        self.assert_employee_hidden(article, "Saved-A 正文唯一关键词")
        self.assert_global_invariants(article)

        draft_v2 = self.autosave_without_article_write(
            article=article,
            draft=draft_v2,
            expected_lock_version=1,
            title="Workflow-A Draft-B",
            body_text="Workflow-A Draft-B 正文",
        )
        saved_v2, draft_v3 = manual_save_draft(
            actor=self.editor,
            article=article,
            draft_id=draft_v2.pk,
            expected_lock_version=2,
            title="Workflow-A Saved-B",
            summary="Workflow-A Saved-B 摘要",
            applicable_scope={"stage": "saved-b"},
            body_text="Workflow-A Saved-B 正文唯一关键词",
            change_summary="第二次手动保存",
        )
        saved_v2_snapshot = self.version_snapshot(saved_v2)
        self.assertEqual(self.version_snapshot(saved_v1), saved_v1_snapshot)

        restored_v4 = restore_article_version(
            actor=self.editor,
            article=article,
            source_version_id=saved_v1.pk,
            draft_id=draft_v3.pk,
            expected_lock_version=1,
            current_title="Workflow-A Current-Before-Restore",
            current_summary="Workflow-A restore 前页面摘要",
            current_applicable_scope={"stage": "before-restore"},
            current_body_text="Workflow-A restore 前页面正文唯一关键词",
            current_change_summary="恢复前冻结页面最新内容",
        )
        draft_v3.refresh_from_db()
        saved_v3_snapshot = self.version_snapshot(draft_v3)
        self.assertEqual(restored_v4.restored_from_version_id, saved_v1.pk)
        for field in ("title", "summary", "applicable_scope", "body", "body_plaintext"):
            with self.subTest(restored_field=field):
                self.assertEqual(getattr(restored_v4, field), getattr(saved_v1, field))
        self.assert_employee_hidden(article, "restore 前页面正文唯一关键词")

        restored_v4 = self.autosave_without_article_write(
            article=article,
            draft=restored_v4,
            expected_lock_version=1,
            title="Workflow-A Restored-Then-Edited",
            body_text="Workflow-A Restored-Then-Edited 正文唯一关键词",
        )
        self.assertEqual(restored_v4.restored_from_version_id, saved_v1.pk)
        self.assert_employee_hidden(article, "Restored-Then-Edited 正文唯一关键词")

        article.refresh_from_db()
        versions = self.assert_global_invariants(article)
        self.assertEqual(
            [(version.version_no, version.status) for version in versions],
            [
                (1, VersionStatus.SAVED),
                (2, VersionStatus.SAVED),
                (3, VersionStatus.SAVED),
                (4, VersionStatus.DRAFT),
            ],
        )
        self.assertEqual(article.latest_working_version_id, restored_v4.pk)
        self.assertIsNone(article.current_published_version_id)
        self.assertEqual(self.article_stable_snapshot(article), stable_article)
        self.assertEqual(self.version_snapshot(saved_v1), saved_v1_snapshot)
        self.assertEqual(self.version_snapshot(saved_v2), saved_v2_snapshot)
        self.assertEqual(self.version_snapshot(draft_v3), saved_v3_snapshot)

        other_article, other_draft = self.create_workflow_article(
            title="Workflow-A Reader 隔离文章",
            body_text="Workflow-A Reader 隔离正文",
        )
        history = self.assert_history_reader_is_read_only(article)
        self.assertEqual([version.version_no for version in history], [4, 3, 2, 1])
        self.assertEqual({version.article_id for version in history}, {article.pk})
        self.assertNotIn(other_draft.pk, {version.pk for version in history})
        self.assertNotEqual(other_article.pk, article.pk)

    def test_published_article_workflow_never_changes_employee_baseline(self):
        article, published_v1, draft_v2 = self.make_published_fixture()
        stable_article = self.article_stable_snapshot(article)
        published_snapshot = self.version_snapshot(published_v1)
        self.assert_employee_sees_published_only(
            article,
            work_marker="v2 初始工作关键词",
        )

        draft_v2 = self.autosave_without_article_write(
            article=article,
            draft=draft_v2,
            expected_lock_version=1,
            title="Workflow-B v2 autosave 工作关键词",
            body_text="Workflow-B v2 autosave 正文关键词",
        )
        self.assert_employee_sees_published_only(article, work_marker="v2 autosave 正文关键词")
        saved_v2, draft_v3 = manual_save_draft(
            actor=self.editor,
            article=article,
            draft_id=draft_v2.pk,
            expected_lock_version=2,
            title="Workflow-B v2 SAVED 工作关键词",
            summary="Workflow-B v2 SAVED 摘要",
            applicable_scope={"working": "saved-v2"},
            body_text="Workflow-B v2 SAVED 正文关键词",
            change_summary="保存工作版本 v2",
        )
        saved_v2_snapshot = self.version_snapshot(saved_v2)
        self.assert_employee_sees_published_only(article, work_marker="v2 SAVED 正文关键词")

        draft_v3 = self.autosave_without_article_write(
            article=article,
            draft=draft_v3,
            expected_lock_version=1,
            title="Workflow-B v3 autosave 工作关键词",
            body_text="Workflow-B v3 autosave 正文关键词",
        )
        saved_v3, draft_v4 = manual_save_draft(
            actor=self.editor,
            article=article,
            draft_id=draft_v3.pk,
            expected_lock_version=2,
            title="Workflow-B v3 SAVED 工作关键词",
            summary="Workflow-B v3 SAVED 摘要",
            applicable_scope={"working": "saved-v3"},
            body_text="Workflow-B v3 SAVED 正文关键词",
            change_summary="保存工作版本 v3",
        )
        saved_v3_snapshot = self.version_snapshot(saved_v3)
        self.assert_employee_sees_published_only(article, work_marker="v3 SAVED 正文关键词")

        restored_v5 = restore_article_version(
            actor=self.editor,
            article=article,
            source_version_id=published_v1.pk,
            draft_id=draft_v4.pk,
            expected_lock_version=1,
            current_title="Workflow-B v4 restore 前工作关键词",
            current_summary="Workflow-B v4 restore 前摘要",
            current_applicable_scope={"working": "before-restore"},
            current_body_text="Workflow-B v4 restore 前正文关键词",
            current_change_summary="冻结 v4 后恢复正式历史",
        )
        draft_v4.refresh_from_db()
        saved_v4_snapshot = self.version_snapshot(draft_v4)
        self.assertEqual(restored_v5.restored_from_version_id, published_v1.pk)
        self.assert_employee_sees_published_only(article, work_marker="v4 restore 前正文关键词")

        restored_v5 = self.autosave_without_article_write(
            article=article,
            draft=restored_v5,
            expected_lock_version=1,
            title="Workflow-B v5 恢复后工作关键词",
            body_text="Workflow-B v5 恢复后正文关键词",
        )
        self.assertEqual(restored_v5.restored_from_version_id, published_v1.pk)
        self.assert_employee_sees_published_only(article, work_marker="v5 恢复后正文关键词")

        article.refresh_from_db()
        versions = self.assert_global_invariants(article)
        self.assertEqual(
            [(version.version_no, version.status) for version in versions],
            [
                (1, VersionStatus.PUBLISHED),
                (2, VersionStatus.SAVED),
                (3, VersionStatus.SAVED),
                (4, VersionStatus.SAVED),
                (5, VersionStatus.DRAFT),
            ],
        )
        self.assertEqual(article.latest_working_version_id, restored_v5.pk)
        self.assertEqual(article.current_published_version_id, published_v1.pk)
        self.assertEqual(self.article_stable_snapshot(article), stable_article)
        self.assertEqual(self.version_snapshot(published_v1), published_snapshot)
        self.assertEqual(self.version_snapshot(saved_v2), saved_v2_snapshot)
        self.assertEqual(self.version_snapshot(saved_v3), saved_v3_snapshot)
        self.assertEqual(self.version_snapshot(draft_v4), saved_v4_snapshot)

        history = self.assert_history_reader_is_read_only(article)
        self.assertEqual([version.version_no for version in history], [5, 4, 3, 2, 1])
        self.assertEqual(
            [version.status for version in history],
            [
                VersionStatus.DRAFT,
                VersionStatus.SAVED,
                VersionStatus.SAVED,
                VersionStatus.SAVED,
                VersionStatus.PUBLISHED,
            ],
        )
        self.assertEqual(history[0].restored_from_version_id, published_v1.pk)

    def test_stale_window_manual_save_cannot_overwrite_successful_autosave(self):
        article, draft = self.create_workflow_article(
            title="Workflow-Stale 初始标题",
            body_text="Workflow-Stale 初始正文",
        )
        draft_id = draft.pk
        window_lock_version = draft.lock_version
        version_count = ArticleVersion.objects.filter(article=article).count()

        latest = self.autosave_without_article_write(
            article=article,
            draft=draft,
            expected_lock_version=window_lock_version,
            title="Workflow-Stale 窗口A成功内容",
            body_text="Workflow-Stale 窗口A成功正文",
        )
        article_after_autosave = Article.objects.values().get(pk=article.pk)

        with self.assertRaises(ArticleVersionWriteError) as caught:
            manual_save_draft(
                actor=self.editor,
                article=article,
                draft_id=draft_id,
                expected_lock_version=window_lock_version,
                title="Workflow-Stale 窗口B过期内容",
                summary="Workflow-Stale 窗口B过期摘要",
                applicable_scope={"window": "stale-b"},
                body_text="Workflow-Stale 窗口B过期正文",
                change_summary="过期窗口不得覆盖",
            )

        self.assertEqual(caught.exception.code, "DRAFT_CONFLICT")
        latest.refresh_from_db()
        article.refresh_from_db()
        self.assertEqual(latest.pk, draft_id)
        self.assertEqual(latest.status, VersionStatus.DRAFT)
        self.assertEqual(latest.lock_version, 2)
        self.assertEqual(latest.title, "Workflow-Stale 窗口A成功内容")
        self.assertEqual(latest.body_plaintext, "Workflow-Stale 窗口A成功正文")
        self.assertEqual(Article.objects.values().get(pk=article.pk), article_after_autosave)
        self.assertEqual(ArticleVersion.objects.filter(article=article).count(), version_count)
        self.assertFalse(
            ArticleVersion.objects.filter(article=article, status=VersionStatus.SAVED).exists()
        )
        self.assertEqual(article.latest_working_version_id, latest.pk)
        self.assert_global_invariants(article)

    def test_restore_lineage_survives_autosave_and_later_manual_freeze(self):
        article, draft_v1 = self.create_workflow_article(
            title="Workflow-Lineage 初始标题",
            body_text="Workflow-Lineage 初始正文",
        )
        source_v1, draft_v2 = manual_save_draft(
            actor=self.editor,
            article=article,
            draft_id=draft_v1.pk,
            expected_lock_version=1,
            title="Workflow-Lineage 恢复来源",
            summary="Workflow-Lineage 恢复来源摘要",
            applicable_scope={"lineage": "source"},
            body_text="Workflow-Lineage 恢复来源正文",
            change_summary="冻结恢复来源",
        )
        source_snapshot = self.version_snapshot(source_v1)

        restored_v3 = restore_article_version(
            actor=self.editor,
            article=article,
            source_version_id=source_v1.pk,
            draft_id=draft_v2.pk,
            expected_lock_version=1,
            current_title="Workflow-Lineage restore 前标题",
            current_summary="Workflow-Lineage restore 前摘要",
            current_applicable_scope={"lineage": "before-restore"},
            current_body_text="Workflow-Lineage restore 前正文",
            current_change_summary="恢复前冻结 v2",
        )
        self.assertEqual(restored_v3.restored_from_version_id, source_v1.pk)

        restored_v3 = self.autosave_without_article_write(
            article=article,
            draft=restored_v3,
            expected_lock_version=1,
            title="Workflow-Lineage 恢复后继续编辑",
            body_text="Workflow-Lineage 恢复后继续编辑正文",
        )
        self.assertEqual(restored_v3.restored_from_version_id, source_v1.pk)

        saved_v3, draft_v4 = manual_save_draft(
            actor=self.editor,
            article=article,
            draft_id=restored_v3.pk,
            expected_lock_version=2,
            title="Workflow-Lineage 恢复稿最终保存",
            summary="Workflow-Lineage 恢复稿最终摘要",
            applicable_scope={"lineage": "saved-after-restore"},
            body_text="Workflow-Lineage 恢复稿最终正文",
            change_summary="冻结恢复后的草稿",
        )
        self.assertEqual(saved_v3.status, VersionStatus.SAVED)
        self.assertEqual(saved_v3.restored_from_version_id, source_v1.pk)
        self.assertEqual(self.version_snapshot(source_v1), source_snapshot)
        self.assertEqual(draft_v4.status, VersionStatus.DRAFT)
        self.assertEqual(draft_v4.version_no, 4)
        self.assertIsNone(draft_v4.restored_from_version_id)
        self.assert_global_invariants(article)
        self.assert_employee_hidden(article, "恢复稿最终正文")
