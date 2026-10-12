"""Task 13-02B：追加式业务审计模型测试。"""

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.models import Permission
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent, AuditEventType
from apps.knowledge.models import Article, ArticleType, ArticleVersion, Category, KnowledgeSpace


class AuditEventFixtures:
    _sequence = 0

    @classmethod
    def next_value(cls) -> int:
        cls._sequence += 1
        return cls._sequence

    def create_user(self, prefix: str = "audit-user") -> User:
        sequence = self.next_value()
        return User.objects.create_user(username=f"{prefix}-{sequence}")

    def create_article(self) -> Article:
        sequence = self.next_value()
        owner = self.create_user("audit-owner")
        space = KnowledgeSpace.objects.create(
            code=f"audit-space-{sequence}",
            name=f"审计空间 {sequence}",
            space_type="employee",
            owner=owner,
        )
        category = Category.objects.create(
            space=space,
            code=f"audit-category-{sequence}",
            name=f"审计分类 {sequence}",
        )
        return Article.objects.create(
            kb_no=f"KB-{sequence:06d}",
            title=f"审计文章 {sequence}",
            space=space,
            category=category,
            article_type=ArticleType.GUIDE,
            owner=owner,
            created_by=owner,
            updated_by=owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )

    def create_version(self, article: Article) -> ArticleVersion:
        return ArticleVersion.objects.create(
            article=article,
            version_no=1,
            status="draft",
            title="审计版本",
            summary="审计版本摘要",
            change_summary="审计底座测试",
            created_by=article.created_by,
        )


class AuditEventTests(AuditEventFixtures, TestCase):
    def test_create_event_with_task13_context(self):
        actor = self.create_user("audit-actor")
        article = self.create_article()
        version = self.create_version(article)

        event = AuditEvent.objects.create(
            event_type=AuditEventType.REVIEW_SUBMITTED,
            actor=actor,
            article=article,
            article_version=version,
            metadata={"source": "task13-test"},
        )

        self.assertEqual(event.actor, actor)
        self.assertEqual(event.article, article)
        self.assertEqual(event.article_version, version)
        self.assertEqual(event.event_type, "review_submitted")
        self.assertEqual(event.metadata, {"source": "task13-test"})
        self.assertIsNotNone(event.occurred_at)

    def test_system_actor_and_business_relations_may_be_null(self):
        event = AuditEvent.objects.create(event_type=AuditEventType.REVIEW_REJECTED)

        self.assertIsNone(event.actor)
        self.assertIsNone(event.article)
        self.assertIsNone(event.article_version)

    def test_metadata_default_is_not_shared(self):
        first = AuditEvent(event_type=AuditEventType.REVIEW_SUBMITTED)
        second = AuditEvent(event_type=AuditEventType.REVIEW_APPROVED_PUBLISHED)

        first.metadata["request_id"] = "first"

        self.assertEqual(second.metadata, {})

    def test_actor_article_and_version_are_protected(self):
        actor = self.create_user("audit-actor")
        actor_event = AuditEvent.objects.create(
            event_type=AuditEventType.REVIEW_SUBMITTED,
            actor=actor,
        )
        article = self.create_article()
        article_event = AuditEvent.objects.create(
            event_type=AuditEventType.REVIEW_REJECTED,
            article=article,
        )
        version = self.create_version(article)
        version_event = AuditEvent.objects.create(
            event_type=AuditEventType.REVIEW_APPROVED_PUBLISHED,
            article_version=version,
        )

        with self.assertRaises(ProtectedError):
            actor.delete()
        with self.assertRaises(ProtectedError):
            article.delete()
        with self.assertRaises(ProtectedError):
            version.delete()
        self.assertIsNotNone(actor_event.pk)
        self.assertIsNotNone(article_event.pk)
        self.assertIsNotNone(version_event.pk)

    def test_meta_contract_is_append_only_and_indexed(self):
        self.assertEqual(AuditEvent._meta.default_permissions, ("add", "view"))
        self.assertEqual(
            {index.name for index in AuditEvent._meta.indexes},
            {
                "audit_type_time_idx",
                "audit_article_time_idx",
                "audit_version_time_idx",
            },
        )
        self.assertNotIn(AuditEvent, admin.site._registry)

    def test_post_migrate_generates_only_add_and_view_permissions(self):
        permissions = set(
            Permission.objects.filter(
                content_type__app_label="audit",
                content_type__model="auditevent",
            ).values_list("codename", flat=True)
        )

        self.assertEqual(permissions, {"add_auditevent", "view_auditevent"})
