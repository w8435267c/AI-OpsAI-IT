"""正式知识管理区路由。"""

from django.urls import path

from apps.knowledge.manage_views import (
    manage_article_autosave,
    manage_article_create,
    manage_article_edit,
    manage_article_list,
)

app_name = "knowledge_manage"

urlpatterns = [
    path("", manage_article_list, name="list"),
    path("new/", manage_article_create, name="create"),
    path("<str:kb_no>/autosave/", manage_article_autosave, name="autosave"),
    path("<str:kb_no>/edit/", manage_article_edit, name="edit"),
]
