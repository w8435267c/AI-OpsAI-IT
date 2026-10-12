"""Task 13-02B：Audit 初始迁移前进、回滚与再前进测试。"""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AuditInitialMigrationTests(TransactionTestCase):
    migrate_from = ("audit", None)
    migrate_to = ("audit", "0001_initial")

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
        self.assertNotIn("audit_event", connection.introspection.table_names())

        apps = self._migrate(self.migrate_to)
        AuditEvent = apps.get_model("audit", "AuditEvent")
        AuditEvent.objects.create(event_type="review_submitted")
        self.assertEqual(AuditEvent.objects.count(), 1)

        self._migrate(self.migrate_from)
        self.assertNotIn("audit_event", connection.introspection.table_names())

        apps = self._migrate(self.migrate_to)
        AuditEvent = apps.get_model("audit", "AuditEvent")
        self.assertEqual(AuditEvent.objects.count(), 0)
