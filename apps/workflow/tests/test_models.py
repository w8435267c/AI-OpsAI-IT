"""Task 13-02B：Workflow Outbox 与 Idempotency 持久化模型测试。"""

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.workflow.models import (
    IdempotencyOperation,
    IdempotencyStatus,
    WorkflowEventType,
    WorkflowIdempotencyRecord,
    WorkflowOutboxEvent,
    WorkflowOutboxStatus,
)


class WorkflowFixtures:
    _sequence = 0

    @classmethod
    def next_value(cls) -> int:
        cls._sequence += 1
        return cls._sequence

    def create_user(self, prefix: str = "workflow-user") -> User:
        sequence = self.next_value()
        return User.objects.create_user(username=f"{prefix}-{sequence}")

    def create_idempotency(self, **overrides) -> WorkflowIdempotencyRecord:
        sequence = self.next_value()
        values = {
            "actor": self.create_user("idempotency-actor"),
            "operation": IdempotencyOperation.SUBMIT,
            "key": f"idempotency-key-{sequence}",
            "request_fingerprint": f"{sequence:064x}",
        }
        values.update(overrides)
        return WorkflowIdempotencyRecord.objects.create(**values)


class WorkflowOutboxEventTests(WorkflowFixtures, TestCase):
    def test_defaults_match_pending_delivery_contract(self):
        before = timezone.now()
        event = WorkflowOutboxEvent.objects.create(
            event_type=WorkflowEventType.REVIEW_SUBMITTED,
            dedupe_key="review-submitted:version-1",
        )

        self.assertEqual(event.status, WorkflowOutboxStatus.PENDING)
        self.assertEqual(event.attempt_count, 0)
        self.assertGreaterEqual(event.available_at, before)
        self.assertIsNone(event.sent_at)
        self.assertEqual(event.payload, {})
        self.assertEqual(event.last_error, "")
        self.assertIsNotNone(event.created_at)
        self.assertIsNotNone(event.updated_at)

    def test_payload_default_is_not_shared(self):
        first = WorkflowOutboxEvent(
            event_type=WorkflowEventType.REVIEW_SUBMITTED,
            dedupe_key="first",
        )
        second = WorkflowOutboxEvent(
            event_type=WorkflowEventType.REVIEW_REJECTED,
            dedupe_key="second",
        )

        first.payload["article_id"] = "first"

        self.assertEqual(second.payload, {})

    def test_dedupe_key_is_unique_but_different_keys_are_allowed(self):
        WorkflowOutboxEvent.objects.create(
            event_type=WorkflowEventType.REVIEW_SUBMITTED,
            dedupe_key="duplicate",
        )
        WorkflowOutboxEvent.objects.create(
            event_type=WorkflowEventType.REVIEW_SUBMITTED,
            dedupe_key="different",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            WorkflowOutboxEvent.objects.create(
                event_type=WorkflowEventType.REVIEW_REJECTED,
                dedupe_key="duplicate",
            )

    def test_invalid_status_fails_model_validation(self):
        event = WorkflowOutboxEvent(
            event_type=WorkflowEventType.REVIEW_SUBMITTED,
            dedupe_key="invalid-status",
            status="unknown",
        )

        with self.assertRaises(ValidationError):
            event.full_clean()

    def test_pending_with_sent_at_fails_model_and_database_validation(self):
        event = WorkflowOutboxEvent(
            event_type=WorkflowEventType.REVIEW_SUBMITTED,
            dedupe_key="pending-sent-model",
            sent_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            event.full_clean()

        with self.assertRaises(IntegrityError), transaction.atomic():
            WorkflowOutboxEvent.objects.create(
                event_type=WorkflowEventType.REVIEW_SUBMITTED,
                dedupe_key="pending-sent-database",
                sent_at=timezone.now(),
            )

    def test_sent_without_sent_at_fails_model_and_database_validation(self):
        event = WorkflowOutboxEvent(
            event_type=WorkflowEventType.REVIEW_SUBMITTED,
            dedupe_key="sent-without-time-model",
            status=WorkflowOutboxStatus.SENT,
        )
        with self.assertRaises(ValidationError):
            event.full_clean()

        with self.assertRaises(IntegrityError), transaction.atomic():
            WorkflowOutboxEvent.objects.create(
                event_type=WorkflowEventType.REVIEW_SUBMITTED,
                dedupe_key="sent-without-time-database",
                status=WorkflowOutboxStatus.SENT,
            )

    def test_sent_with_timestamp_is_valid(self):
        event = WorkflowOutboxEvent(
            event_type=WorkflowEventType.REVIEW_APPROVED_PUBLISHED,
            dedupe_key="sent-valid",
            status=WorkflowOutboxStatus.SENT,
            sent_at=timezone.now(),
        )

        event.full_clean()

    def test_meta_contract_has_dispatcher_indexes_and_no_admin(self):
        self.assertEqual(
            {index.name for index in WorkflowOutboxEvent._meta.indexes},
            {"wf_out_status_avail_idx", "wf_out_type_created_idx"},
        )
        self.assertEqual(
            {constraint.name for constraint in WorkflowOutboxEvent._meta.constraints},
            {
                "wf_out_status_valid_ck",
                "wf_out_pending_unsent_ck",
                "wf_out_sent_time_ck",
            },
        )
        self.assertNotIn(WorkflowOutboxEvent, admin.site._registry)


class WorkflowIdempotencyRecordTests(WorkflowFixtures, TestCase):
    def test_create_record_with_in_progress_defaults(self):
        actor = self.create_user("idempotency-actor")
        record = WorkflowIdempotencyRecord.objects.create(
            actor=actor,
            operation=IdempotencyOperation.REJECT,
            key="reject-key",
            request_fingerprint="a" * 64,
        )

        self.assertEqual(record.actor, actor)
        self.assertEqual(record.operation, "reject")
        self.assertEqual(record.key, "reject-key")
        self.assertEqual(record.request_fingerprint, "a" * 64)
        self.assertEqual(record.status, IdempotencyStatus.IN_PROGRESS)
        self.assertEqual(record.result_code, "")
        self.assertEqual(record.result_payload, {})
        self.assertIsNotNone(record.created_at)
        self.assertIsNotNone(record.updated_at)

    def test_result_payload_default_is_not_shared(self):
        first = WorkflowIdempotencyRecord(
            actor=self.create_user("idempotency-actor"),
            operation=IdempotencyOperation.SUBMIT,
            key="first",
            request_fingerprint="1" * 64,
        )
        second = WorkflowIdempotencyRecord(
            actor=self.create_user("idempotency-actor"),
            operation=IdempotencyOperation.SUBMIT,
            key="second",
            request_fingerprint="2" * 64,
        )

        first.result_payload["version_id"] = "first"

        self.assertEqual(second.result_payload, {})

    def test_actor_operation_key_is_unique_in_database(self):
        actor = self.create_user("idempotency-actor")
        self.create_idempotency(actor=actor, key="duplicate")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_idempotency(actor=actor, key="duplicate")

    def test_same_key_is_allowed_for_different_actor(self):
        first = self.create_idempotency(key="shared")
        second = self.create_idempotency(key="shared")

        self.assertNotEqual(first.actor_id, second.actor_id)

    def test_same_actor_and_key_are_allowed_for_different_operation(self):
        actor = self.create_user("idempotency-actor")
        first = self.create_idempotency(
            actor=actor,
            operation=IdempotencyOperation.SUBMIT,
            key="shared",
        )
        second = self.create_idempotency(
            actor=actor,
            operation=IdempotencyOperation.REJECT,
            key="shared",
        )

        self.assertNotEqual(first.operation, second.operation)

    def test_fingerprint_requires_lowercase_sha256_hex(self):
        valid = WorkflowIdempotencyRecord(
            actor=self.create_user("idempotency-actor"),
            operation=IdempotencyOperation.APPROVE_PUBLISH,
            key="valid-fingerprint",
            request_fingerprint="0123456789abcdef" * 4,
        )
        valid.full_clean()

        for fingerprint in ("a" * 63, "A" * 64, "g" * 64):
            with self.subTest(fingerprint=fingerprint):
                invalid = WorkflowIdempotencyRecord(
                    actor=self.create_user("idempotency-actor"),
                    operation=IdempotencyOperation.SUBMIT,
                    key=f"invalid-{fingerprint[:8]}",
                    request_fingerprint=fingerprint,
                )
                with self.assertRaises(ValidationError):
                    invalid.full_clean()

    def test_completed_requires_result_code_in_model_and_database(self):
        record = WorkflowIdempotencyRecord(
            actor=self.create_user("idempotency-actor"),
            operation=IdempotencyOperation.SUBMIT,
            key="completed-model",
            request_fingerprint="b" * 64,
            status=IdempotencyStatus.COMPLETED,
        )
        with self.assertRaises(ValidationError):
            record.full_clean()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_idempotency(
                key="completed-database",
                status=IdempotencyStatus.COMPLETED,
            )

    def test_completed_with_result_code_is_valid(self):
        record = WorkflowIdempotencyRecord(
            actor=self.create_user("idempotency-actor"),
            operation=IdempotencyOperation.APPROVE_PUBLISH,
            key="completed-valid",
            request_fingerprint="c" * 64,
            status=IdempotencyStatus.COMPLETED,
            result_code="published",
        )

        record.full_clean()

    def test_meta_contract_has_unique_constraint_cleanup_index_and_no_admin(self):
        self.assertEqual(
            {index.name for index in WorkflowIdempotencyRecord._meta.indexes},
            {"wf_idem_status_created_idx"},
        )
        self.assertEqual(
            {constraint.name for constraint in WorkflowIdempotencyRecord._meta.constraints},
            {
                "wf_idem_actor_op_key_uniq",
                "wf_idem_op_valid_ck",
                "wf_idem_status_valid_ck",
                "wf_idem_completed_result_ck",
            },
        )
        self.assertNotIn(WorkflowIdempotencyRecord, admin.site._registry)

    def test_system_roles_receive_no_audit_or_workflow_permissions(self):
        call_command("sync_system_roles", verbosity=0)

        from django.contrib.auth.models import Group

        granted = Group.objects.filter(
            permissions__content_type__app_label__in=("audit", "workflow")
        ).distinct()
        self.assertFalse(granted.exists())
