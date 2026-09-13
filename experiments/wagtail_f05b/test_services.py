"""直接调用服务的批准测试；不验收新 HTTP 入口。"""

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from wagtail.actions.publish_revision import PublishRevisionAction
from wagtail.models import ModelLogEntry, Revision, TaskState, WorkflowState

from apps.accounts.models import User
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.tests import legacy_snapshot
from experiments.wagtail_f04a.versions import read_live
from experiments.wagtail_f05a.models import TaskSubmission
from experiments.wagtail_f05a.services import reject, submit
from experiments.wagtail_f05a.tests import snapshot

from . import tests as eligibility_tests
from .eligibility import check_approval_eligibility
from .services import ApprovalRejected, approve_review


class ApprovalTests(TestCase):
    login = eligibility_tests.EligibilityTests.login
    data = eligibility_tests.EligibilityTests.data
    url = eligibility_tests.EligibilityTests.url
    post_submit = eligibility_tests.EligibilityTests.post_submit

    def setUp(self):
        eligibility_tests.EligibilityTests.setUp(self)
        self.revision_history = list(Revision.objects.order_by("pk").values())
        self.content_identity = (self.content.pk, self.content.article_id)

    def tearDown(self):
        self.assertEqual(legacy_snapshot(), self.legacy)
        self.assertEqual(
            list(
                Revision.objects.filter(pk__in=[r["id"] for r in self.revision_history])
                .order_by("pk")
                .values()
            ),
            self.revision_history,
        )
        obj = KnowledgeContent.objects.get(pk=self.pk)
        self.assertEqual((obj.pk, obj.article_id), self.content_identity)

    def denied(self, task_id=None, actor=None, code=None):
        before = snapshot()
        with self.assertRaises(ApprovalRejected) as error:
            approve_review(task_id or self.ts_id, actor or self.reviewer)
        if code:
            self.assertEqual(error.exception.code, code)
        self.assertEqual(snapshot(), before)

    def test_approve_v2_once_and_save_v3_keeps_live_v2(self):
        self.assertFalse(self.reviewer.has_perm("fusion_f04a.publish_knowledgecontent"))
        self.assertEqual(read_live(self.pk)["title"], "V1")
        before_logs = ModelLogEntry.objects.filter(action="wagtail.publish").count()
        result = approve_review(self.ts_id, self.reviewer)
        self.assertEqual(result.status, "approved")
        self.assertEqual(result.finished_by_id, self.reviewer.pk)
        self.assertIsNotNone(result.finished_at)
        self.ws.refresh_from_db()
        self.assertEqual(self.ws.status, "approved")
        self.assertEqual(KnowledgeContent.objects.get(pk=self.pk).live_revision_id, self.v2)
        self.assertEqual(read_live(self.pk)["title"], "V2")
        self.assertEqual(
            ModelLogEntry.objects.filter(action="wagtail.publish").count(), before_logs + 1
        )
        self.denied(code="task_inactive")
        obj = KnowledgeContent.objects.get(pk=self.pk)
        obj.title = "V3"
        revision = obj.save_revision(user=self.creator)
        self.assertNotEqual(revision.pk, self.v2)
        self.assertEqual(read_live(self.pk)["title"], "V2")
        self.assertEqual(KnowledgeContent.objects.get(pk=self.pk).live_revision_id, self.v2)

    def test_first_publication(self):
        obj = KnowledgeContent.objects.create(
            article=self.other, title="首次正式内容", body="新正文"
        )
        revision = obj.save_revision(user=self.creator)
        state = submit(obj.pk, revision.pk, self.submitter)
        self.assertIsNone(read_live(obj.pk))
        approve_review(state.current_task_state_id, self.reviewer)
        obj.refresh_from_db()
        self.assertTrue(obj.live)
        self.assertEqual(obj.live_revision_id, revision.pk)
        self.assertEqual(read_live(obj.pk)["body"], "新正文")

    def test_resubmit_uses_new_identity_and_revision(self):
        old_task = self.ts_id
        old_submission = TaskSubmission.objects.values().get(pk=old_task)
        reject(self.pk, old_task, self.reviewer, "重提")
        obj = KnowledgeContent.objects.get(pk=self.pk)
        obj.title = "重提修订"
        revision = obj.save_revision(user=self.submitter)
        state = submit(self.pk, revision.pk, self.creator)
        self.ts_id = state.current_task_state_id
        self.assertNotEqual(self.ts_id, old_task)
        self.assertEqual(TaskSubmission.objects.get(pk=self.ts_id).submitted_by_id, self.creator.pk)
        self.denied(actor=self.creator, code="review_submitter")
        self.denied(actor=self.submitter, code="revision_creator")
        self.denied(task_id=old_task, code="task_inactive")
        approve_review(self.ts_id, self.reviewer)
        self.assertEqual(KnowledgeContent.objects.get(pk=self.pk).live_revision_id, revision.pk)
        self.assertEqual(TaskSubmission.objects.values().get(pk=old_task), old_submission)
        self.assertEqual(TaskState.objects.get(pk=old_task).status, "rejected")

    def test_identity_and_current_account_are_rechecked(self):
        self.denied(actor=self.creator, code="revision_creator")
        self.denied(actor=self.submitter, code="review_submitter")
        for actor in (self.creator, self.submitter):
            User.objects.filter(pk=actor.pk).update(is_superuser=True)
            self.denied(actor=actor)
        self.denied(actor=self.users["super"], code="reviewer_required")
        self.assertTrue(
            check_approval_eligibility(
                content_id=self.pk, task_state_id=self.ts_id, user=self.reviewer
            ).allowed
        )
        User.objects.filter(pk=self.reviewer.pk).update(is_active=False)
        self.denied(code="account_invalid")
        User.objects.filter(pk=self.reviewer.pk).update(is_active=True, account_status="disabled")
        self.denied(code="account_invalid")
        User.objects.filter(pk=self.reviewer.pk).update(account_status="active")
        self.reviewer.groups.clear()
        self.denied(code="reviewer_required")
        self.denied(actor=AnonymousUser(), code="account_invalid")

    def test_missing_and_wrong_submission_rejected(self):
        TaskSubmission.objects.filter(pk=self.ts_id).update(revision_id=self.revision_id)
        self.denied(code="identity_inconsistent")
        TaskSubmission.objects.filter(pk=self.ts_id).delete()
        self.denied(code="identity_missing")

    def test_rejected_and_missing_task_denied(self):
        self.denied(task_id=999999, code="binding_invalid")
        reject(self.pk, self.ts_id, self.reviewer, "驳回")
        self.denied(code="task_inactive")

    def test_newer_draft_and_cross_object_revision_denied(self):
        obj = KnowledgeContent.objects.get(pk=self.pk)
        newer = obj.save_revision(user=self.creator)
        self.denied(code="binding_invalid")
        other = KnowledgeContent.objects.create(article=self.other, title="另一内容", body="其他")
        foreign = other.save_revision(user=self.creator)
        TaskState.objects.filter(pk=self.ts_id).update(revision=foreign)
        self.denied(code="binding_invalid")
        self.assertNotEqual(newer.pk, self.v2)

    def test_exception_after_status_updates_rolls_back(self):
        before = snapshot()

        def fail(action):
            self.assertEqual(TaskState.objects.get(pk=self.ts_id).status, "approved")
            self.assertEqual(WorkflowState.objects.get(pk=self.ws.pk).status, "approved")
            self.assertEqual(
                KnowledgeContent.objects.get(pk=self.pk).live_revision_id, self.revision_id
            )
            raise RuntimeError("发布完成前的合成异常")

        with patch.object(
            PublishRevisionAction,
            "_publish_revision",
            autospec=True,
            side_effect=lambda action, *args, **kwargs: fail(action),
        ) as call:
            with self.assertRaisesMessage(RuntimeError, "发布完成前的合成异常"):
                approve_review(self.ts_id, self.reviewer)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(snapshot(), before)
        approve_review(self.ts_id, self.reviewer)
        self.assertEqual(read_live(self.pk)["title"], "V2")

    def test_direct_native_approval_and_publish_do_not_gain_permission(self):
        before = snapshot()
        with self.assertRaises(PermissionDenied):
            TaskState.objects.get(pk=self.ts_id).approve(user=self.reviewer)
        self.assertEqual(snapshot(), before)
        with self.assertRaises(PermissionDenied):
            Revision.objects.get(pk=self.v2).publish(user=self.reviewer)
        self.assertEqual(snapshot(), before)
