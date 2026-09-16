"""F08C：字符串正文导入、显式转换、草稿保存、重新审核与员工读取的合成集成证据。"""

from django.test import Client, TestCase
from django.urls import reverse
from wagtail.models import ModelLogEntry, Revision, TaskState, WorkflowState

from apps.knowledge.models import ArticleVersion
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f05a.body_rules import (
    EMPTY_BODY_CODE,
    EMPTY_BODY_REASON,
    EmptyBodyRejected,
    require_nonempty_body,
)
from experiments.wagtail_f05a.models import TaskSubmission
from experiments.wagtail_f05a.services import reject, submit
from experiments.wagtail_f05b.services import ApprovalRejected, approve_review
from experiments.wagtail_f06.readers import get_employee_article_detail
from experiments.wagtail_f07 import test_integration as f07_integration
from experiments.wagtail_f07.conversion import decode_body
from experiments.wagtail_f07.import_service import import_article
from experiments.wagtail_f07.models import ImportedVersionSource

from .body_text import convert_encoded_body_to_plaintext

# 合成旧正式版本正文：普通字符串，含中文、空行、步骤与列表标记、引号、反斜杠及 JSON 外观片段。
LEGACY_PLAINTEXT = (
    "内网访问申请\n"
    "\n"
    "1. 打开钉钉工作台的 IT 服务入口。\n"
    '2. 提交"网络访问"申请并说明原因。\n'
    "- 附件：无\n"
    "- 备份路径：C:\\Temp\\说明.txt\n"
    '不是另一个节点的 JSON 外观：{"payload": "仍是普通文本"}'
)
LEGACY_DRAFT_PLAINTEXT = "较新草稿的普通文本正文"
# 派生字段只用于对照；转换成功不得来自 body_plaintext 回退。
LEGACY_DERIVED_TEXT = "不应作为正文回退的派生文本"
PADDED_PLAINTEXT = "  前置空白与制表\t\n第一行\n\n第二行\n末尾空白 \t\n"
UNSUPPORTED_REASON = "不支持自动转换，需要人工确认"


def review_snapshot():
    """内容与审核侧完整快照；旧业务记录由 F07C 的 legacy_state 覆盖。"""
    return {
        model._meta.label: list(model.objects.order_by("pk").values())
        for model in (
            KnowledgeContent,
            Revision,
            ModelLogEntry,
            ImportedVersionSource,
            TaskState,
            WorkflowState,
            TaskSubmission,
        )
    }


class PlaintextDraftReviewReadTests(TestCase):
    """复用 F07C 的夹具、权限及工作流装配；只组合现有入口，不新增服务或模型。"""

    def setUp(self):
        f07_integration.ImportedReviewReadIntegrationTests.setUp(self)

    def assert_legacy_unchanged(self):
        self.assertEqual(f07_integration.legacy_state(), self.original)

    def assert_imported_revisions_unchanged(self, imported, expected):
        self.assertEqual(
            list(Revision.objects.filter(pk__in=imported.revision_ids).order_by("pk").values()),
            expected,
        )

    def set_legacy_bodies(self, published_body, draft_body, derived=""):
        """把合成旧版本正文改为指定 payload，并以该状态重设旧记录基线。"""
        ArticleVersion.objects.filter(pk=self.published.pk).update(
            body=published_body, body_plaintext=derived
        )
        ArticleVersion.objects.filter(pk=self.draft.pk).update(body=draft_body)
        self.original = f07_integration.legacy_state()

    def post_edit(self, content, *, title, summary, body):
        """现有 Snippet 编辑 POST：真实认证、CSRF、字段白名单与保存事务。"""
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.editor)
        url = reverse(KnowledgeContent.snippet_viewset.get_url_name("edit"), args=[content.pk])
        self.assertEqual(client.get(url).status_code, 200)
        return client.post(
            url,
            {
                "title": title,
                "summary": summary,
                "body": body,
                "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            },
        )

    def save_draft(self, content, *, title, summary, body):
        response = self.post_edit(content, title=title, summary=summary, body=body)
        self.assertEqual(response.status_code, 302)
        content.refresh_from_db()
        return Revision.objects.get(pk=content.latest_revision_id)

    def import_string_bodies(self):
        self.set_legacy_bodies(
            LEGACY_PLAINTEXT, LEGACY_DRAFT_PLAINTEXT, derived=LEGACY_DERIVED_TEXT
        )
        imported = import_article(self.article.pk, self.importer)
        content = KnowledgeContent.objects.get(pk=imported.content_id)
        legacy_revision = Revision.objects.get(pk=imported.revision_ids[0])
        self.assertEqual(decode_body(legacy_revision.content["body"]), LEGACY_PLAINTEXT)
        return imported, content, legacy_revision

    def assert_no_employee_snapshot(self):
        for reader in (self.employee, self.outsider):
            with self.subTest(reader=reader.username):
                self.assertIsNone(get_employee_article_detail(reader, self.article.pk))

    def make_draft_revision(self, content, body):
        """夹具方式追加指定正文的草稿修订；不经过表单，也不改变任何表单规则。"""
        content.refresh_from_db()
        content.body = body
        content.save()
        # 与 Wagtail 的 saving_as_draft 路径一致，不在草稿阶段执行 required 校验。
        return content.save_revision(user=self.editor, clean=False)

    def start_legacy_task(self, content, revision):
        """构造旧有待审任务：直接启动现有工作流，不经过已加固的 submit()。"""
        state = content.get_workflow().start(content, user=self.review_submitter)
        TaskSubmission.objects.create(
            task_state=state.current_task_state,
            revision=revision,
            submitted_by=self.review_submitter,
        )
        return state

    def admin_client(self, user, warmup_url):
        """已登录且持有 CSRF cookie 的真实客户端；沿用现有 HTTP 入口。"""
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        self.assertEqual(client.get(warmup_url).status_code, 200)
        return client

    def csrf_post(self, client, url, **fields):
        return client.post(
            url, {**fields, "csrfmiddlewaretoken": client.cookies["csrftoken"].value}
        )

    def test_imported_string_body_becomes_reviewed_plaintext(self):
        imported, content, legacy_revision = self.import_string_bodies()
        encoded_body = legacy_revision.content["body"]
        self.assertFalse(content.live)
        self.assertIsNone(content.live_revision_id)
        self.assertEqual(TaskState.objects.count(), 0)
        self.assertEqual(TaskSubmission.objects.count(), 0)
        source_rows = f07_integration.imported_state()
        imported_revisions = list(
            Revision.objects.filter(pk__in=imported.revision_ids).order_by("pk").values()
        )
        before_convert = review_snapshot()
        self.assert_legacy_unchanged()
        self.assert_no_employee_snapshot()

        # 显式转换已确认的导入修订；不按正文“看起来像 JSON”自动判断是否转换。
        converted = convert_encoded_body_to_plaintext(encoded_body)
        self.assertTrue(converted.success)
        self.assertEqual(converted.code, "ok")
        self.assertIs(type(converted.text), str)
        self.assertEqual(converted.text, LEGACY_PLAINTEXT)
        self.assertNotEqual(converted.text, LEGACY_DERIVED_TEXT)
        self.assertIn('{"payload": "仍是普通文本"}', converted.text)
        # 转换是纯计算：不写数据库，也不产生草稿、任务或发布。
        self.assertEqual(review_snapshot(), before_convert)
        self.assert_no_employee_snapshot()

        reviewed = self.save_draft(
            content,
            title=legacy_revision.content["title"],
            summary=legacy_revision.content["summary"],
            body=converted.text,
        )
        content.refresh_from_db()
        self.assertEqual(reviewed.user_id, self.editor.pk)
        self.assertNotIn(reviewed.pk, imported.revision_ids)
        self.assertEqual(
            (reviewed.content["title"], reviewed.content["summary"], reviewed.content["body"]),
            ("旧正式版", "旧摘要", LEGACY_PLAINTEXT),
        )
        self.assertEqual(content.latest_revision_id, reviewed.pk)
        self.assertFalse(content.live)
        self.assertIsNone(content.live_revision_id)
        self.assertEqual(f07_integration.imported_state(), source_rows)
        self.assert_imported_revisions_unchanged(imported, imported_revisions)
        self.assertEqual(
            Revision.objects.get(pk=imported.revision_ids[0]).user_id, self.importer.pk
        )
        self.assert_legacy_unchanged()
        # 保存草稿不发布：批准前有权限员工也读不到任何快照。
        self.assert_no_employee_snapshot()

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
        content.refresh_from_db()
        self.assertFalse(content.live)
        self.assertIsNone(content.live_revision_id)
        self.assert_no_employee_snapshot()

        approve_review(task_id, self.approver)
        content.refresh_from_db()
        workflow.refresh_from_db()
        self.assertEqual(TaskState.objects.get(pk=task_id).status, TaskState.STATUS_APPROVED)
        self.assertEqual(workflow.status, WorkflowState.STATUS_APPROVED)
        self.assertTrue(content.live)
        self.assertEqual(content.live_revision_id, reviewed.pk)
        expected = (reviewed.pk, "旧正式版", "旧摘要", LEGACY_PLAINTEXT)
        detail = get_employee_article_detail(self.employee, self.article.pk)
        self.assertEqual((detail.revision_id, detail.title, detail.summary, detail.body), expected)
        self.assertEqual(detail.body, converted.text)
        self.assertIsNone(get_employee_article_detail(self.outsider, self.article.pk))

        later = self.save_draft(
            content, title="尚未审核的新草稿", summary="不可见摘要", body="不可见正文"
        )
        content.refresh_from_db()
        self.assertNotEqual(later.pk, reviewed.pk)
        self.assertEqual(
            (content.latest_revision_id, content.live_revision_id), (later.pk, reviewed.pk)
        )
        detail = get_employee_article_detail(self.employee, self.article.pk)
        self.assertEqual((detail.revision_id, detail.title, detail.summary, detail.body), expected)
        self.assertIsNone(get_employee_article_detail(self.outsider, self.article.pk))

        before_repeat = review_snapshot()
        self.assertEqual(import_article(self.article.pk, self.importer), imported)
        self.assertEqual(review_snapshot(), before_repeat)
        self.assertEqual(f07_integration.imported_state(), source_rows)
        self.assert_imported_revisions_unchanged(imported, imported_revisions)
        self.assert_legacy_unchanged()
        content.refresh_from_db()
        self.assertEqual(
            (content.latest_revision_id, content.live_revision_id), (later.pk, reviewed.pk)
        )
        detail = get_employee_article_detail(self.employee, self.article.pk)
        self.assertEqual((detail.revision_id, detail.body), (reviewed.pk, LEGACY_PLAINTEXT))
        self.assertIsNone(get_employee_article_detail(self.outsider, self.article.pk))
        print(
            f"F08C ids: C={content.pk}; imported={imported.revision_ids}; "
            f"reviewed={reviewed.pk}; later={later.pk}; task={task_id}"
        )

    def test_plaintext_text_boundaries_through_existing_form(self):
        self.set_legacy_bodies(PADDED_PLAINTEXT, "")
        imported = import_article(self.article.pk, self.importer)
        content = KnowledgeContent.objects.get(pk=imported.content_id)
        padded_revision = Revision.objects.get(pk=imported.revision_ids[0])
        empty_revision = Revision.objects.get(pk=imported.revision_ids[1])
        source_rows = f07_integration.imported_state()
        imported_revisions = list(
            Revision.objects.filter(pk__in=imported.revision_ids).order_by("pk").values()
        )

        padded = convert_encoded_body_to_plaintext(padded_revision.content["body"])
        self.assertTrue(padded.success)
        self.assertEqual(padded.code, "ok")
        # 纯函数原样返回，包括首尾空白与制表；表单保存是另一个环节。
        self.assertEqual(padded.text, PADDED_PLAINTEXT)
        saved = self.save_draft(
            content,
            title=padded_revision.content["title"],
            summary=padded_revision.content["summary"],
            body=padded.text,
        )
        self.assertEqual(saved.user_id, self.editor.pk)
        self.assertNotIn(saved.pk, imported.revision_ids)
        # 实际表单行为：CharField(strip=True) 去掉首尾空白，内部制表、换行与空行原样保留。
        self.assertEqual(saved.content["body"], PADDED_PLAINTEXT.strip())
        self.assertNotEqual(saved.content["body"], padded.text)
        self.assertIn("制表\t\n第一行\n\n第二行", saved.content["body"])
        self.assertFalse(saved.content["body"][:1].isspace())
        self.assertFalse(saved.content["body"][-1:].isspace())
        content.refresh_from_db()
        self.assertFalse(content.live)
        self.assertIsNone(content.live_revision_id)
        self.assert_no_employee_snapshot()

        empty = convert_encoded_body_to_plaintext(empty_revision.content["body"])
        self.assertTrue(empty.success)
        self.assertEqual(empty.code, "ok")
        self.assertEqual(empty.text, "")
        # 现有正文表单规则本身要求非空：独立构造同一表单类会拒绝空正文。
        form_class = KnowledgeContent.snippet_viewset.get_form_class()
        standalone = form_class(
            data={
                "title": empty_revision.content["title"],
                "summary": empty_revision.content["summary"],
                "body": empty.text,
            }
        )
        self.assertFalse(standalone.is_valid())
        self.assertEqual(list(standalone.errors), ["body"])
        self.assertEqual(
            standalone.errors["body"],
            [standalone.fields["body"].error_messages["required"]],
        )
        # 实际行为：现有草稿保存 POST 属于 saving_as_draft，Wagtail 推迟 required 校验并以
        # clean=False 追加修订，因此转换成功的空字符串仍会保存为新草稿。本轮只如实记录，
        # 不放宽也不改写任何表单规则。
        accepted = self.post_edit(
            content,
            title=empty_revision.content["title"],
            summary=empty_revision.content["summary"],
            body=empty.text,
        )
        self.assertEqual(accepted.status_code, 302)
        content.refresh_from_db()
        empty_draft = Revision.objects.get(pk=content.latest_revision_id)
        self.assertNotEqual(empty_draft.pk, saved.pk)
        self.assertNotIn(empty_draft.pk, imported.revision_ids)
        self.assertEqual(empty_draft.user_id, self.editor.pk)
        self.assertEqual(empty_draft.content["body"], "")
        self.assertEqual(Revision.objects.count(), len(imported.revision_ids) + 2)
        # 空草稿同样不发布：无正式快照，审核侧没有新增记录，导入修订与来源保持不变。
        self.assertFalse(content.live)
        self.assertIsNone(content.live_revision_id)
        self.assertEqual(TaskState.objects.count(), 0)
        self.assertEqual(TaskSubmission.objects.count(), 0)
        self.assertEqual(WorkflowState.objects.count(), 0)
        self.assertEqual(f07_integration.imported_state(), source_rows)
        self.assert_imported_revisions_unchanged(imported, imported_revisions)
        self.assert_legacy_unchanged()
        self.assert_no_employee_snapshot()
        print(
            f"F08C boundaries: padded_draft={saved.pk}; "
            f"stripped={saved.content['body']!r}; empty_draft={empty_draft.pk}; "
            f"required_error={standalone.errors['body']!r}"
        )

    def test_empty_plaintext_draft_cannot_be_submitted_or_approved(self):
        """缺陷回归：空正文草稿仍可暂存，但不能提交审核，也不能被批准发布。"""
        self.set_legacy_bodies("", LEGACY_DRAFT_PLAINTEXT)
        imported = import_article(self.article.pk, self.importer)
        content = KnowledgeContent.objects.get(pk=imported.content_id)
        legacy_revision = Revision.objects.get(pk=imported.revision_ids[0])
        source_rows = f07_integration.imported_state()
        imported_revisions = list(
            Revision.objects.filter(pk__in=imported.revision_ids).order_by("pk").values()
        )
        converted = convert_encoded_body_to_plaintext(legacy_revision.content["body"])
        self.assertTrue(converted.success)
        self.assertEqual(converted.code, "ok")
        self.assertEqual(converted.text, "")

        # 草稿暂存机制未修改：转换成功的空正文仍可作为新草稿保存。
        draft = self.save_draft(
            content,
            title=legacy_revision.content["title"],
            summary=legacy_revision.content["summary"],
            body=converted.text,
        )
        self.assertEqual(draft.content["body"], "")
        self.assertEqual(draft.user_id, self.editor.pk)
        content.refresh_from_db()
        self.assertEqual(content.latest_revision_id, draft.pk)
        self.assertFalse(content.live)
        self.assertIsNone(content.live_revision_id)
        self.assert_no_employee_snapshot()

        # 提交审核在写入任务、工作流或提交记录之前被共用正文规则拒绝。
        before = review_snapshot()
        with self.assertRaises(EmptyBodyRejected) as caught:
            submit(content.pk, draft.pk, self.review_submitter)
        self.assertEqual(caught.exception.code, EMPTY_BODY_CODE)
        self.assertEqual(str(caught.exception), EMPTY_BODY_REASON)
        self.assertEqual(review_snapshot(), before)
        self.assertEqual(TaskState.objects.count(), 0)
        self.assertEqual(TaskSubmission.objects.count(), 0)
        self.assertEqual(WorkflowState.objects.count(), 0)
        self.assert_no_employee_snapshot()

        # 真实提交 POST：中文业务拒绝与 409，不是 500。
        edit_url = reverse(KnowledgeContent.snippet_viewset.get_url_name("edit"), args=[content.pk])
        editor_client = self.admin_client(self.editor, edit_url)
        submit_response = self.csrf_post(
            editor_client, reverse("f05a_submit", args=[content.pk]), revision_id=draft.pk
        )
        self.assertEqual(submit_response.status_code, 409)
        self.assertEqual(submit_response.content.decode(), EMPTY_BODY_REASON)
        self.assertEqual(review_snapshot(), before)

        # 夹具构造旧有空正文待审任务：批准被拒绝，任务、工作流与正式内容保持原状。
        state = self.start_legacy_task(content, draft)
        task_id = state.current_task_state_id
        self.assertEqual(TaskState.objects.get(pk=task_id).revision_id, draft.pk)
        legacy_task = review_snapshot()
        with self.assertRaises(ApprovalRejected) as denied:
            approve_review(task_id, self.approver)
        self.assertEqual(denied.exception.code, EMPTY_BODY_CODE)
        self.assertEqual(str(denied.exception), EMPTY_BODY_REASON)
        self.assertEqual(review_snapshot(), legacy_task)
        self.assertEqual(TaskState.objects.get(pk=task_id).status, TaskState.STATUS_IN_PROGRESS)
        self.assertEqual(
            WorkflowState.objects.get(pk=state.pk).status, WorkflowState.STATUS_IN_PROGRESS
        )
        content.refresh_from_db()
        self.assertFalse(content.live)
        self.assertIsNone(content.live_revision_id)
        self.assert_no_employee_snapshot()

        # 真实批准 POST：同样返回中文业务拒绝与 409，不是 500。
        review_url = reverse("f05b_review", args=[task_id])
        reviewer_client = self.admin_client(self.approver, review_url)
        approve_response = self.csrf_post(reviewer_client, reverse("f05b_approve", args=[task_id]))
        self.assertEqual(approve_response.status_code, 409)
        self.assertEqual(approve_response.content.decode(), EMPTY_BODY_REASON)
        self.assertEqual(review_snapshot(), legacy_task)
        content.refresh_from_db()
        self.assertFalse(content.live)
        self.assertIsNone(content.live_revision_id)
        self.assertEqual(f07_integration.imported_state(), source_rows)
        self.assert_imported_revisions_unchanged(imported, imported_revisions)
        self.assert_legacy_unchanged()
        self.assert_no_employee_snapshot()
        print(f"F08C-1 empty body blocked: draft={draft.pk}; legacy_task={task_id}")

    def test_blank_and_nonstring_bodies_are_rejected_before_review_writes(self):
        """仅空白与非字符串正文同样被拒绝；正常非空正文仍可提交并批准发布。"""
        self.set_legacy_bodies(LEGACY_PLAINTEXT, LEGACY_DRAFT_PLAINTEXT)
        imported = import_article(self.article.pk, self.importer)
        content = KnowledgeContent.objects.get(pk=imported.content_id)
        source_rows = f07_integration.imported_state()
        imported_revisions = list(
            Revision.objects.filter(pk__in=imported.revision_ids).order_by("pk").values()
        )
        # 非字符串正文由同一规则拒绝：不猜测、不转换、不填充占位文本。
        for body in (None, 1, 1.0, True, {"text": "字典"}, ["列表"]):
            with self.subTest(body=repr(body)):
                with self.assertRaises(EmptyBodyRejected):
                    require_nonempty_body(body)
        # 夹具构造仅空白的受审修订：提交被拒绝，且审核侧没有任何写入。
        for body in ("", "   ", "\t\n ", "　"):
            with self.subTest(body=repr(body)):
                draft = self.make_draft_revision(content, body)
                content.refresh_from_db()
                self.assertEqual(content.latest_revision_id, draft.pk)
                self.assertEqual(draft.content["body"], body)
                before = review_snapshot()
                with self.assertRaises(EmptyBodyRejected) as caught:
                    submit(content.pk, draft.pk, self.review_submitter)
                self.assertEqual(caught.exception.code, EMPTY_BODY_CODE)
                self.assertEqual(str(caught.exception), EMPTY_BODY_REASON)
                self.assertEqual(review_snapshot(), before)
                self.assertEqual(TaskState.objects.count(), 0)
                self.assertEqual(TaskSubmission.objects.count(), 0)
                self.assertEqual(WorkflowState.objects.count(), 0)
                content.refresh_from_db()
                self.assertFalse(content.live)
                self.assertIsNone(content.live_revision_id)
                self.assert_no_employee_snapshot()
        # 首次正常提交后驳回，再以空白正文重提：共用规则仍在 resume/新任务写入前拒绝。
        first_reviewed = self.make_draft_revision(content, "首次非空待审正文")
        workflow = submit(content.pk, first_reviewed.pk, self.review_submitter)
        first_task_id = workflow.current_task_state_id
        reject(content.pk, first_task_id, self.approver, "请补充正文")
        rejected_snapshot = review_snapshot()
        rejected_blank = self.make_draft_revision(content, " \t\n")
        before_resubmit = review_snapshot()
        with self.assertRaises(EmptyBodyRejected) as caught:
            submit(content.pk, rejected_blank.pk, self.review_submitter)
        self.assertEqual(caught.exception.code, EMPTY_BODY_CODE)
        self.assertEqual(str(caught.exception), EMPTY_BODY_REASON)
        self.assertEqual(review_snapshot(), before_resubmit)
        self.assertEqual(TaskState.objects.count(), 1)
        self.assertEqual(TaskSubmission.objects.count(), 1)
        self.assertEqual(WorkflowState.objects.count(), 1)
        self.assertEqual(TaskState.objects.get(pk=first_task_id).status, TaskState.STATUS_REJECTED)
        self.assertEqual(
            WorkflowState.objects.get(pk=workflow.pk).status,
            WorkflowState.STATUS_NEEDS_CHANGES,
        )
        self.assertNotEqual(rejected_snapshot, before_resubmit)  # 只多出本次空白草稿。

        # 驳回后改为正常非空正文，同一入口仍可重提并由合法第三方批准发布。
        reviewed = self.make_draft_revision(content, LEGACY_PLAINTEXT)
        workflow = submit(content.pk, reviewed.pk, self.review_submitter)
        task_id = workflow.current_task_state_id
        self.assertNotEqual(task_id, first_task_id)
        self.assertEqual(TaskState.objects.get(pk=task_id).revision_id, reviewed.pk)
        approve_review(task_id, self.approver)
        content.refresh_from_db()
        self.assertTrue(content.live)
        self.assertEqual(content.live_revision_id, reviewed.pk)
        detail = get_employee_article_detail(self.employee, self.article.pk)
        self.assertEqual((detail.revision_id, detail.body), (reviewed.pk, LEGACY_PLAINTEXT))
        self.assertIsNone(get_employee_article_detail(self.outsider, self.article.pk))
        self.assertEqual(f07_integration.imported_state(), source_rows)
        self.assert_imported_revisions_unchanged(imported, imported_revisions)
        self.assert_legacy_unchanged()
        print(f"F08C-1 blank rejected: approved={reviewed.pk}; task={task_id}")

    def test_unsupported_mapping_body_stops_before_draft_and_review(self):
        # 夹具原始旧正式版本正文 payload 是字典，属于不支持自动转换的场景。
        imported = import_article(self.article.pk, self.importer)
        content = KnowledgeContent.objects.get(pk=imported.content_id)
        legacy_revision = Revision.objects.get(pk=imported.revision_ids[0])
        draft_revision = Revision.objects.get(pk=imported.revision_ids[1])
        encoded_body = legacy_revision.content["body"]
        self.assertIs(type(decode_body(encoded_body)), dict)
        source_rows = f07_integration.imported_state()
        before = review_snapshot()
        self.assert_legacy_unchanged()

        converted = convert_encoded_body_to_plaintext(encoded_body)
        self.assertFalse(converted.success)
        self.assertIsNone(converted.text)
        self.assertEqual(converted.code, "unsupported_mapping")
        self.assertEqual(converted.reason, UNSUPPORTED_REASON)

        # 失败即停止：本轮不保存转换草稿、不提交审核、不发布，也不做自动人工回退。
        self.assertEqual(review_snapshot(), before)
        self.assertEqual(f07_integration.imported_state(), source_rows)
        self.assert_legacy_unchanged()
        self.assertEqual(Revision.objects.count(), len(imported.revision_ids))
        content.refresh_from_db()
        self.assertEqual(content.latest_revision_id, draft_revision.pk)
        self.assertEqual(content.body, draft_revision.content["body"])
        self.assertFalse(content.live)
        self.assertIsNone(content.live_revision_id)
        self.assertEqual(TaskState.objects.count(), 0)
        self.assertEqual(TaskSubmission.objects.count(), 0)
        self.assertEqual(WorkflowState.objects.count(), 0)
        self.assert_no_employee_snapshot()
        print(f"F08C unsupported: C={content.pk}; imported={imported.revision_ids}")
