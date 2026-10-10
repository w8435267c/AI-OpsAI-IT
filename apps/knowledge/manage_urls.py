"""正式知识管理区路由。"""

from django.urls import path

from apps.knowledge.manage_views import manage_article_list

app_name = "knowledge_manage"

urlpatterns = [
    path("", manage_article_list, name="list"),
]
