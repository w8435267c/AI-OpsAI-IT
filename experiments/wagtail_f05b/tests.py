"""合成账号与内存数据；只调用资格入口，不调用批准。"""

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from wagtail.models import Revision, TaskState, WorkflowState

from apps.accounts.models import User
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.tests import legacy_snapshot
from experiments.wagtail_f05a import tests as f05a
from experiments.wagtail_f05a.models import TaskSubmission
from experiments.wagtail_f05a.services import reject

from .eligibility import check_approval_eligibility


class EligibilityTests(TestCase):
    # 仅借用夹具和辅助方法，不继承/收集 F05A 历史测试。
    login = f05a.ReviewTests.login
    data = f05a.ReviewTests.data
    url = f05a.ReviewTests.url
    tearDown = f05a.ReviewTests.tearDown

    def setUp(self):
        f05a.ReviewTests.setUp(self)
        self.creator = self.users["editor"]
        self.creator.groups.add(self.group)
        self.submitter = User.objects.create_user(
            username="f05b_submitter", password="synthetic-f04b"
        )
        self.submitter.groups.add(self.group, *self.creator.groups.all())
        self.users["submitter"] = self.submitter
        self.login("submitter")
        self.assertEqual(self.post_submit(self.v2).status_code, 302)
        self.ws = WorkflowState.objects.get(object_id=str(self.pk))
        self.ts_id = self.ws.current_task_state_id

    def post_submit(self, revision_id, content_id=None, **fields):
        return self.client.post(
            reverse("f05a_submit", args=[content_id or self.pk]),
            {
                "revision_id": revision_id,
                "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
                **fields,
            },
        )

    def check(self, actor=None, code="allowed", **kwargs):
        before = (f05a.snapshot(), legacy_snapshot())
        with CaptureQueriesContext(connection) as queries:
            result = check_approval_eligibility(
                content_id=kwargs.get("content_id", self.pk),
                task_state_id=kwargs.get("task_state_id", self.ts_id),
                user=self.reviewer if actor is None else actor,
            )
        self.assertEqual(result.code, code)
        self.assertEqual(result.allowed, code == "allowed")
        self.assertTrue(result.reason)
        self.assertEqual((f05a.snapshot(), legacy_snapshot()), before)
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries))
        return result

    def test_third_party_reviewer_allowed(self):
        self.check()

    def test_creator_and_submitter_denied_third_party_allowed(self):
        self.assertEqual(Revision.objects.get(pk=self.v2).user_id, self.creator.pk)
        self.assertEqual(self.ws.requested_by_id, self.submitter.pk)
        self.check(self.creator, "revision_creator")
        self.check(self.submitter, "review_submitter")
        self.check()

    def test_same_creator_and_submitter_denied(self):
        reject(self.pk, self.ts_id, self.reviewer, "新一轮")
        obj = KnowledgeContent.objects.get(pk=self.pk)
        revision = obj.save_revision(user=self.creator)
        self.login("editor")
        self.assertEqual(self.post_submit(revision.pk).status_code, 302)
        self.ws.refresh_from_db()
        self.ts_id = self.ws.current_task_state_id
        self.check(self.creator, "revision_creator")
        self.check()

    def test_superuser_has_no_bypass(self):
        self.check(self.users["super"], "reviewer_required")
        for actor, code in (
            (self.creator, "revision_creator"),
            (self.submitter, "review_submitter"),
        ):
            User.objects.filter(pk=actor.pk).update(is_superuser=True)
            self.check(actor, code)
        self.users["super"].groups.add(self.group)
        self.check(self.users["super"])

    def test_group_membership_required_and_reread(self):
        self.check(self.users["viewer"], "reviewer_required")
        self.reviewer.groups.clear()
        self.check(code="reviewer_required")

    def test_inactive_and_business_invalid_accounts_reread(self):
        for values in (
            {"is_active": False},
            {"account_status": "disabled"},
            {"account_status": "departed"},
        ):
            with self.subTest(values=values):
                User.objects.filter(pk=self.reviewer.pk).update(
                    is_active=True, account_status="active"
                )
                User.objects.filter(pk=self.reviewer.pk).update(**values)
                self.check(code="account_invalid")

    def test_anonymous_unsaved_and_deleted_account_denied(self):
        self.check(AnonymousUser(), "account_invalid")
        self.check(User(username="unsaved"), "account_invalid")
        self.check(User(pk=self.reviewer.pk, username="forged_unsaved"), "account_invalid")
        actor = User.objects.create_user(username="deleted_fixture")
        pk = actor.pk
        actor.delete()
        actor.pk = pk
        self.check(actor, "account_invalid")

    def test_missing_creator_denied(self):
        Revision.objects.filter(pk=self.v2).update(user=None)
        self.check(code="identity_missing")

    def test_missing_submission_denied_without_history_fallback(self):
        TaskSubmission.objects.filter(task_state_id=self.ts_id).delete()
        self.check(code="identity_missing")

    def test_wrong_revision_binding_denied(self):
        TaskSubmission.objects.filter(task_state_id=self.ts_id).update(revision_id=self.revision_id)
        self.check(code="identity_inconsistent")

    def test_initial_requester_is_not_current_identity_source(self):
        WorkflowState.objects.filter(pk=self.ws.pk).update(requested_by=None)
        self.check(self.submitter, "review_submitter")
        self.check()

    def test_finished_task_and_workflow_denied(self):
        for status in ("approved", "rejected", "cancelled"):
            with self.subTest(task=status):
                TaskState.objects.filter(pk=self.ts_id).update(status=status)
                self.check(code="task_inactive")
        TaskState.objects.filter(pk=self.ts_id).update(status="in_progress")
        for status in ("approved", "needs_changes", "cancelled"):
            with self.subTest(workflow=status):
                WorkflowState.objects.filter(pk=self.ws.pk).update(status=status)
                self.check(code="task_inactive")

    def test_inactive_configuration_and_noncurrent_task_denied(self):
        self.task.active = False
        self.task.save()
        self.check(code="task_inactive")
        self.task.active = True
        self.task.save()
        self.workflow.active = False
        self.workflow.save()
        self.check(code="task_inactive")
        self.workflow.active = True
        self.workflow.save()
        WorkflowState.objects.filter(pk=self.ws.pk).update(current_task_state=None)
        self.check(code="task_inactive")

    def test_missing_records_and_cross_object_revision_denied(self):
        self.check(task_state_id=999999, code="binding_invalid")
        self.check(content_id=999999, code="binding_invalid")
        other = KnowledgeContent.objects.create(
            article=self.other, title="另一个对象", body="other"
        )
        revision = other.save_revision(user=self.creator)
        self.check(content_id=other.pk, code="binding_invalid")
        TaskState.objects.filter(pk=self.ts_id).update(revision=revision)
        self.check(code="binding_invalid")

    def test_revision_payload_and_latest_binding_denied(self):
        revision = Revision.objects.get(pk=self.v2)
        original = revision.content.copy()
        revision.content["article"] = str(self.other.pk)
        revision.save(update_fields=["content"])
        self.check(code="binding_invalid")
        revision.content = original
        revision.save(update_fields=["content"])
        KnowledgeContent.objects.filter(pk=self.pk).update(latest_revision_id=self.revision_id)
        self.check(code="binding_invalid")

    def test_resubmission_binds_new_submitter_and_preserves_old(self):
        old = TaskSubmission.objects.values().get(task_state_id=self.ts_id)
        self.assertEqual(old["submitted_by_id"], self.submitter.pk)
        self.assertEqual(old["revision_id"], self.v2)
        old_task = self.ts_id
        reject(self.pk, self.ts_id, self.reviewer, "合成驳回")
        obj = KnowledgeContent.objects.get(pk=self.pk)
        obj.body = "重提正文"
        revision = obj.save_revision(user=self.submitter)
        self.login("editor")
        self.assertEqual(self.post_submit(revision.pk).status_code, 302)
        self.ws.refresh_from_db()
        self.ts_id = self.ws.current_task_state_id
        self.assertNotEqual(self.ts_id, old_task)
        self.assertEqual(self.ws.requested_by_id, self.submitter.pk)
        self.assertEqual(TaskSubmission.objects.values().get(task_state_id=old_task), old)
        current = TaskSubmission.objects.get(task_state_id=self.ts_id)
        self.assertEqual(current.submitted_by_id, self.creator.pk)
        self.assertEqual(current.revision_id, revision.pk)
        self.assertEqual(current.task_state.workflow_state_id, self.ws.pk)
        self.check(self.submitter, "revision_creator")
        self.check(self.creator, "review_submitter")
        self.check()
        for actor, code in (
            (self.submitter, "revision_creator"),
            (self.creator, "review_submitter"),
        ):
            User.objects.filter(pk=actor.pk).update(is_superuser=True)
            self.check(actor, code)
        before = f05a.snapshot()
        self.assertEqual(self.post_submit(revision.pk).status_code, 409)
        self.assertEqual(f05a.snapshot(), before)

    def test_first_submission_and_duplicate_are_bound_once(self):
        record = TaskSubmission.objects.get(task_state_id=self.ts_id)
        self.assertEqual(record.submitted_by_id, self.submitter.pk)
        self.assertEqual(record.revision_id, self.v2)
        before = f05a.snapshot()
        self.assertEqual(self.post_submit(self.v2).status_code, 409)
        self.assertEqual(f05a.snapshot(), before)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TaskSubmission.objects.create(
                task_state_id=self.ts_id, revision_id=self.v2, submitted_by=self.creator
            )
        self.assertEqual(f05a.snapshot(), before)

    def test_forged_submitter_fields_are_rejected(self):
        reject(self.pk, self.ts_id, self.reviewer, "重提测试")
        obj = KnowledgeContent.objects.get(pk=self.pk)
        revision = obj.save_revision(user=self.creator)
        before = f05a.snapshot()
        for key in ("submitted_by", "submitted_by_id", "requested_by", "user_id"):
            with self.subTest(key=key):
                self.assertEqual(
                    self.post_submit(revision.pk, **{key: self.reviewer.pk}).status_code, 400
                )
                self.assertEqual(f05a.snapshot(), before)
        self.assertEqual(self.post_submit(revision.pk).status_code, 302)
        self.ws.refresh_from_db()
        record = TaskSubmission.objects.get(task_state_id=self.ws.current_task_state_id)
        self.assertEqual(record.submitted_by_id, self.submitter.pk)

    def assert_submission_rollback(self, content_id, revision_id):
        before = f05a.snapshot()
        original = TaskSubmission.objects.create
        calls = []

        def create_then_fail(**kwargs):
            record = original(**kwargs)
            self.assertTrue(TaskState.objects.filter(pk=record.task_state_id).exists())
            self.assertTrue(TaskSubmission.objects.filter(pk=record.pk).exists())
            calls.append(record.pk)
            raise RuntimeError("提交记录写入后的合成异常")

        with patch.object(TaskSubmission.objects, "create", side_effect=create_then_fail):
            with self.assertRaisesMessage(RuntimeError, "提交记录写入后的合成异常"):
                self.post_submit(revision_id, content_id=content_id)
        self.assertEqual(len(calls), 1)
        self.assertEqual(f05a.snapshot(), before)
        self.assertFalse(TaskState.objects.filter(pk=calls[0]).exists())
        self.assertFalse(TaskSubmission.objects.filter(pk=calls[0]).exists())

    def test_initial_submission_failure_rolls_back_task_and_identity(self):
        obj = KnowledgeContent.objects.create(article=self.other, title="首次提交故障", body="正文")
        revision = obj.save_revision(user=self.creator)
        self.assert_submission_rollback(obj.pk, revision.pk)

    def test_resubmission_failure_rolls_back_task_and_identity(self):
        reject(self.pk, self.ts_id, self.reviewer, "重提故障")
        obj = KnowledgeContent.objects.get(pk=self.pk)
        revision = obj.save_revision(user=self.creator)
        self.assert_submission_rollback(self.pk, revision.pk)
