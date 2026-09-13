"""所有关键结果重新查询数据库；只使用合成业务记录。"""

from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from wagtail.models import ModelLogEntry, Revision

from apps.accounts.models import User
from apps.knowledge.models import Article, ArticleVersion, ReviewRecord
from apps.knowledge.tests.test_models import make_article, make_published_version, make_version

from .models import KnowledgeContent
from .versions import publish_for_test, read_live, restore_draft


def legacy_snapshot():
    return {
        m._meta.label: list(m.objects.order_by("pk").values())
        for m in (Article, ArticleVersion, ReviewRecord)
    }


def version_snapshot():
    return {
        m._meta.label: list(m.objects.order_by("pk").values())
        for m in (KnowledgeContent, Revision, ModelLogEntry)
    }


class VersionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="f04a_publisher")
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="fusion_f04a", codename="publish_knowledgecontent"
            )
        )
        self.article = make_article(owner=self.user)
        self.other = make_article(kb_no="KB-000002", owner=self.user)
        published = make_published_version(article=self.article)
        working = make_version(article=self.article, version_no=2)
        reviewer = User.objects.create_user(username="f04a_legacy_reviewer")
        ReviewRecord.objects.create(
            article_version=published,
            reviewer=reviewer,
            review_type="content_review",
            decision="approved",
        )
        Article.objects.filter(pk=self.article.pk).update(
            current_published_version=published,
            latest_working_version=working,
        )
        self.legacy = legacy_snapshot()
        self.content = KnowledgeContent.objects.create(
            article=self.article, title="V1", summary="摘要1", body="正文1"
        )
        self.pk = self.content.pk

    def tearDown(self):
        self.assertEqual(legacy_snapshot(), self.legacy)

    def draft(self, title):
        obj = KnowledgeContent.objects.get(pk=self.pk)
        obj.title, obj.summary, obj.body = title, "摘要" + title, "正文" + title
        return obj.save_revision(user=self.user)

    def publish(self, revision):
        publish_for_test(self.pk, revision.pk, self.user)

    def test_migration_applied_and_constraints(self):
        executor = MigrationExecutor(connection)
        self.assertEqual(executor.migration_plan(executor.loader.graph.leaf_nodes()), [])
        self.assertIn(("fusion_f04a", "0001_initial"), executor.loader.applied_migrations)
        connection.check_constraints()

    def test_one_to_one_database_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            KnowledgeContent.objects.create(article=self.article, title="duplicate", body="x")
        self.assertEqual(KnowledgeContent.objects.filter(article=self.article).count(), 1)

    def test_new_object_is_not_live(self):
        obj = KnowledgeContent.objects.get(pk=self.pk)
        self.assertFalse(obj.live)
        self.assertIsNone(obj.live_revision_id)
        self.assertIsNone(read_live(self.pk))

    def test_first_draft_creates_revision_without_publish(self):
        revision = self.draft("V1")
        obj = KnowledgeContent.objects.get(pk=self.pk)
        self.assertEqual(obj.latest_revision_id, revision.pk)
        self.assertEqual(obj.revisions.count(), 1)
        self.assertFalse(obj.live)
        self.assertIsNone(read_live(self.pk))
        self.assertEqual(Revision.objects.get(pk=revision.pk).as_object().body, "正文V1")

    def test_v1_publish(self):
        revision = self.draft("V1")
        self.publish(revision)
        self.assertEqual(read_live(self.pk)["body"], "正文V1")
        self.assertEqual(KnowledgeContent.objects.get(pk=self.pk).live_revision_id, revision.pk)

    def test_v2_draft_isolated_from_live(self):
        self.publish(self.draft("V1"))
        revision = self.draft("V2")
        obj = KnowledgeContent.objects.get(pk=self.pk)
        self.assertEqual(obj.body, "正文V1")
        self.assertEqual(obj.latest_revision_id, revision.pk)
        self.assertEqual(obj.get_latest_revision_as_object().body, "正文V2")
        self.assertEqual(read_live(self.pk)["body"], "正文V1")

    def test_v2_publish_switches_live(self):
        self.publish(self.draft("V1"))
        revision = self.draft("V2")
        self.publish(revision)
        self.assertEqual(read_live(self.pk)["body"], "正文V2")
        self.assertEqual(KnowledgeContent.objects.get(pk=self.pk).live_revision_id, revision.pk)

    def test_restore_appends_draft_preserves_identity_and_history(self):
        v1 = self.draft("V1")
        self.publish(v1)
        self.publish(self.draft("V2"))
        history = list(Revision.objects.order_by("pk").values())
        restored = restore_draft(self.pk, v1.pk, self.user)
        obj = KnowledgeContent.objects.get(pk=self.pk)
        self.assertEqual(obj.article_id, self.article.pk)
        self.assertEqual(obj.pk, self.pk)
        self.assertEqual(obj.latest_revision_id, restored.pk)
        self.assertNotEqual(restored.pk, v1.pk)
        self.assertEqual(read_live(self.pk)["body"], "正文V2")
        self.assertEqual(
            list(Revision.objects.exclude(pk=restored.pk).order_by("pk").values()), history
        )
        self.publish(restored)
        self.assertEqual(read_live(self.pk)["body"], "正文V1")
        self.assertEqual(KnowledgeContent.objects.count(), 1)
        self.assertEqual(
            list(Revision.objects.exclude(pk=restored.pk).order_by("pk").values()), history
        )

    def test_save_and_save_revision_reject_rebinding(self):
        for operation in ("save", "save_revision"):
            obj = KnowledgeContent.objects.get(pk=self.pk)
            obj.article = self.other
            before = version_snapshot()
            with self.assertRaises(ValidationError):
                getattr(obj, operation)()
            self.assertEqual(version_snapshot(), before)

    def test_primary_key_change_rejected(self):
        for operation in ("save", "save_revision"):
            obj = KnowledgeContent.objects.get(pk=self.pk)
            obj.pk += 100
            before = version_snapshot()
            with self.assertRaises(ValidationError):
                getattr(obj, operation)()
            self.assertEqual(version_snapshot(), before)

    def test_forged_restore_json_rejected(self):
        revision = self.draft("V1")
        for field, value in (("article", str(self.other.pk)), ("pk", self.pk + 100)):
            payload = deepcopy(Revision.objects.get(pk=revision.pk).content)
            payload[field] = value
            before = version_snapshot()
            # 模拟存储中被篡改的 JSON；不在测试中手工修回关联。
            with self.assertRaises(ValidationError):
                KnowledgeContent.objects.get(pk=self.pk).with_content_json(payload)
            # 让实际恢复入口读到篡改 JSON，并断言不生成修订。
            with patch.object(Revision.objects, "get", return_value=revision):
                revision.content = payload
                with self.assertRaises(ValidationError):
                    restore_draft(self.pk, revision.pk, self.user)
            self.assertEqual(version_snapshot(), before)

    def test_foreign_revision_restore_and_publish_rejected(self):
        other = KnowledgeContent.objects.create(article=self.other, title="其他", body="其他")
        revision = other.save_revision(user=self.user)
        before = version_snapshot()
        for operation in (restore_draft, publish_for_test):
            with self.assertRaises(ValidationError):
                operation(self.pk, revision.pk, self.user)
        self.assertEqual(version_snapshot(), before)

    def test_no_permission_or_missing_user_cannot_publish(self):
        revision = self.draft("V1")
        plain = User.objects.create_user(username="f04a_plain")
        for user in (plain, None):
            before = version_snapshot()
            with self.assertRaises(PermissionDenied):
                publish_for_test(self.pk, revision.pk, user)
            self.assertEqual(version_snapshot(), before)

    def test_publish_failure_rolls_back_all_writes(self):
        self.publish(self.draft("V1"))
        revision = self.draft("V2")
        before = version_snapshot()
        # 在 Wagtail 已写入内容后、发布日志阶段抛错，验证入口外层 atomic。
        with patch("wagtail.actions.publish_revision.log", side_effect=RuntimeError("故障注入")):
            with self.assertRaises(RuntimeError):
                self.publish(revision)
        self.assertEqual(version_snapshot(), before)
        self.assertEqual(read_live(self.pk)["body"], "正文V1")

    def test_article_deletion_protected(self):
        self.draft("V1")
        before = version_snapshot()
        with self.assertRaises(ProtectedError) as caught:
            self.article.delete()
        self.assertEqual(version_snapshot(), before)
        self.assertIn(KnowledgeContent.objects.get(pk=self.pk), caught.exception.protected_objects)
        self.assertTrue(Article.objects.filter(pk=self.article.pk).exists())

    def test_overwrite_rejected(self):
        revision = self.draft("V1")
        before = version_snapshot()
        with self.assertRaises(ValidationError):
            KnowledgeContent.objects.get(pk=self.pk).save_revision(overwrite_revision=revision)
        self.assertEqual(version_snapshot(), before)

    def test_reconstructed_instance_cannot_rebind_existing_pk(self):
        obj = KnowledgeContent(pk=self.pk, article=self.other, title="伪造", body="伪造")
        before = version_snapshot()
        with self.assertRaises(ValidationError):
            obj.save()
        self.assertEqual(version_snapshot(), before)
