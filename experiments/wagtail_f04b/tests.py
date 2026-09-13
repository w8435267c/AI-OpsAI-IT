"""真实 Snippet 请求，启用 CSRF；夹具权限不属于正式角色矩阵。"""

from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import reverse
from wagtail.models import Revision

from apps.accounts.models import User
from experiments.wagtail_f04a import tests as f04a
from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f04a.versions import publish_for_test, read_live


class BackendTests(TestCase):
    def setUp(self):
        f04a.VersionTests.setUp(self)
        revision = self.content.save_revision(user=self.user)
        publish_for_test(self.pk, revision.pk, self.user)
        self.revision_id = revision.pk
        self.history = list(Revision.objects.order_by("pk").values())
        self.users = {}
        grants = {
            "entry": ["wagtailadmin.access_admin"],
            "viewer": ["wagtailadmin.access_admin", "fusion_f04a.view_knowledgecontent"],
            "editor": ["wagtailadmin.access_admin", "fusion_f04a.change_knowledgecontent"],
            "no_entry": ["fusion_f04a.change_knowledgecontent"],
        }
        for name, permissions in grants.items():
            user = User.objects.create_user(username="f04b_" + name, password="synthetic-f04b")
            group = Group.objects.create(name="F04B fixture " + name)
            for permission in permissions:
                app, code = permission.split(".")
                group.permissions.add(
                    Permission.objects.get(content_type__app_label=app, codename=code)
                )
            user.groups.add(group)
            self.users[name] = user
        self.users["super"] = User.objects.create_superuser(
            username="f04b_super", password="synthetic-f04b", email="test@example.invalid"
        )
        self.viewset = KnowledgeContent.snippet_viewset
        self.edit_url = self.url("edit", self.pk)

    def tearDown(self):
        self.assertEqual(f04a.legacy_snapshot(), self.legacy)
        self.assertEqual(
            list(
                Revision.objects.filter(pk__in=[r["id"] for r in self.history])
                .order_by("pk")
                .values()
            ),
            self.history,
        )

    def url(self, name, *args):
        return reverse(self.viewset.get_url_name(name), args=args)

    def login(self, name):
        self.client = Client(enforce_csrf_checks=True)
        self.client.get("/cms/login/")
        response = self.client.post(
            "/cms/login/",
            {
                "username": self.users[name].username,
                "password": "synthetic-f04b",
                "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.users[name].user_permissions.exists())

    def data(self, **extra):
        return {
            "title": "V2",
            "summary": "摘要V2",
            "body": "正文V2",
            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            **extra,
        }

    def unchanged_request(self, method, url, data=None, statuses=(403,)):
        before = f04a.version_snapshot()
        response = getattr(self.client, method)(url, data or {})
        self.assertIn(response.status_code, statuses)
        self.assertEqual(f04a.version_snapshot(), before)
        return response

    def test_anonymous_and_missing_entry_cannot_edit(self):
        self.client = Client(enforce_csrf_checks=True)
        response = self.client.get(self.edit_url, follow=True)
        self.assertTemplateUsed(response, "wagtailadmin/login.html")
        self.login("no_entry")
        response = self.client.get(self.edit_url, follow=True)
        self.assertTemplateUsed(response, "wagtailadmin/login.html")

    def test_entry_only_cannot_list_or_edit_or_save(self):
        self.login("entry")
        for url in (self.url("list"), self.edit_url):
            self.unchanged_request("get", url, statuses=(302, 403))
        self.unchanged_request("post", self.edit_url, self.data(), statuses=(302, 403))

    def test_view_only_can_read_but_not_edit(self):
        self.login("viewer")
        self.assertEqual(self.client.get(self.url("list")).status_code, 200)
        self.assertEqual(self.client.get(self.url("inspect", self.pk)).status_code, 200)
        self.unchanged_request("get", self.edit_url, statuses=(302, 403))
        self.unchanged_request("post", self.edit_url, self.data(), statuses=(302, 403))
        self.unchanged_request("post", self.url("inspect", self.pk), self.data(), statuses=(405,))

    def test_real_save_appends_draft_and_reopens_latest(self):
        self.login("editor")
        self.assertFalse(self.users["editor"].is_staff)
        page = self.client.get(self.edit_url)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(set(page.context["form"].fields), {"title", "summary", "body"})
        self.assertContains(page, 'class="button action-save button-longrunning"')
        self.assertNotContains(page, 'name="action-publish"')
        # spy 委托实际模型方法，不代替真实保存。
        with patch.object(
            KnowledgeContent,
            "save_revision",
            autospec=True,
            side_effect=KnowledgeContent.save_revision,
        ) as save:
            response = self.client.post(self.edit_url, self.data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(save.call_count, 1)
        obj = KnowledgeContent.objects.get(pk=self.pk)
        self.assertEqual(obj.article_id, self.article.pk)
        self.assertEqual(obj.live_revision_id, self.revision_id)
        self.assertNotEqual(obj.latest_revision_id, self.revision_id)
        self.assertEqual(read_live(self.pk)["body"], "正文1")
        self.assertEqual(obj.body, "正文1")
        page = self.client.get(self.edit_url)
        self.assertEqual(page.context["form"]["title"].value(), "V2")
        self.assertEqual(page.context["form"]["summary"].value(), "摘要V2")
        self.assertEqual(page.context["form"]["body"].value(), "正文V2")
        previous = list(Revision.objects.order_by("pk").values())
        second = self.client.post(self.edit_url, self.data(body="正文V3"))
        self.assertEqual(second.status_code, 302)
        self.assertEqual(KnowledgeContent.objects.get(pk=self.pk).revisions.count(), 3)
        self.assertEqual(
            list(
                Revision.objects.filter(pk__in=[r["id"] for r in previous]).order_by("pk").values()
            ),
            previous,
        )

    def test_session_status_gate_for_get_and_post(self):
        for fields in (
            {"is_active": False},
            {"account_status": "disabled"},
            {"account_status": "departed"},
        ):
            for method in ("get", "post"):
                with self.subTest(fields=fields, method=method):
                    User.objects.filter(pk=self.users["editor"].pk).update(
                        is_active=True, account_status="active"
                    )
                    self.login("editor")
                    User.objects.filter(pk=self.users["editor"].pk).update(**fields)
                    response = self.unchanged_request(
                        method,
                        self.edit_url,
                        self.data() if method == "post" else None,
                        statuses=(302,),
                    )
                    self.assertIn("/cms/login/", response.url)

    def test_csrf_missing_and_invalid_rejected(self):
        self.login("editor")
        missing = self.data()
        missing.pop("csrfmiddlewaretoken")
        self.unchanged_request("post", self.edit_url, missing)
        self.unchanged_request("post", self.edit_url, self.data(csrfmiddlewaretoken="invalid"))

    def test_internal_fields_ignored_by_edit_whitelist(self):
        self.login("editor")
        response = self.client.post(
            self.edit_url,
            self.data(
                article=str(self.other.pk),
                article_id=str(self.other.pk),
                pk="9999",
                id="9999",
                live="false",
                live_revision="9999",
                latest_revision="9999",
                live_revision_id="9999",
                latest_revision_id="9999",
                go_live_at="2099-01-01 00:00",
                expire_at="2099-01-02 00:00",
            ),
        )
        self.assertEqual(response.status_code, 302)
        obj = KnowledgeContent.objects.get(pk=self.pk)
        self.assertEqual(obj.article_id, self.article.pk)
        self.assertEqual(obj.live_revision_id, self.revision_id)
        self.assertTrue(obj.live)
        self.assertIsNone(obj.go_live_at)
        self.assertIsNone(obj.expire_at)
        self.assertEqual(KnowledgeContent.objects.count(), 1)
        self.assertEqual(read_live(self.pk)["body"], "正文1")

    def test_url_target_is_authoritative_for_model_level_editor(self):
        other = KnowledgeContent.objects.create(article=self.other, title="other", body="other")
        self.login("editor")
        before = list(KnowledgeContent.objects.filter(pk=self.pk).values())
        response = self.client.post(self.url("edit", other.pk), self.data(pk=self.pk))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(KnowledgeContent.objects.filter(pk=self.pk).values()), before)
        self.assertEqual(KnowledgeContent.objects.get(pk=other.pk).article_id, self.other.pk)
        self.assertIsNone(read_live(other.pk))
        # 模型级编辑权限允许编辑另一个 URL 目标，不宣称存在组织级对象权限。

    def test_closed_actions_and_overwrite_rejected_even_superuser(self):
        for role in ("editor", "super"):
            self.login(role)
            page = self.client.get(self.edit_url)
            self.assertEqual(page.status_code, 200)
            self.assertNotContains(page, 'name="action-publish"')
            self.assertNotContains(page, 'name="action-submit"')
            for key in (
                "action-publish",
                "action-submit",
                "action-delete",
                "action-unpublish",
                "action-copy",
                "action-revert",
                "action-schedule",
                "action-unknown",
                "overwrite_revision_id",
                "revision_id",
                "action",
            ):
                with self.subTest(role=role, key=key):
                    self.unchanged_request("post", self.edit_url, self.data(**{key: "1"}))
                    self.unchanged_request("get", self.edit_url, {key: "1"})

    def test_closed_routes_and_chooser_and_bulk_rejected(self):
        args = {
            "add": (),
            "delete": (self.pk,),
            "usage": (self.pk,),
            "history": (self.pk,),
            "history_results": (self.pk,),
            "copy": (self.pk,),
            "revisions_revert": (self.pk, self.revision_id),
            "revisions_compare": (self.pk, "earliest", "latest"),
            "revisions_unschedule": (self.pk, self.revision_id),
            "unpublish": (self.pk,),
        }
        patterns = self.viewset.get_urlpatterns()
        self.assertEqual(
            {p.name for p in patterns}, set(args) | {"list", "list_results", "edit", "inspect"}
        )
        chooser = self.viewset.chooser_viewset
        chooser_urls = [
            reverse(chooser.get_url_name(p.name), args=[self.pk] if p.name == "chosen" else [])
            for p in chooser.get_urlpatterns()
        ]
        for role in ("editor", "super"):
            self.login(role)
            urls = [self.url(name, *values) for name, values in args.items()]
            urls += chooser_urls
            urls += [
                f"/cms/bulk/fusion_f04a/knowledgecontent/{action}/?id={self.pk}"
                for action in ("delete", "publish", "unpublish")
            ]
            for url in urls:
                with self.subTest(role=role, url=url):
                    self.unchanged_request("get", url)
                    self.unchanged_request("post", url, self.data())
            for name in ("list", "list_results"):
                self.unchanged_request("post", self.url(name), self.data(), statuses=(405,))

    def test_save_failure_rolls_back_real_request(self):
        self.login("editor")
        self.client.get(self.edit_url)
        before = f04a.version_snapshot()
        with patch(
            "wagtail.admin.views.generic.mixins.log",
            side_effect=RuntimeError("F04B 保存后日志故障"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(self.edit_url, self.data())
        self.assertEqual(f04a.version_snapshot(), before)
        self.assertEqual(read_live(self.pk)["body"], "正文1")
