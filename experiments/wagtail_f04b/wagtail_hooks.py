"""公开注册 API 和菜单 hook；真正的关闭策略在视图/URL 层。"""

from wagtail import hooks
from wagtail.snippets.action_menu import SaveMenuItem
from wagtail.snippets.models import register_snippet

from experiments.wagtail_f04a.models import KnowledgeContent

from .views import KnowledgeContentViewSet

register_snippet(KnowledgeContentViewSet)


@hooks.register("construct_snippet_action_menu")
def draft_only_menu(menu_items, request, context):
    if context.get("model") is KnowledgeContent:
        menu_items[:] = [item for item in menu_items if isinstance(item, SaveMenuItem)]
