"""Task 13-02B：Workflow 初始迁移前进、回滚与再前进测试。"""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class WorkflowInitialMigrationTests(TransactionTestCase):
    migrate_from = ("workflow", None)
    migrate_to = ("workflow", "0001_initial")

    def setUp(self):
        super().setUp()
        self._migrate(self.migrate_from)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def _migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        if target[1] is None:
            return None
        return executor.loader.project_state([target]).apps

    def test_forward_reverse_forward_is_reversible(self):
        tables = connection.introspection.table_names()
        self.assertNotIn("workflow_outbox_event", tables)
        self.assertNotIn("workflow_idempotency_record", tables)

        apps = self._migrate(self.migrate_to)
        Outbox = apps.get_model("workflow", "WorkflowOutboxEvent")
        Outbox.objects.create(
            event_type="review_submitted",
            dedupe_key="migration-roundtrip",
        )
        self.assertEqual(Outbox.objects.count(), 1)

        self._migrate(self.migrate_from)
        tables = connection.introspection.table_names()
        self.assertNotIn("workflow_outbox_event", tables)
        self.assertNotIn("workflow_idempotency_record", tables)

        apps = self._migrate(self.migrate_to)
        Outbox = apps.get_model("workflow", "WorkflowOutboxEvent")
        Idempotency = apps.get_model("workflow", "WorkflowIdempotencyRecord")
        self.assertEqual(Outbox.objects.count(), 0)
        self.assertEqual(Idempotency.objects.count(), 0)
