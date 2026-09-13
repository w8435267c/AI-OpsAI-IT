"""启用工作流后的真实请求验证；不混用历史成绩。"""

from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.urls import reverse
from wagtail.models import (
    Revision,
    TaskState,
    Workflow,
    WorkflowContentType,
    WorkflowState,
    WorkflowTask,
)

from apps.accounts.models import User
from experiments.wagtail_f04a import tests as a
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.versions import read_live
from experiments.wagtail_f04b import tests as b

from .models import RejectOnlyTask, TaskSubmission


def snapshot():
    result = a.version_snapshot()
    for model in (WorkflowState, TaskState, TaskSubmission):
        result[model._meta.label] = list(model.objects.order_by("pk").values())
    return result


class ReviewTests(TestCase):
    def setUp(self):
        b.BackendTests.setUp(self)
        self.group = Group.objects.create(name="F05A reviewer fixture")
        self.group.permissions.add(
            Permission.objects.get(content_type__app_label="wagtailadmin", codename="access_admin")
        )
        self.reviewer = User.objects.create_user(
            username="f05a_reviewer", password="synthetic-f04b"
        )
        self.reviewer.groups.add(self.group)
        self.users["reviewer"] = self.reviewer
        self.users["editor"].groups.get().permissions.add(
            Permission.objects.get(
                content_type__app_label="fusion_f04a", codename="submit_knowledgecontent"
            )
        )
        self.task = RejectOnlyTask.objects.create(name="仅驳回测试任务")
        self.task.groups.add(self.group)
        self.workflow = Workflow.objects.create(name="单步骤实验")
        WorkflowTask.objects.create(workflow=self.workflow, task=self.task, sort_order=0)
        WorkflowContentType.objects.create(
            content_type=ContentType.objects.get_for_model(KnowledgeContent), workflow=self.workflow
        )
        self.login("editor")
        response = self.client.post(self.edit_url, self.data())
        self.assertEqual(response.status_code, 302)
        self.v2 = KnowledgeContent.objects.get(pk=self.pk).latest_revision_id

    login = b.BackendTests.login
    data = b.BackendTests.data
    url = b.BackendTests.url

    def tearDown(self):
        b.BackendTests.tearDown(self)
        self.assertEqual(read_live(self.pk)["body"], "正文1")

    def post(self, kind, **extra):
        values = (
            {"revision_id": self.v2}
            if kind == "submit"
            else {"task_state_id": self.state().current_task_state_id, "comment": "请补充"}
        )
        values.update(extra)
        values.setdefault("csrfmiddlewaretoken", self.client.cookies["csrftoken"].value)
        return self.client.post(reverse("f05a_" + kind, args=[self.pk]), values)

    def state(self):
        return WorkflowState.objects.get(
            object_id=str(self.pk), base_content_type=KnowledgeContent.get_base_content_type()
        )

    def submit_ok(self):
        self.assertEqual(self.post("submit").status_code, 302)
        state = self.state()
        self.assertEqual(state.status, "in_progress")
        self.assertEqual(state.current_task_state.revision_id, self.v2)
        self.assertEqual(state.requested_by_id, self.users["editor"].pk)
        return state

    def test_migrations_and_workflow_binding(self):
        executor = MigrationExecutor(connection)
        self.assertEqual(executor.migration_plan(executor.loader.graph.leaf_nodes()), [])
        self.assertIn(
            ("fusion_f04a", "0002_alter_knowledgecontent_options"),
            executor.loader.applied_migrations,
        )
        self.assertIn(("fusion_f05a", "0001_initial"), executor.loader.applied_migrations)
        self.assertEqual(
            KnowledgeContent.objects.get(pk=self.pk).get_workflow().pk, self.workflow.pk
        )
        self.assertIsInstance(self.task.specific, RejectOnlyTask)

    def test_submit_reject_edit_resubmit_preserves_revision_records(self):
        page = self.client.get(reverse("f05a_review", args=[self.pk]))
        self.assertContains(page, 'name="revision_id"')
        state = self.submit_ok()
        old_task_id = state.current_task_state_id
        self.assertEqual(read_live(self.pk)["body"], "正文1")
        self.login("reviewer")
        self.assertEqual(self.post("reject").status_code, 302)
        self.assertEqual(self.state().status, "needs_changes")
        old = TaskState.objects.get(pk=old_task_id)
        self.assertEqual(old.status, "rejected")
        self.assertEqual(old.finished_by_id, self.reviewer.pk)
        self.assertEqual(old.comment, "请补充")
        old_record = TaskState.objects.filter(pk=old_task_id).values().get()
        old_revision = Revision.objects.filter(pk=self.v2).values().get()
        self.login("editor")
        self.assertEqual(self.client.post(self.edit_url, self.data(body="V3")).status_code, 302)
        v3 = KnowledgeContent.objects.get(pk=self.pk).latest_revision_id
        self.assertNotEqual(v3, self.v2)
        before = snapshot()
        self.assertEqual(self.post("submit").status_code, 409)
        self.assertEqual(snapshot(), before)
        self.assertEqual(self.post("submit", revision_id=v3).status_code, 302)
        current = self.state()
        self.assertEqual(current.pk, state.pk)  # 原生 resume，同一工作流新任务记录。
        self.assertNotEqual(current.current_task_state_id, old_task_id)
        self.assertEqual(current.current_task_state.revision_id, v3)
        self.login("reviewer")
        before = snapshot()
        self.assertEqual(self.post("reject", task_state_id=old_task_id).status_code, 409)
        self.assertEqual(snapshot(), before)
        self.assertEqual(TaskState.objects.filter(pk=old_task_id).values().get(), old_record)
        self.assertEqual(Revision.objects.filter(pk=self.v2).values().get(), old_revision)

    def test_duplicates_and_finished_tasks_are_noop(self):
        self.submit_ok()
        before = snapshot()
        self.assertEqual(self.post("submit").status_code, 409)
        self.assertEqual(snapshot(), before)
        self.login("reviewer")
        self.assertEqual(self.post("reject").status_code, 302)
        before = snapshot()
        self.assertEqual(self.post("reject").status_code, 409)
        self.assertEqual(snapshot(), before)
        self.login("editor")
        self.assertEqual(self.post("submit").status_code, 409)
        self.assertEqual(snapshot(), before)

    def test_pending_review_blocks_old_form_and_superuser_save(self):
        self.assertEqual(self.client.get(self.edit_url).status_code, 200)
        self.submit_ok()
        for role in ("editor", "super"):
            self.login(role)
            before = snapshot()
            self.assertEqual(self.client.post(self.edit_url, self.data()).status_code, 409)
            self.assertEqual(snapshot(), before)

    def test_missing_submit_or_reject_qualification(self):
        permission = Permission.objects.get(
            content_type__app_label="fusion_f04a", codename="submit_knowledgecontent"
        )
        self.users["editor"].groups.get().permissions.remove(permission)
        self.login("editor")
        before = snapshot()
        self.assertRedirects(self.post("submit"), "/cms/", fetch_redirect_response=False)
        self.assertEqual(snapshot(), before)
        self.users["editor"].groups.get().permissions.add(permission)
        for role in ("entry", "viewer", "reviewer"):
            self.login(role)
            before = snapshot()
            response = self.post("submit")
            self.assertIn(response.status_code, (302, 403))
            if response.status_code == 302:
                self.assertEqual(response.url, "/cms/")
            self.assertEqual(snapshot(), before)
        self.login("editor")
        self.submit_ok()
        for role in ("editor", "entry", "super"):
            self.login(role)
            before = snapshot()
            response = self.post("reject")
            self.assertIn(response.status_code, (302, 403))
            if response.status_code == 302:
                self.assertEqual(response.url, "/cms/")
            self.assertEqual(snapshot(), before)

    def test_account_state_changes_block_existing_sessions(self):
        for changes in (
            {"is_active": False},
            {"account_status": "disabled"},
            {"account_status": "departed"},
        ):
            User.objects.filter(pk=self.users["editor"].pk).update(
                is_active=True, account_status="active"
            )
            self.login("editor")
            User.objects.filter(pk=self.users["editor"].pk).update(**changes)
            before = snapshot()
            self.assertEqual(self.post("submit").status_code, 302)
            self.assertEqual(snapshot(), before)
        User.objects.filter(pk=self.users["editor"].pk).update(
            is_active=True, account_status="active"
        )
        self.login("editor")
        self.submit_ok()
        for changes in (
            {"is_active": False},
            {"account_status": "disabled"},
            {"account_status": "departed"},
        ):
            User.objects.filter(pk=self.reviewer.pk).update(is_active=True, account_status="active")
            self.login("reviewer")
            User.objects.filter(pk=self.reviewer.pk).update(**changes)
            before = snapshot()
            response = self.post("reject")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/cms/login/", response.url)
            self.assertEqual(snapshot(), before)

    def test_foreign_stale_revision_and_forged_fields(self):
        other = KnowledgeContent.objects.create(article=self.other, title="其他", body="其他")
        foreign = other.save_revision(user=self.user)
        for revision_id in (foreign.pk, self.revision_id, 999999):
            before = snapshot()
            self.assertEqual(self.post("submit", revision_id=revision_id).status_code, 409)
            self.assertEqual(snapshot(), before)
        for extra in (
            {"requested_by": self.reviewer.pk},
            {"status": "approved"},
            {"action-publish": "1"},
            {"task_state_id": "1"},
        ):
            before = snapshot()
            self.assertEqual(self.post("submit", **extra).status_code, 400)
            self.assertEqual(snapshot(), before)
        self.submit_ok()
        self.login("reviewer")
        for task_id in (999999, self.state().current_task_state_id + 1):
            before = snapshot()
            self.assertEqual(self.post("reject", task_state_id=task_id).status_code, 409)
            self.assertEqual(snapshot(), before)
        before = snapshot()
        self.assertEqual(self.post("reject", status="approved").status_code, 400)
        self.assertEqual(snapshot(), before)

    def test_other_object_task_cannot_be_rejected(self):
        state = self.submit_ok()
        other = KnowledgeContent.objects.create(article=self.other, title="其他", body="其他")
        revision = other.save_revision(user=self.user)
        url = reverse("f05a_submit", args=[other.pk])
        self.assertEqual(
            self.client.post(
                url,
                {
                    "revision_id": revision.pk,
                    "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
                },
            ).status_code,
            302,
        )
        foreign = other.workflow_states.get().current_task_state_id
        self.login("reviewer")
        before = snapshot()
        self.assertEqual(self.post("reject", task_state_id=foreign).status_code, 409)
        self.assertEqual(snapshot(), before)
        self.assertEqual(self.state().current_task_state_id, state.current_task_state_id)

    def test_csrf_rejects_writes(self):
        for token in ("", "wrong"):
            before = snapshot()
            self.assertEqual(self.post("submit", csrfmiddlewaretoken=token).status_code, 403)
            self.assertEqual(snapshot(), before)
        self.submit_ok()
        self.login("reviewer")
        for token in ("", "wrong"):
            before = snapshot()
            self.assertEqual(self.post("reject", csrfmiddlewaretoken=token).status_code, 403)
            self.assertEqual(snapshot(), before)
        self.assertEqual(self.post("reject").status_code, 302)

    def test_mid_submit_and_reject_failures_roll_back(self):
        before = snapshot()
        with patch("wagtail.models.workflows.log", side_effect=RuntimeError("提交中途故障")):
            with self.assertRaises(RuntimeError):
                self.post("submit")
        self.assertEqual(snapshot(), before)
        self.submit_ok()
        self.login("reviewer")
        before = snapshot()
        with patch.object(
            TaskState, "log_state_change_action", side_effect=RuntimeError("驳回中途故障")
        ):
            with self.assertRaises(RuntimeError):
                self.post("reject")
        self.assertEqual(snapshot(), before)

    def test_closed_native_workflow_actions_and_finish_guard(self):
        state = self.submit_ok()
        self.login("super")
        before = snapshot()
        urls = [
            self.url("workflow_action", self.pk, "approve", state.current_task_state_id),
            self.url("workflow_action", self.pk, "reject", state.current_task_state_id),
            self.url(
                "collect_workflow_action_data", self.pk, "approve", state.current_task_state_id
            ),
            self.url("confirm_workflow_cancellation", self.pk),
            self.url("workflow_history", self.pk),
            self.url("workflow_history_detail", self.pk, state.pk),
            "/cms/workflows/list/",
            f"/cms/workflows/edit/{self.workflow.pk}/",
            f"/cms/workflows/tasks/edit/{self.task.pk}/",
            f"/cms/groups/{self.group.pk}/",
            f"/admin/auth/group/{self.group.pk}/change/",
            reverse("f05a_review", args=[self.pk]).replace("review/", "approve/"),
        ]
        urls += [
            self.url("add"),
            self.url("copy", self.pk),
            self.url("delete", self.pk),
            self.url("unpublish", self.pk),
            self.url("revisions_revert", self.pk, self.v2),
            self.url("revisions_unschedule", self.pk, self.v2),
            f"/cms/bulk/fusion_f04a/knowledgecontent/delete/?id={self.pk}",
        ]
        for key in (
            "action-publish",
            "action-submit",
            "action-cancel-workflow",
            "action-restart-workflow",
            "action-workflow-action",
            "action-schedule",
            "overwrite_revision_id",
        ):
            response = self.client.post(self.edit_url, self.data(**{key: "1"}))
            self.assertEqual(response.status_code, 403)
            self.assertEqual(snapshot(), before)
        for url in urls:
            for method in ("get", "post"):
                response = getattr(self.client, method)(url, self.data())
                self.assertEqual(response.status_code, 403, url)
                self.assertEqual(snapshot(), before)
        with self.assertRaises(PermissionDenied):
            self.task.on_action(
                TaskState.objects.get(pk=state.current_task_state_id),
                self.users["super"],
                "approve",
            )
        with self.assertRaises(PermissionDenied):
            WorkflowState.objects.get(pk=state.pk).finish(user=self.users["super"])
        self.assertEqual(snapshot(), before)
