"""仅由 F05B 配置安装的公开后台扩展。"""

from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.widgets.button import Button

from experiments.wagtail_f04a.models import KnowledgeContent
from experiments.wagtail_f05a.services import active_state

from . import views
from .eligibility import check_approval_eligibility


@hooks.register("register_admin_urls")
def approval_urls():
    return [
        path("f05b/tasks/<int:task_state_id>/review/", views.review, name="f05b_review"),
        path("f05b/tasks/<int:task_state_id>/approve/", views.approve, name="f05b_approve"),
    ]


@hooks.register("register_snippet_listing_buttons")
def approval_button(instance, user, next_url=None):
    if not isinstance(instance, KnowledgeContent):
        return
    state = active_state(instance)
    if state and state.current_task_state_id:
        result = check_approval_eligibility(
            content_id=instance.pk, task_state_id=state.current_task_state_id, user=user
        )
        if result.allowed:
            yield Button(
                "审核并批准",
                reverse("f05b_review", args=[state.current_task_state_id]),
                priority=20,
            )
