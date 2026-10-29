"""LOCAL-DEMO-DATA-01 演示文章初始化命令测试。"""

from __future__ import annotations

import os
import socket
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import UserGroup
from apps.audit.models import AuditEvent
from apps.knowledge.management.commands.seed_demo_data import (
    DEMO_CATEGORY_CODE,
    DEMO_GROUP_NAME,
    DEMO_SPACE_CODE,
)
from apps.knowledge.management.commands.seed_local_demo_article import (
    DEMO_APPROVE_IDEMPOTENCY_KEY,
    DEMO_BODY_TEXT,
    DEMO_SUBMIT_IDEMPOTENCY_KEY,
    DEMO_TITLE,
)
from apps.knowledge.management.commands.seed_local_demo_article import (
    Command as SeedLocalDemoArticleCommand,
)
from apps.knowledge.models import (
    Article,
    ArticleAudience,
    ArticleVersion,
    AudienceEffect,
    AudienceType,
    Category,
    KnowledgeSpace,
    ReviewDecision,
    ReviewerSpaceScope,
    ReviewRecord,
    VersionStatus,
)
from apps.knowledge.readers import get_employee_article_detail
from apps.search.readers import search_employee_articles
from apps.workflow.models import (
    IdempotencyStatus,
    WorkflowIdempotencyRecord,
    WorkflowOutboxEvent,
    WorkflowOutboxStatus,
)


class SeedLocalDemoArticleGuardTests(TestCase):
    """环境标识或运行模式不足时，命令必须在任何写入前失败关闭。"""

    @override_settings(DEBUG=False, DEV_LOGIN_ENABLED=True)
    def test_rejects_non_demo_runtime_even_with_markers(self):
        environment = {
            "OPSAI_LOCAL_DEMO": "true",
            "OPSAI_LOCAL_DEMO_PROJECT": "opsai-local-demo",
            "OPSAI_LOCAL_DEMO_INSTANCE": "local-demo-data-01",
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            with self.assertRaisesMessage(CommandError, "DEBUG=True"):
                call_command("seed_local_demo_article", stdout=StringIO())

        self.assertEqual(Article.objects.count(), 0)
        self.assertEqual(get_user_model().objects.count(), 0)

    @override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
    def test_rejects_missing_demo_marker(self):
        environment = {
            "OPSAI_LOCAL_DEMO": "",
            "OPSAI_LOCAL_DEMO_PROJECT": "opsai-local-demo",
            "OPSAI_LOCAL_DEMO_INSTANCE": "local-demo-data-01",
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            with self.assertRaisesMessage(CommandError, "演示环境标识"):
                call_command("seed_local_demo_article", stdout=StringIO())

        self.assertEqual(Article.objects.count(), 0)
        self.assertEqual(get_user_model().objects.count(), 0)


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class SeedLocalDemoArticleTests(TestCase):
    """在隔离测试库中验证完整服务链、权限、幂等和回滚。"""

    def run_seed(self) -> str:
        output = StringIO()
        with mock.patch.object(
            SeedLocalDemoArticleCommand,
            "_verify_isolated_environment",
            return_value={
                "database": "opsai_local_demo_test",
                "user": "test-runner",
                "server": "isolated-test-db",
            },
        ):
            call_command("seed_local_demo_article", stdout=output)
        return output.getvalue()

    def test_first_run_builds_published_demo_with_independent_identities(self):
        output = self.run_seed()

        article = Article.objects.select_related(
            "current_published_version", "latest_working_version"
        ).get(title=DEMO_TITLE)
        users = get_user_model().objects.in_bulk(
            ["dev_employee", "dev_editor", "dev_reviewer"], field_name="username"
        )

        self.assertIn("created: 1", output)
        self.assertEqual(set(users), {"dev_employee", "dev_editor", "dev_reviewer"})
        self.assertNotEqual(users["dev_editor"].pk, users["dev_reviewer"].pk)
        self.assertTrue(all(not user.is_superuser for user in users.values()))
        self.assertTrue(all(not user.has_usable_password() for user in users.values()))
        self.assertEqual(article.space.code, DEMO_SPACE_CODE)
        self.assertEqual(article.category.code, DEMO_CATEGORY_CODE)
        self.assertEqual(article.current_published_version.status, VersionStatus.PUBLISHED)
        self.assertEqual(article.latest_working_version.status, VersionStatus.DRAFT)
        self.assertIn(DEMO_BODY_TEXT, article.current_published_version.body_plaintext)

    def test_second_run_is_idempotent_without_duplicate_business_data(self):
        self.run_seed()
        before = {
            "users": get_user_model().objects.count(),
            "spaces": KnowledgeSpace.objects.count(),
            "categories": Category.objects.count(),
            "articles": Article.objects.count(),
            "versions": ArticleVersion.objects.count(),
            "scopes": ReviewerSpaceScope.objects.count(),
            "audiences": ArticleAudience.objects.count(),
            "reviews": ReviewRecord.objects.count(),
            "audit": AuditEvent.objects.count(),
            "outbox": WorkflowOutboxEvent.objects.count(),
            "idempotency": WorkflowIdempotencyRecord.objects.count(),
        }

        output = self.run_seed()
        after = {
            "users": get_user_model().objects.count(),
            "spaces": KnowledgeSpace.objects.count(),
            "categories": Category.objects.count(),
            "articles": Article.objects.count(),
            "versions": ArticleVersion.objects.count(),
            "scopes": ReviewerSpaceScope.objects.count(),
            "audiences": ArticleAudience.objects.count(),
            "reviews": ReviewRecord.objects.count(),
            "audit": AuditEvent.objects.count(),
            "outbox": WorkflowOutboxEvent.objects.count(),
            "idempotency": WorkflowIdempotencyRecord.objects.count(),
        }

        self.assertIn("existing: 1", output)
        self.assertEqual(after, before)
        self.assertEqual(Article.objects.filter(title=DEMO_TITLE).count(), 1)

    def test_formal_workflow_evidence_proves_review_was_not_bypassed(self):
        self.run_seed()

        article = Article.objects.select_related(
            "current_published_version", "latest_working_version"
        ).get(title=DEMO_TITLE)
        versions = list(article.versions.order_by("version_no"))
        review = ReviewRecord.objects.get(article_version=article.current_published_version)
        idempotency = WorkflowIdempotencyRecord.objects.order_by("operation")

        self.assertEqual(
            [version.status for version in versions],
            [VersionStatus.SAVED, VersionStatus.PUBLISHED, VersionStatus.DRAFT],
        )
        self.assertEqual(article.current_published_version.submitted_by.username, "dev_editor")
        self.assertEqual(review.reviewer.username, "dev_reviewer")
        self.assertEqual(review.decision, ReviewDecision.APPROVED)
        self.assertEqual(
            set(idempotency.values_list("key", flat=True)),
            {DEMO_SUBMIT_IDEMPOTENCY_KEY, DEMO_APPROVE_IDEMPOTENCY_KEY},
        )
        self.assertTrue(
            all(
                status == IdempotencyStatus.COMPLETED
                for status in idempotency.values_list("status", flat=True)
            )
        )
        self.assertEqual(AuditEvent.objects.count(), 2)

    def test_published_version_is_visible_and_searchable_to_demo_employee(self):
        self.run_seed()
        user = get_user_model().objects.get(username="dev_employee")
        article = Article.objects.get(title=DEMO_TITLE)

        detail = get_employee_article_detail(user, article.kb_no)
        results = search_employee_articles(user, "网络打印机")

        self.assertIsNotNone(detail)
        self.assertEqual(detail.title, DEMO_TITLE)
        self.assertIn("Print Spooler", detail.body_text)
        self.assertEqual(list(results.values_list("pk", flat=True)), [article.pk])

    def test_successor_draft_is_not_exposed_as_formal_content(self):
        self.run_seed()
        user = get_user_model().objects.get(username="dev_employee")
        article = Article.objects.select_related(
            "current_published_version", "latest_working_version"
        ).get(title=DEMO_TITLE)

        ArticleVersion.objects.filter(pk=article.latest_working_version_id).update(
            body_plaintext="仅草稿可见的秘密文本"
        )
        detail = get_employee_article_detail(user, article.kb_no)

        self.assertNotEqual(article.current_published_version_id, article.latest_working_version_id)
        self.assertNotIn("仅草稿可见的秘密文本", detail.body_text)
        self.assertEqual(search_employee_articles(user, "仅草稿可见").count(), 0)

    def test_unauthorized_identity_cannot_read_restricted_article(self):
        self.run_seed()
        editor = get_user_model().objects.get(username="dev_editor")
        article = Article.objects.get(title=DEMO_TITLE)
        audience = ArticleAudience.objects.get(article=article)

        self.assertEqual(audience.audience_type, AudienceType.USER_GROUP)
        self.assertEqual(audience.effect, AudienceEffect.ALLOW)
        self.assertEqual(audience.user_group, UserGroup.objects.get(name=DEMO_GROUP_NAME))
        self.assertIsNone(get_employee_article_detail(editor, article.kb_no))
        self.assertEqual(search_employee_articles(editor, "网络打印机").count(), 0)

    def test_workflow_only_records_pending_outbox_and_does_not_send(self):
        with mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("初始化命令不得建立外部网络连接"),
        ):
            self.run_seed()

        events = WorkflowOutboxEvent.objects.order_by("event_type")
        self.assertEqual(events.count(), 2)
        self.assertTrue(
            all(
                status == WorkflowOutboxStatus.PENDING
                for status in events.values_list("status", flat=True)
            )
        )
        self.assertTrue(all(count == 0 for count in events.values_list("attempt_count", flat=True)))
        self.assertTrue(all(value is None for value in events.values_list("sent_at", flat=True)))

    def test_failure_rolls_back_demo_writes_without_overwriting_history(self):
        historical = get_user_model().objects.create_user(
            username="existing-history-user",
            password=None,
            display_name="既有历史用户",
        )
        output = StringIO()

        with (
            mock.patch.object(
                SeedLocalDemoArticleCommand,
                "_verify_isolated_environment",
                return_value={"database": "test", "user": "test", "server": "test"},
            ),
            mock.patch(
                "apps.knowledge.management.commands.seed_local_demo_article."
                "approve_and_publish_article_version",
                side_effect=RuntimeError("injected failure"),
            ),
            self.assertRaisesMessage(CommandError, "已整体回滚"),
        ):
            call_command("seed_local_demo_article", stdout=output)

        historical.refresh_from_db()
        self.assertEqual(historical.display_name, "既有历史用户")
        self.assertEqual(Article.objects.count(), 0)
        self.assertEqual(KnowledgeSpace.objects.count(), 0)
        self.assertEqual(
            get_user_model().objects.exclude(pk=historical.pk).count(),
            0,
        )
        self.assertEqual(WorkflowOutboxEvent.objects.count(), 0)
