from wagtail import hooks
from wagtail.snippets.action_menu import SaveMenuItem
from wagtail.snippets.models import register_snippet

from experiments.wagtail_f04a.models import KnowledgeContent

from .views import ReviewViewSet

register_snippet(ReviewViewSet)


@hooks.register("construct_snippet_action_menu")
def only_draft(menu_items, request, context):
    if context.get("model") is KnowledgeContent:
        menu_items[:] = [item for item in menu_items if isinstance(item, SaveMenuItem)]
