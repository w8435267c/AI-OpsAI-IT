"""正式知识管理区路由。"""

from django.urls import path

from apps.knowledge.manage_views import (
    manage_article_autosave,
    manage_article_create,
    manage_article_edit,
    manage_article_history,
    manage_article_history_detail,
    manage_article_list,
    manage_article_manual_save,
    manage_article_restore,
)

app_name = "knowledge_manage"

urlpatterns = [
    path("", manage_article_list, name="list"),
    path("new/", manage_article_create, name="create"),
    path("<str:kb_no>/autosave/", manage_article_autosave, name="autosave"),
    path("<str:kb_no>/save/", manage_article_manual_save, name="save"),
    path("<str:kb_no>/history/", manage_article_history, name="history"),
    path(
        "<str:kb_no>/history/<uuid:version_id>/",
        manage_article_history_detail,
        name="history_detail",
    ),
    path(
        "<str:kb_no>/history/<uuid:version_id>/restore/",
        manage_article_restore,
        name="restore",
    ),
    path("<str:kb_no>/edit/", manage_article_edit, name="edit"),
]
