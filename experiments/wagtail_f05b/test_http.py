"""真实 Django 客户端 + CSRF；不重复服务层故障注入。"""

from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from wagtail.actions.publish_revision import PublishRevisionAction
from wagtail.models import ModelLogEntry, TaskState, WorkflowState

from apps.accounts.models import User
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.tests import legacy_snapshot
from experiments.wagtail_f04a.versions import read_live
from experiments.wagtail_f04b.views import closed_operation
from experiments.wagtail_f05a.services import reject, submit
from experiments.wagtail_f05a.tests import snapshot

from . import services, test_services


class ApprovalHTTPTests(TestCase):
    login = test_services.ApprovalTests.login
    data = test_services.ApprovalTests.data
    url = test_services.ApprovalTests.url
    post_submit = test_services.ApprovalTests.post_submit
    tearDown = test_services.ApprovalTests.tearDown

    def setUp(self):
        test_services.ApprovalTests.setUp(self)
        self.login("reviewer")
        self.approve_url = reverse("f05b_approve", args=[self.ts_id])
        self.review_url = reverse("f05b_review", args=[self.ts_id])

    def csrf(self):
        return {"csrfmiddlewaretoken": self.client.cookies["csrftoken"].value}

    def unchanged(self, method, url, data=None, status=403):
        before = snapshot()
        response = getattr(self.client, method)(url, self.csrf() if data is None else data)
        self.assertEqual(response.status_code, status)
        self.assertEqual(snapshot(), before)
        return response

    def test_form_and_valid_post_call_service_once(self):
        page = self.unchanged("get", self.review_url, data={}, status=200)
        self.assertContains(page, 'method="post"')
        self.assertContains(page, 'action="' + self.approve_url + '"')
        self.assertContains(page, 'name="csrfmiddlewaretoken"')
        self.assertContains(page, "批准并发布本次修订")
        self.assertContains(page, "V2")
        self.assertNotContains(page, 'name="revision_id"')
        before = ModelLogEntry.objects.filter(action="wagtail.publish").count()
        with patch.object(services, "approve_review", wraps=services.approve_review) as spy:
            response = self.client.post(self.approve_url, self.csrf())
        self.assertContains(response, "批准成功")
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(spy.call_args.args[0], self.ts_id)
        self.assertEqual(spy.call_args.args[1].pk, self.reviewer.pk)
        self.assertEqual(read_live(self.pk)["title"], "V2")
        self.assertEqual(ModelLogEntry.objects.filter(action="wagtail.publish").count(), before + 1)
        self.unchanged("post", self.approve_url, status=409)

    def test_listing_hook_renders_eligible_link_only(self):
        self.group.permissions.add(
            Permission.objects.get(
                content_type__app_label="fusion_f04a", codename="view_knowledgecontent"
            )
        )
        page = self.client.get(self.url("list"))
        self.assertContains(page, self.review_url)
        self.assertContains(page, "审核并批准")
        self.login("editor")
        page = self.client.get(self.url("list"))
        self.assertNotContains(page, self.review_url)
        self.unchanged("get", self.review_url, data={}, status=403)

    def test_get_and_invalid_csrf_never_write(self):
        self.unchanged("get", self.approve_url, data={}, status=405)
        self.unchanged("post", self.approve_url, data={}, status=403)
        self.unchanged(
            "post", self.approve_url, data={"csrfmiddlewaretoken": "invalid"}, status=403
        )

    def test_anonymous_and_invalid_account_sessions(self):
        for values in (
            {"is_active": False},
            {"account_status": "disabled"},
            {"account_status": "departed"},
        ):
            self.login("reviewer")
            User.objects.filter(pk=self.reviewer.pk).update(**values)
            response = self.unchanged("post", self.approve_url, status=302)
            self.assertIn("/cms/login/", response.url)
            User.objects.filter(pk=self.reviewer.pk).update(is_active=True, account_status="active")
        self.client = Client(enforce_csrf_checks=True)
        self.client.get("/cms/login/")
        response = self.unchanged("post", self.approve_url, status=302)
        self.assertIn("/cms/login/", response.url)

    def test_group_revoked_after_form_was_opened(self):
        self.assertEqual(self.client.get(self.review_url).status_code, 200)
        self.reviewer.groups.remove(self.group)
        # 保留后台准入，验证确实由任务组校验拒绝。
        self.reviewer.user_permissions.add(
            Permission.objects.get(content_type__app_label="wagtailadmin", codename="access_admin")
        )
        response = self.unchanged("post", self.approve_url)
        self.assertContains(response, "审核组", status_code=403)

    def test_author_submitter_and_superuser_cannot_self_approve(self):
        publish = Permission.objects.get(
            content_type__app_label="fusion_f04a", codename="publish_knowledgecontent"
        )
        for name in ("editor", "submitter", "super"):
            actor = self.users[name]
            actor.groups.first().permissions.add(publish) if actor.groups.exists() else None
            for elevated in (False, True) if name != "super" else (True,):
                User.objects.filter(pk=actor.pk).update(is_superuser=elevated)
                self.login(name)
                self.unchanged("post", self.approve_url)
        self.users["viewer"].groups.get().permissions.add(publish)
        self.login("viewer")
        self.unchanged("post", self.approve_url)

    def test_forged_fields_rejected(self):
        for key in (
            "actor",
            "actor_id",
            "user_id",
            "revision_id",
            "task_state_id",
            "content_id",
            "action-publish",
        ):
            with self.subTest(field=key):
                self.unchanged(
                    "post", self.approve_url, {**self.csrf(), key: self.creator.pk}, status=400
                )
        self.unchanged("post", self.approve_url + "?revision_id=1", status=400)

    def test_other_task_id_uses_actual_qualification(self):
        other = KnowledgeContent.objects.create(
            article=self.other, title="另一任务", body="其他正文"
        )
        revision = other.save_revision(user=self.creator)
        state = submit(other.pk, revision.pk, self.submitter)
        url = reverse("f05b_approve", args=[state.current_task_state_id])
        self.assertEqual(self.client.post(url, self.csrf()).status_code, 200)
        self.assertEqual(read_live(other.pk)["title"], "另一任务")
        self.assertEqual(read_live(self.pk)["title"], "V1")
        self.assertEqual(TaskState.objects.get(pk=self.ts_id).status, "in_progress")

    def test_cross_object_binding_and_missing_task_rejected(self):
        other = KnowledgeContent.objects.create(
            article=self.other, title="错误绑定", body="其他正文"
        )
        revision = other.save_revision(user=self.creator)
        TaskState.objects.filter(pk=self.ts_id).update(revision=revision)
        self.unchanged("post", self.approve_url, status=409)
        self.unchanged("post", reverse("f05b_approve", args=[999999]), status=409)

    def test_stale_rejected_task_post_does_not_publish(self):
        self.assertEqual(self.client.get(self.review_url).status_code, 200)
        reject(self.pk, self.ts_id, self.reviewer, "需要修改")
        self.unchanged("post", self.approve_url, status=409)

    def test_registered_alternative_actions_stay_closed(self):
        self.login("super")
        viewset = KnowledgeContent.snippet_viewset
        for pattern in viewset.get_urlpatterns():
            if pattern.name not in {"list", "list_results", "edit", "inspect"}:
                self.assertIs(pattern.callback, closed_operation, pattern.name)
        urls = [
            self.url("workflow_action", self.pk, "approve", self.ts_id),
            self.url("collect_workflow_action_data", self.pk, "approve", self.ts_id),
            self.url("confirm_workflow_cancellation", self.pk),
            self.url("add"),
            self.url("copy", self.pk),
            self.url("delete", self.pk),
            self.url("unpublish", self.pk),
            self.url("revisions_revert", self.pk, self.v2),
            self.url("revisions_unschedule", self.pk, self.v2),
            *[
                f"/cms/bulk/fusion_f04a/knowledgecontent/{action}/?id={self.pk}"
                for action in ("publish", "unpublish", "delete")
            ],
        ]
        for url in urls:
            with self.subTest(url=url):
                self.unchanged("get", url, data={})
                self.unchanged("post", url)
        for key in (
            "action-publish",
            "action-submit",
            "action-workflow-action",
            "action-schedule",
            "action-cancel-workflow",
            "action-restart-workflow",
            "overwrite_revision_id",
        ):
            with self.subTest(action=key):
                self.unchanged("post", self.edit_url, self.data(**{key: "1"}))

    def test_http_publish_failure_rolls_back_then_retry_once(self):
        self.assertEqual(self.client.get(self.review_url).status_code, 200)
        before = (snapshot(), legacy_snapshot())
        before_publish_count = ModelLogEntry.objects.filter(action="wagtail.publish").count()

        def fail_before_publish(action, *args, **kwargs):
            # 复用服务测试的注入位置；但入口是带真实认证/CSRF 的 HTTP POST。
            state = TaskState.objects.get(pk=self.ts_id)
            self.assertEqual(state.status, "approved")
            self.assertEqual(state.finished_by_id, self.reviewer.pk)
            self.assertIsNotNone(state.finished_at)
            self.assertEqual(WorkflowState.objects.get(pk=self.ws.pk).status, "approved")
            self.assertEqual(action.revision.pk, state.revision_id)
            self.assertEqual(action.revision.pk, self.v2)
            self.assertEqual(
                KnowledgeContent.objects.get(pk=self.pk).live_revision_id, self.revision_id
            )
            raise RuntimeError("HTTP 发布完成前的合成异常")

        with (
            patch.object(services, "approve_review", wraps=services.approve_review) as service,
            patch.object(
                PublishRevisionAction,
                "_publish_revision",
                autospec=True,
                side_effect=fail_before_publish,
            ) as publishing,
        ):
            with self.assertRaisesMessage(RuntimeError, "HTTP 发布完成前的合成异常"):
                self.client.post(self.approve_url, self.csrf())
        self.assertEqual(service.call_count, 1)
        self.assertEqual(service.call_args.args[0], self.ts_id)
        self.assertEqual(service.call_args.args[1].pk, self.reviewer.pk)
        self.assertEqual(publishing.call_count, 1)
        self.assertEqual((snapshot(), legacy_snapshot()), before)
        self.assertEqual(read_live(self.pk)["title"], "V1")
        self.assertEqual(TaskState.objects.get(pk=self.ts_id).status, "in_progress")
        self.assertEqual(WorkflowState.objects.get(pk=self.ws.pk).status, "in_progress")

        response = self.client.post(self.approve_url, self.csrf())
        self.assertContains(response, "批准成功")
        self.assertEqual(TaskState.objects.get(pk=self.ts_id).status, "approved")
        self.assertEqual(WorkflowState.objects.get(pk=self.ws.pk).status, "approved")
        self.assertEqual(KnowledgeContent.objects.get(pk=self.pk).live_revision_id, self.v2)
        self.assertEqual(read_live(self.pk)["title"], "V2")
        self.assertEqual(
            ModelLogEntry.objects.filter(action="wagtail.publish").count(), before_publish_count + 1
        )
        self.assertEqual(
            ModelLogEntry.objects.filter(action="wagtail.publish", revision_id=self.v2).count(), 1
        )
        response = self.unchanged("post", self.approve_url, status=409)
        self.assertContains(response, "任务", status_code=409)
        self.assertEqual(legacy_snapshot(), before[1])
