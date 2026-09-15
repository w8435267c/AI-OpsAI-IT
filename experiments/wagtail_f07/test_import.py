"""单篇合成数据顺序幂等及事务回滚；不验证并发或生产迁移。"""

import json
from datetime import datetime, timedelta
from datetime import timezone as fixed_timezone
from unittest.mock import patch
from uuid import UUID
from zoneinfo import ZoneInfo

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from wagtail.models import Revision, TaskState, WorkflowState

from apps.accounts.models import User
from apps.knowledge.models import Article, ArticleAudience, ArticleVersion, ReviewRecord
from apps.knowledge.tests.test_models import make_version
from apps.knowledge.tests.test_selectors import _add_audience, _mk_article, _mk_user
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.tests import legacy_snapshot, version_snapshot
from experiments.wagtail_f05a.models import TaskSubmission
from experiments.wagtail_f06.readers import get_employee_article_detail

from .conversion import FORMAT, ConversionError, convert_version, restore_version
from .import_service import ImportRejected, import_article
from .models import ImportedVersionSource
from .source_codec import SOURCE_FORMAT, deserialize_source, serialize_source


def current_snapshot():
    return (
        legacy_snapshot(),
        version_snapshot(),
        {
            model._meta.label: list(model.objects.order_by("pk").values())
            for model in (
                ImportedVersionSource,
                TaskState,
                WorkflowState,
                TaskSubmission,
                ArticleAudience,
            )
        },
    )


class FirstImportTests(TestCase):
    def setUp(self):
        self.author = _mk_user()
        self.submitter = _mk_user()
        self.reviewer = _mk_user()
        self.importer = _mk_user()
        self.employee = _mk_user()
        self.article = _mk_article(policy="all_employees", owner=self.author)
        stamp = timezone.now() - timedelta(days=40)
        self.published = make_version(
            article=self.article,
            version_no=1,
            status="published",
            created_by=self.author,
            submitted_by=self.submitter,
            submitted_at=stamp + timedelta(hours=1),
            published_at=stamp + timedelta(hours=3),
            title="旧正式版",
            summary="旧摘要",
            body={"嵌套": [True, 1, 1.0, None, '引号"\\与换行\n']},
            applicable_scope={"format": SOURCE_FORMAT, "value": ["uuid", "普通业务字符串"]},
        )
        self.draft = make_version(
            article=self.article,
            version_no=2,
            created_by=self.author,
            title="较新草稿",
            summary="草稿摘要",
            body=["草稿", {"状态": False}],
            body_plaintext="草稿纯文本",
            change_summary="新的版本说明",
        )
        self.review = ReviewRecord.objects.create(
            article_version=self.published,
            reviewer=self.reviewer,
            review_type="content_review",
            decision="approved",
            comment="历史来源",
        )
        ArticleVersion.objects.filter(pk=self.published.pk).update(
            created_at=stamp, updated_at=stamp + timedelta(hours=3)
        )
        ArticleVersion.objects.filter(pk=self.draft.pk).update(
            created_at=stamp + timedelta(days=1), updated_at=stamp + timedelta(days=1)
        )
        ReviewRecord.objects.filter(pk=self.review.pk).update(
            reviewed_at=stamp + timedelta(hours=2)
        )
        Article.objects.filter(pk=self.article.pk).update(
            current_published_version=self.published, latest_working_version=self.draft
        )
        _add_audience(self.article, "user", "deny", user=self.reviewer)
        self.old = legacy_snapshot()
        self.audience = list(ArticleAudience.objects.values())
        self.workflow_counts = (
            TaskState.objects.count(),
            WorkflowState.objects.count(),
            TaskSubmission.objects.count(),
        )

    def tearDown(self):
        # 拒绝用例会故意改坏旧指针，测试负责更新预期；服务不允许改任何旧行。
        self.assertEqual(legacy_snapshot(), self.old)
        self.assertEqual(list(ArticleAudience.objects.values()), self.audience)
        self.assertEqual(
            (
                TaskState.objects.count(),
                WorkflowState.objects.count(),
                TaskSubmission.objects.count(),
            ),
            self.workflow_counts,
        )

    def test_first_import_has_two_unpublished_revisions_and_sources(self):
        before = Revision.objects.count()
        start = timezone.now()
        result = import_article(self.article.pk, self.importer)
        end = timezone.now()
        content = KnowledgeContent.objects.get(pk=result.content_id)
        self.assertEqual(KnowledgeContent.objects.count(), 1)
        self.assertEqual(Revision.objects.count(), before + 2)
        self.assertEqual(ImportedVersionSource.objects.count(), 2)
        self.assertEqual(content.article_id, self.article.pk)
        self.assertEqual(content.latest_revision_id, result.revision_ids[1])
        self.assertEqual(content.title, "较新草稿")
        self.assertTrue(content.has_unpublished_changes)
        self.assertFalse(content.live)
        self.assertIsNone(content.live_revision_id)
        self.assertIsNone(content.first_published_at)
        self.assertIsNone(content.last_published_at)
        self.assertIsNone(get_employee_article_detail(self.employee, self.article.pk))
        for old, revision_id in zip((self.published, self.draft), result.revision_ids, strict=True):
            source = ImportedVersionSource.objects.get(source_version_id=old.pk)
            revision = Revision.objects.get(pk=revision_id)
            version = ArticleVersion.objects.values().get(pk=old.pk)
            reviews = list(
                ReviewRecord.objects.filter(article_version_id=old.pk).order_by("pk").values()
            )
            decoded = deserialize_source(source.source_data)
            self.assertEqual(decoded, convert_version(version, reviews))
            restored, restored_reviews = restore_version(decoded)
            self.assertEqual(restored, version)
            self.assertEqual(restored_reviews, reviews)
            self.assertIs(type(restored["id"]), UUID)
            self.assertIs(type(restored["article_id"]), UUID)
            self.assertIs(type(restored["created_at"]), datetime)
            self.assertEqual(restored["created_at"].isoformat(), version["created_at"].isoformat())
            self.assertEqual(source.content_id, content.pk)
            self.assertEqual(source.revision_id, revision_id)
            self.assertEqual(source.conversion_format, FORMAT)
            self.assertEqual(source.imported_by_id, self.importer.pk)
            self.assertTrue(start <= source.imported_at <= end)
            self.assertEqual(revision.user_id, self.importer.pk)
            self.assertNotEqual(revision.user_id, restored["created_by_id"])
            self.assertTrue(start <= revision.created_at <= end)
            self.assertEqual(revision.object_id, str(content.pk))
            self.assertEqual(revision.content_type_id, content.get_content_type().pk)
            self.assertEqual(revision.base_content_type_id, content.get_base_content_type().pk)
            for field in ("title", "summary", "body"):
                self.assertEqual(revision.content[field], decoded["content"][field])
            self.assertIsNone(revision.approved_go_live_at)

    def test_cross_article_pointer_refused_without_writes(self):
        other = _mk_article(policy="all_employees")
        foreign = make_version(article=other, version_no=2)
        Article.objects.filter(pk=self.article.pk).update(latest_working_version=foreign)
        self.old = legacy_snapshot()
        before = current_snapshot()
        with self.assertRaises(ImportRejected):
            import_article(self.article.pk, self.importer)
        self.assertEqual(current_snapshot(), before)

    def test_existing_content_refused_without_writes(self):
        KnowledgeContent.objects.create(article=self.article, title="已存在", body="原内容")
        before = current_snapshot()
        with self.assertRaisesRegex(ImportRejected, "冲突"):
            import_article(self.article.pk, self.importer)
        self.assertEqual(current_snapshot(), before)

    def test_existing_mapping_refused_even_without_target_content(self):
        other = _mk_article(policy="all_employees")
        content = KnowledgeContent.objects.create(article=other, title="其他内容", body="原内容")
        revision = content.save_revision(user=self.importer)
        ImportedVersionSource.objects.create(
            source_version=self.published,
            content=content,
            revision=revision,
            conversion_format=FORMAT,
            source_data={},
            imported_by=self.importer,
        )
        self.old = legacy_snapshot()
        before = current_snapshot()
        with self.assertRaisesRegex(ImportRejected, "冲突"):
            import_article(self.article.pk, self.importer)
        self.assertEqual(current_snapshot(), before)

    def test_unique_source_and_revision_constraints(self):
        import_article(self.article.pk, self.importer)
        one, two = ImportedVersionSource.objects.order_by("pk")
        for row, fields in (
            (two, {"source_version_id": one.source_version_id}),
            (two, {"revision_id": one.revision_id}),
        ):
            with self.assertRaises(IntegrityError), transaction.atomic():
                ImportedVersionSource.objects.filter(pk=row.pk).update(**fields)

    def test_invalid_actor_and_invalid_pair_refused_before_creation(self):
        User.objects.filter(pk=self.importer.pk).update(account_status="disabled")
        before = current_snapshot()
        with self.assertRaises(ImportRejected):
            import_article(self.article.pk, self.importer)
        self.assertEqual(current_snapshot(), before)
        User.objects.filter(pk=self.importer.pk).update(account_status="active")
        Article.objects.filter(pk=self.article.pk).update(current_published_version=None)
        self.old = legacy_snapshot()
        before = current_snapshot()
        with self.assertRaises(ImportRejected):
            import_article(self.article.pk, self.importer)
        self.assertEqual(current_snapshot(), before)

    def test_experimental_migration_actually_applied(self):
        executor = MigrationExecutor(connection)
        self.assertIn(("fusion_f07", "0001_initial"), executor.loader.applied_migrations)
        self.assertEqual(executor.migration_plan(executor.loader.graph.leaf_nodes()), [])

    def test_identical_repeat_returns_mapping_without_writes(self):
        first = import_article(self.article.pk, self.importer)
        before = current_snapshot()
        # 另一个有效执行人也不能覆盖首次导入身份及时间。
        second = import_article(str(self.article.pk), self.employee)
        self.assertEqual(second, first)
        self.assertEqual(current_snapshot(), before)

    def test_changed_source_or_pointer_conflicts_without_writes(self):
        import_article(self.article.pk, self.importer)
        changes = (
            (ArticleVersion, self.published.pk, {"title": "源标题已变化"}),
            (ArticleVersion, self.draft.pk, {"applicable_scope": {"changed": True}}),
            (ArticleVersion, self.draft.pk, {"updated_at": timezone.now()}),
            (ReviewRecord, self.review.pk, {"comment": "审核来源已变化"}),
            (Article, self.article.pk, {"current_published_version_id": None}),
            (Article, self.article.pk, {"latest_working_version_id": self.published.pk}),
        )
        for model, pk, fields in changes:
            with self.subTest(fields=fields), transaction.atomic():
                model.objects.filter(pk=pk).update(**fields)
                before = current_snapshot()
                with self.assertRaisesRegex(ImportRejected, "冲突"):
                    import_article(self.article.pk, self.importer)
                self.assertEqual(current_snapshot(), before)
                transaction.set_rollback(True)

    def test_partial_mapping_conflicts_without_repair(self):
        import_article(self.article.pk, self.importer)
        ImportedVersionSource.objects.filter(source_version=self.draft).delete()
        before = current_snapshot()
        with self.assertRaisesRegex(ImportRejected, "冲突"):
            import_article(self.article.pk, self.importer)
        self.assertEqual(current_snapshot(), before)

    def test_corrupted_associations_snapshots_and_revisions_conflict(self):
        result = import_article(self.article.pk, self.importer)
        other = _mk_article(policy="all_employees")
        other_version = make_version(article=other)
        foreign = KnowledgeContent.objects.create(article=other, title="其他", body="其他")
        foreign_revision = foreign.save_revision(user=self.importer)
        self.old = legacy_snapshot()
        row = ImportedVersionSource.objects.get(source_version=self.published)
        revision = Revision.objects.get(pk=result.revision_ids[0])
        data = dict(revision.content)
        mutations = (
            (ImportedVersionSource, row.pk, {"content_id": foreign.pk}),
            (ImportedVersionSource, row.pk, {"revision_id": foreign_revision.pk}),
            (ImportedVersionSource, row.pk, {"source_version_id": other_version.pk}),
            (ImportedVersionSource, row.pk, {"conversion_format": "unknown"}),
            (ImportedVersionSource, row.pk, {"source_data": {}}),
            (ImportedVersionSource, row.pk, {"imported_by_id": self.employee.pk}),
            (Revision, revision.pk, {"object_id": str(foreign.pk)}),
            (
                Revision,
                revision.pk,
                {"content_type_id": ContentType.objects.get_for_model(Article).pk},
            ),
            (
                Revision,
                revision.pk,
                {"base_content_type_id": ContentType.objects.get_for_model(Article).pk},
            ),
            (Revision, revision.pk, {"content": {**data, "article": str(other.pk)}}),
            (Revision, revision.pk, {"content": {**data, "pk": foreign.pk}}),
            (Revision, revision.pk, {"content": {**data, "title": "被改写的修订"}}),
        )
        for model, pk, fields in mutations:
            with self.subTest(fields=fields), transaction.atomic():
                model.objects.filter(pk=pk).update(**fields)
                before = current_snapshot()
                with self.assertRaisesRegex(ImportRejected, "冲突"):
                    import_article(self.article.pk, self.importer)
                self.assertEqual(current_snapshot(), before)
                transaction.set_rollback(True)

    def test_later_edit_is_not_overwritten_by_repeat(self):
        first = import_article(self.article.pk, self.importer)
        content = KnowledgeContent.objects.get(pk=first.content_id)
        content.title, content.summary, content.body = "后续编辑", "新摘要", "新正文"
        content.save()
        new_revision = content.save_revision(user=self.employee, log_action=True)
        before = current_snapshot()
        self.assertEqual(import_article(self.article.pk, self.importer), first)
        self.assertEqual(current_snapshot(), before)
        content.refresh_from_db()
        self.assertEqual(content.latest_revision_id, new_revision.pk)
        self.assertEqual(
            (content.title, content.summary, content.body), ("后续编辑", "新摘要", "新正文")
        )

    def test_invalid_actor_still_refused_on_repeat(self):
        import_article(self.article.pk, self.importer)
        for fields in ({"is_active": False}, {"account_status": "disabled"}):
            with self.subTest(fields=fields), transaction.atomic():
                User.objects.filter(pk=self.importer.pk).update(**fields)
                before = current_snapshot()
                with self.assertRaises(ImportRejected):
                    import_article(self.article.pk, self.importer)
                self.assertEqual(current_snapshot(), before)
                transaction.set_rollback(True)

    def _assert_fault_rollback_and_retry(self, stage):
        before = current_snapshot()
        create = ImportedVersionSource.objects.create
        calls = []

        def fail_at_boundary(**kwargs):
            calls.append(kwargs["source_version_id"])
            if stage == 1:
                create(**kwargs)
                self.assertEqual(Revision.objects.count(), 1)
                self.assertEqual(ImportedVersionSource.objects.count(), 1)
                raise RuntimeError("实验注入：第一修订及来源已保存")
            if len(calls) == 2:
                self.assertEqual(Revision.objects.count(), 2)
                self.assertEqual(ImportedVersionSource.objects.count(), 1)
                raise RuntimeError("实验注入：第二修订已保存，来源尚未保存")
            return create(**kwargs)

        with patch.object(ImportedVersionSource.objects, "create", side_effect=fail_at_boundary):
            with self.assertRaisesRegex(RuntimeError, "实验注入"):
                import_article(self.article.pk, self.importer)
        self.assertEqual(len(calls), stage)
        self.assertEqual(current_snapshot(), before)
        result = import_article(self.article.pk, self.importer)
        self.assertEqual(KnowledgeContent.objects.count(), 1)
        self.assertEqual(Revision.objects.count(), 2)
        self.assertEqual(ImportedVersionSource.objects.count(), 2)
        self.assertEqual(
            tuple(
                ImportedVersionSource.objects.get(source_version=v).revision_id
                for v in (self.published, self.draft)
            ),
            result.revision_ids,
        )
        content = KnowledgeContent.objects.get(pk=result.content_id)
        self.assertFalse(content.live)
        self.assertIsNone(content.live_revision_id)
        self.assertIsNone(get_employee_article_detail(self.employee, self.article.pk))

    def test_rollback_after_first_revision_and_source_then_retry(self):
        self._assert_fault_rollback_and_retry(1)

    def test_rollback_after_second_revision_before_source_then_retry(self):
        self._assert_fault_rollback_and_retry(2)


class SourceCodecTests(SimpleTestCase):
    def test_tags_cannot_collide_and_temporal_types_survive_json(self):
        for tz in (fixed_timezone(timedelta(hours=8), "original zone"), ZoneInfo("UTC")):
            value = {
                "format": SOURCE_FORMAT,
                "value": ["uuid", "not a uuid"],
                "original": UUID(int=9),
                "time": datetime(2024, 1, 2, 3, 4, 5, 6789, tzinfo=tz, fold=1),
                "nested": [None, True, False, 1, 1.0, -0.0],
            }
            restored = deserialize_source(json.loads(json.dumps(serialize_source(value))))
            self.assertEqual(restored, value)
            self.assertIs(type(restored["original"]), UUID)
            self.assertIs(type(restored["time"]), datetime)
            self.assertEqual(restored["time"].isoformat(), value["time"].isoformat())
            self.assertEqual(restored["time"].fold, 1)
            self.assertIs(type(restored["time"].tzinfo), type(tz))
            self.assertEqual(restored["time"].tzname(), value["time"].tzname())

    def test_unknown_or_malformed_encoding_rejected(self):
        for value in (
            {"format": "unknown", "value": ["scalar", None]},
            {"format": SOURCE_FORMAT, "value": ["unknown", 1]},
            {
                "format": SOURCE_FORMAT,
                "value": ["dict", [["a", ["scalar", 1]], ["a", ["scalar", 2]]]],
            },
            {"format": SOURCE_FORMAT, "value": ["uuid", "bad"]},
        ):
            with self.assertRaises(ConversionError):
                deserialize_source(value)
