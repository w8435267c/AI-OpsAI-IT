"""只开放已有内容的查看及草稿编辑；本模块不更改模型或系统角色。"""

from django.db import transaction
from django.http import HttpResponseForbidden
from django.urls.resolvers import URLPattern
from django.utils.functional import cached_property
from wagtail.admin.panels import FieldPanel
from wagtail.admin.ui.tables import BulkActionsCheckboxColumn
from wagtail.permission_policies.base import ModelPermissionPolicy
from wagtail.snippets.views.chooser import SnippetChooserViewSet
from wagtail.snippets.views.snippets import EditView, IndexView, SnippetViewSet

from experiments.wagtail_f04a.models import KnowledgeContent


def closed_operation(request, *args, **kwargs):
    return HttpResponseForbidden("F04B 仅开放已有内容的查看与草稿编辑。")


def close_patterns(patterns, allowed=()):
    # 保留实际 URL 名称便于模板反向解析；未经允许的处理器一律拒绝。
    return [
        pattern
        if pattern.name in allowed
        else URLPattern(pattern.pattern, closed_operation, pattern.default_args, pattern.name)
        for pattern in patterns
    ]


class DraftPermissionPolicy(ModelPermissionPolicy):
    def user_has_permission(self, user, action):
        return action in {"view", "change"} and super().user_has_permission(user, action)


class DraftIndexView(IndexView):
    http_method_names = ["get", "head", "options"]

    @cached_property
    def columns(self):
        return [c for c in super().columns if not isinstance(c, BulkActionsCheckboxColumn)]


class DraftEditView(EditView):
    http_method_names = ["get", "head", "post", "options"]

    def get_available_actions(self):
        return ["edit"]

    def dispatch(self, request, *args, **kwargs):
        for data in (request.GET, request.POST):
            if any(
                key.startswith("action-") and key not in {"action-save", "action-edit"}
                for key in data
            ):
                return closed_operation(request)
            if any(key in data for key in ("overwrite_revision_id", "revision_id", "action")):
                return closed_operation(request)
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        # 包住实际 Wagtail 表单保存、追加修订、日志及后置 hook。
        return super().post(request, *args, **kwargs)

    def get_history_url(self):
        return None

    def get_usage_url(self):
        return None


class ClosedChooserViewSet(SnippetChooserViewSet):
    def get_urlpatterns(self):
        return close_patterns(super().get_urlpatterns())


class KnowledgeContentViewSet(SnippetViewSet):
    model = KnowledgeContent
    icon = "doc-full"
    panels = [FieldPanel("title"), FieldPanel("summary"), FieldPanel("body")]
    list_display = ["title"]
    edit_view_class = DraftEditView
    index_view_class = DraftIndexView
    chooser_viewset_class = ClosedChooserViewSet
    inspect_view_enabled = True
    inspect_view_fields = ["title", "summary", "body"]

    @cached_property
    def permission_policy(self):
        return DraftPermissionPolicy(self.model)

    def get_urlpatterns(self):
        return close_patterns(
            [
                p
                for p in super().get_urlpatterns()
                if p.name
                not in {
                    "workflow_action",
                    "collect_workflow_action_data",
                    "confirm_workflow_cancellation",
                    "workflow_history",
                    "workflow_history_detail",
                    "workflow_preview",
                }
            ],
            {"list", "list_results", "edit", "inspect"},
        )
