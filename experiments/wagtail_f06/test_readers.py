"""真实提交批准夹具；只验证实验详情的组合风险。"""

from dataclasses import asdict
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from wagtail.actions.publish_revision import PublishRevisionAction
from wagtail.models import (
    Revision,
    TaskState,
    Workflow,
    WorkflowContentType,
    WorkflowState,
    WorkflowTask,
)

from apps.accounts.models import User, UserGroup, UserGroupMembership
from apps.knowledge.models import Article, ArticleAudience, KnowledgeSpace
from apps.knowledge.tests.test_selectors import _add_audience, _mk_article, _mk_user
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.tests import legacy_snapshot
from experiments.wagtail_f05a.models import RejectOnlyTask, TaskSubmission
from experiments.wagtail_f05a.services import reject, submit
from experiments.wagtail_f05a.tests import snapshot
from experiments.wagtail_f05b.services import approve_review

from .readers import get_employee_article_detail


class DetailTests(TestCase):
    def setUp(self):
        self.creator = _mk_user()
        self.submitter = _mk_user()
        self.reviewer = _mk_user()
        self.employee = _mk_user()
        for app, code in (
            ("wagtailadmin", "access_admin"),
            ("fusion_f04a", "change_knowledgecontent"),
            ("fusion_f04a", "submit_knowledgecontent"),
        ):
            self.submitter.user_permissions.add(
                Permission.objects.get(content_type__app_label=app, codename=code)
            )
        self.reviewer.user_permissions.add(
            Permission.objects.get(content_type__app_label="wagtailadmin", codename="access_admin")
        )
        self.group = Group.objects.create(name="F06 synthetic reviewers")
        self.reviewer.groups.add(self.group)
        self.task = RejectOnlyTask.objects.create(name="F06 review")
        self.task.groups.add(self.group)
        workflow = Workflow.objects.create(name="F06 workflow")
        WorkflowTask.objects.create(workflow=workflow, task=self.task, sort_order=0)
        WorkflowContentType.objects.create(
            content_type=ContentType.objects.get_for_model(KnowledgeContent), workflow=workflow
        )
        self.article = _mk_article(policy="all_employees", owner=self.creator)
        self.content = KnowledgeContent.objects.create(
            article=self.article, title="正式标题", summary="正式摘要", body="正式正文"
        )
        self.revision = self.content.save_revision(user=self.creator)
        ws = submit(self.content.pk, self.revision.pk, self.submitter)
        self.approved = approve_review(ws.current_task_state_id, self.reviewer)

    def read(self, user=None, article_id=None):
        before = (snapshot(), legacy_snapshot())
        with CaptureQueriesContext(connection) as queries:
            result = get_employee_article_detail(
                self.employee if user is None else user,
                self.article.pk if article_id is None else article_id,
            )
        self.assertEqual((snapshot(), legacy_snapshot()), before)
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries))
        return result

    def assert_live(self, user=None):
        result = self.read(user)
        self.assertIsNotNone(result)
        self.assertEqual(
            asdict(result),
            dict(
                article_id=self.article.pk,
                content_id=self.content.pk,
                revision_id=self.revision.pk,
                title="正式标题",
                summary="正式摘要",
                body="正式正文",
            ),
        )
        return result

    def draft(self):
        content = KnowledgeContent.objects.get(pk=self.content.pk)
        content.title, content.summary, content.body = (
            "秘密草稿标题",
            "秘密草稿摘要",
            "秘密草稿正文",
        )
        return content.save_revision(user=self.creator)

    def test_published_without_legacy_pointer_and_whitelist(self):
        self.article.refresh_from_db()
        self.assertIsNone(self.article.current_published_version_id)
        self.assert_live()
        self.assertEqual(self.read(article_id=str(self.article.pk)), self.read())

    def test_draft_review_and_rejection_keep_live_snapshot(self):
        revision = self.draft()
        self.assert_live()
        ws = submit(self.content.pk, revision.pk, self.submitter)
        self.assertNotEqual(ws.pk, self.approved.workflow_state_id)
        self.assert_live()
        reject(self.content.pk, ws.current_task_state_id, self.reviewer, "请修改")
        self.assert_live()

    def test_unpublished_missing_content_and_direct_publish_denied(self):
        other = _mk_article(policy="all_employees")
        self.assertIsNone(self.read(article_id=other.pk))
        obj = KnowledgeContent.objects.create(article=other, title="未审核", body="秘密")
        revision = obj.save_revision(user=self.creator)
        self.assertIsNone(self.read(article_id=other.pk))
        # 明确模拟历史直发：原生发布默认无 user 的机制，不伪装为已审核夹具。
        PublishRevisionAction(revision).execute()
        obj.refresh_from_db()
        self.assertTrue(obj.live)
        self.assertFalse(TaskState.objects.filter(revision=revision).exists())
        self.assertIsNone(self.read(article_id=other.pk))

    def test_three_policies_and_deny(self):
        self.assert_live()
        Article.objects.filter(pk=self.article.pk).update(audience_policy="restricted")
        self.assertIsNone(self.read())
        _add_audience(self.article, "user", user=self.employee)
        self.assert_live()
        Article.objects.filter(pk=self.article.pk).update(audience_policy="it_only")
        self.assertIsNone(self.read())
        group = UserGroup.objects.create(name="F06 IT audience")
        UserGroupMembership.objects.create(user=self.employee, user_group=group)
        with self.settings(KNOWLEDGE_IT_USER_GROUP_ID=group.pk):
            self.assert_live()
            _add_audience(self.article, "user", "deny", user=self.employee)
            self.assertIsNone(self.read())
        self.assertTrue(ArticleAudience.objects.filter(article=self.article).exists())

    def test_current_account_and_business_availability(self):
        for fields in (
            {"is_active": False},
            {"account_status": "disabled"},
            {"account_status": "departed"},
        ):
            with self.subTest(fields=fields):
                User.objects.filter(pk=self.employee.pk).update(**fields)
                self.assertIsNone(self.read())  # 持有旧对象仍必须重读账号。
                User.objects.filter(pk=self.employee.pk).update(
                    is_active=True, account_status="active"
                )
        for status in ("offline", "archived"):
            Article.objects.filter(pk=self.article.pk).update(article_status=status)
            self.assertIsNone(self.read())
        Article.objects.filter(pk=self.article.pk).update(article_status="active")
        KnowledgeSpace.objects.filter(pk=self.article.space_id).update(is_active=False)
        self.assertIsNone(self.read())
        KnowledgeSpace.objects.filter(pk=self.article.space_id).update(is_active=True)
        Article.objects.filter(pk=self.article.pk).update(
            effective_at=timezone.now() + timedelta(days=1)
        )
        self.assertIsNone(self.read())

    def test_roles_have_no_audience_bypass(self):
        Article.objects.filter(pk=self.article.pk).update(audience_policy="restricted")
        admin = _mk_user(is_superuser=True, is_staff=True)
        for user in (admin, self.creator, self.reviewer, self.submitter):
            self.assertIsNone(self.read(user))

    def test_historical_reviewer_can_leave_group_and_account(self):
        self.reviewer.groups.clear()
        User.objects.filter(pk=self.reviewer.pk).update(is_active=False, account_status="departed")
        self.assert_live()

    def test_bad_inputs_and_absent_reader(self):
        for user in (AnonymousUser(), User(), User(pk=self.employee.pk)):
            self.assertIsNone(self.read(user))
        for article_id in (uuid4(), "invalid", self.article, 1):
            self.assertIsNone(self.read(article_id=article_id))
        self.assertIsNone(get_employee_article_detail(None, self.article.pk))
        removed = _mk_user()
        removed_id = removed.pk
        removed.delete()
        removed.pk = removed_id
        self.assertIsNone(self.read(removed))

    def test_revision_binding_and_snapshot_corruption(self):
        row = Revision.objects.values().get(pk=self.revision.pk)
        wrong_type = ContentType.objects.get_for_model(Article).pk
        cases = [
            {"object_id": "999999"},
            {"content_type_id": wrong_type},
            {"base_content_type_id": wrong_type},
            *[
                {"content": {**row["content"], key: value}}
                for key, value in (("pk", "999999"), ("article", str(uuid4())), ("body", None))
            ],
        ]
        for fields in cases:
            with self.subTest(fields=fields):
                Revision.objects.filter(pk=self.revision.pk).update(**fields)
                self.assertIsNone(self.read())
                Revision.objects.filter(pk=self.revision.pk).update(**{k: row[k] for k in fields})
        KnowledgeContent.objects.filter(pk=self.content.pk).update(live_revision=None)
        self.assertIsNone(self.read())
        KnowledgeContent.objects.filter(pk=self.content.pk).update(
            live_revision=self.revision, live=False
        )
        self.assertIsNone(self.read())

    def test_approval_and_submission_corruption(self):
        revision = self.draft()
        for model, pk, cases in (
            (
                TaskSubmission,
                self.approved.pk,
                [{"revision_id": revision.pk}, {"submitted_by_id": self.reviewer.pk}],
            ),
            (
                TaskState,
                self.approved.pk,
                [
                    {"status": "rejected"},
                    {"finished_at": None},
                    {"finished_by_id": None},
                    {"finished_by_id": self.creator.pk},
                ],
            ),
            (
                WorkflowState,
                self.approved.workflow_state_id,
                [
                    {"status": "in_progress"},
                    {"current_task_state_id": None},
                    {"object_id": "999999"},
                    {"content_type_id": ContentType.objects.get_for_model(Article).pk},
                ],
            ),
            (Revision, self.revision.pk, [{"user_id": None}]),
        ):
            row = model.objects.values().get(pk=pk)
            for fields in cases:
                with self.subTest(model=model, fields=fields):
                    model.objects.filter(pk=pk).update(**fields)
                    self.assertIsNone(self.read())
                    model.objects.filter(pk=pk).update(**{k: row[k] for k in fields})
        TaskSubmission.objects.filter(pk=self.approved.pk).delete()
        self.assertIsNone(self.read())

    def test_unexpected_error_is_not_hidden(self):
        with patch(
            "experiments.wagtail_f06.readers.checked_revision", side_effect=RuntimeError("bug")
        ):
            with self.assertRaisesRegex(RuntimeError, "bug"):
                self.read()

    def test_cross_object_live_pointer_and_malformed_snapshot(self):
        other = _mk_article(policy="all_employees")
        obj = KnowledgeContent.objects.create(article=other, title="其他内容", body="不能泄露")
        revision = obj.save_revision(user=self.creator)
        state = submit(obj.pk, revision.pk, self.submitter)
        approve_review(state.current_task_state_id, self.reviewer)
        KnowledgeContent.objects.filter(pk=self.content.pk).update(live_revision=revision)
        self.assertIsNone(self.read())
        KnowledgeContent.objects.filter(pk=self.content.pk).update(live_revision=self.revision)
        Revision.objects.filter(pk=self.revision.pk).update(content=[])
        self.assertIsNone(self.read())
