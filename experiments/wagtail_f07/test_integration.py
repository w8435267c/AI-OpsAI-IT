"""单篇导入到重新审核、发布及员工读取的合成集成证据。"""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse
from wagtail.models import (
    Revision,
    TaskState,
    Workflow,
    WorkflowContentType,
    WorkflowState,
    WorkflowTask,
)

from apps.knowledge.models import Article, ArticleAudience, ArticleVersion, ReviewRecord
from apps.knowledge.tests.test_selectors import _add_audience, _mk_user
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f05a.models import RejectOnlyTask, TaskSubmission
from experiments.wagtail_f05a.services import submit
from experiments.wagtail_f05b.services import ApprovalRejected, approve_review
from experiments.wagtail_f06.readers import get_employee_article_detail

from . import test_import as fixtures
from .import_service import import_article
from .models import ImportedVersionSource


def legacy_state():
    return {
        model._meta.label: list(model.objects.order_by("pk").values())
        for model in (Article, ArticleVersion, ReviewRecord, ArticleAudience)
    }


def imported_state():
    return list(ImportedVersionSource.objects.order_by("pk").values())


class ImportedReviewReadIntegrationTests(TestCase):
    def setUp(self):
        fixtures.FirstImportTests.setUp(self)
        self.outsider = _mk_user()
        Article.objects.filter(pk=self.article.pk).update(audience_policy="restricted")
        _add_audience(self.article, "user", "allow", user=self.employee)
        self.original = legacy_state()

        self.editor = _mk_user()
        self.review_submitter = _mk_user()
        self.approver = _mk_user()
        self.review_group = Group.objects.create(name="F07C synthetic reviewers")
        self.review_group.permissions.add(
            Permission.objects.get(content_type__app_label="wagtailadmin", codename="access_admin")
        )
        for user in (self.editor, self.review_submitter, self.approver):
            user.groups.add(self.review_group)
        for user in (self.editor, self.review_submitter):
            for app, code in (
                ("wagtailadmin", "access_admin"),
                ("fusion_f04a", "change_knowledgecontent"),
                ("fusion_f04a", "submit_knowledgecontent"),
            ):
                user.user_permissions.add(
                    Permission.objects.get(content_type__app_label=app, codename=code)
                )
        self.task = RejectOnlyTask.objects.create(name="F07C review")
        self.task.groups.add(self.review_group)
        workflow = Workflow.objects.create(name="F07C single task workflow")
        WorkflowTask.objects.create(workflow=workflow, task=self.task, sort_order=0)
        WorkflowContentType.objects.create(
            content_type=ContentType.objects.get_for_model(KnowledgeContent), workflow=workflow
        )

    def assert_original_unchanged(self):
        self.assertEqual(legacy_state(), self.original)

    def save_draft(self, content, *, title, summary, body):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.editor)
        viewset = KnowledgeContent.snippet_viewset
        url = reverse(viewset.get_url_name("edit"), args=[content.pk])
        self.assertEqual(client.get(url).status_code, 200)
        response = client.post(
            url,
            {
                "title": title,
                "summary": summary,
                "body": body,
                "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            },
        )
        self.assertEqual(response.status_code, 302)
        content.refresh_from_db()
        return Revision.objects.get(pk=content.latest_revision_id)

    def test_import_review_publish_read_and_repeat_import(self):
        imported = import_article(self.article.pk, self.importer)
        content = KnowledgeContent.objects.get(pk=imported.content_id)
        self.assertEqual(
            imported.revision_ids,
            tuple(content.revisions.order_by("pk").values_list("pk", flat=True)),
        )
        self.assertFalse(content.live)
        self.assertIsNone(content.live_revision_id)
        self.assertIsNone(get_employee_article_detail(self.employee, self.article.pk))
        self.assertEqual(TaskState.objects.count(), 0)
        self.assertEqual(TaskSubmission.objects.count(), 0)
        source_before = imported_state()
        imported_revisions = list(
            Revision.objects.filter(pk__in=imported.revision_ids).order_by("pk").values()
        )
        self.assert_original_unchanged()

        reviewed = self.save_draft(
            content,
            title="导入确认稿",
            summary="重新审核摘要",
            body=content.body,
        )
        self.assertEqual(reviewed.user_id, self.editor.pk)
        self.assertNotIn(reviewed.pk, imported.revision_ids)
        self.assertEqual(imported_state(), source_before)
        self.assertEqual(
            list(Revision.objects.filter(pk__in=imported.revision_ids).order_by("pk").values()),
            imported_revisions,
        )
        self.assertIsNone(get_employee_article_detail(self.employee, self.article.pk))

        workflow = submit(content.pk, reviewed.pk, self.review_submitter)
        task_id = workflow.current_task_state_id
        submission = TaskSubmission.objects.get(task_state_id=task_id)
        self.assertEqual(submission.revision_id, reviewed.pk)
        self.assertEqual(submission.submitted_by_id, self.review_submitter.pk)
        for actor, reason in (
            (self.editor, "受审修订创建者"),
            (self.review_submitter, "本次审核提交人"),
        ):
            with self.subTest(actor=actor.username):
                with self.assertRaisesRegex(ApprovalRejected, reason):
                    approve_review(task_id, actor)
        self.assertIsNone(get_employee_article_detail(self.employee, self.article.pk))

        approve_review(task_id, self.approver)
        content.refresh_from_db()
        workflow.refresh_from_db()
        task = TaskState.objects.get(pk=task_id)
        self.assertEqual(task.status, TaskState.STATUS_APPROVED)
        self.assertEqual(workflow.status, WorkflowState.STATUS_APPROVED)
        self.assertTrue(content.live)
        self.assertEqual(content.live_revision_id, reviewed.pk)
        detail = get_employee_article_detail(self.employee, self.article.pk)
        self.assertIsNotNone(detail)
        self.assertEqual(
            (detail.revision_id, detail.title, detail.summary, detail.body),
            (reviewed.pk, "导入确认稿", "重新审核摘要", reviewed.content["body"]),
        )
        self.assertIsNone(get_employee_article_detail(self.outsider, self.article.pk))

        later = self.save_draft(
            content,
            title="尚未审核的新草稿",
            summary="不可见摘要",
            body="不可见正文",
        )
        self.assertNotEqual(later.pk, reviewed.pk)
        detail = get_employee_article_detail(self.employee, self.article.pk)
        self.assertEqual(
            (detail.revision_id, detail.title, detail.summary, detail.body),
            (reviewed.pk, "导入确认稿", "重新审核摘要", reviewed.content["body"]),
        )
        before_repeat = {
            "content": list(KnowledgeContent.objects.values()),
            "revisions": list(Revision.objects.order_by("pk").values()),
            "sources": imported_state(),
            "tasks": list(TaskState.objects.order_by("pk").values()),
            "workflows": list(WorkflowState.objects.order_by("pk").values()),
            "submissions": list(TaskSubmission.objects.order_by("pk").values()),
        }
        self.assertEqual(import_article(self.article.pk, self.importer), imported)
        after_repeat = {
            "content": list(KnowledgeContent.objects.values()),
            "revisions": list(Revision.objects.order_by("pk").values()),
            "sources": imported_state(),
            "tasks": list(TaskState.objects.order_by("pk").values()),
            "workflows": list(WorkflowState.objects.order_by("pk").values()),
            "submissions": list(TaskSubmission.objects.order_by("pk").values()),
        }
        self.assertEqual(after_repeat, before_repeat)
        self.assertEqual(imported_state(), source_before)
        self.assert_original_unchanged()
        print(
            f"F07C ids: C={content.pk}; imported={imported.revision_ids}; "
            f"reviewed={reviewed.pk}; later={later.pk}; task={task_id}"
        )
