"""F08 专用页面路由；同时保留既有 F06 JSON 实验入口。"""

from django.urls import include, path

from .views import article_detail

urlpatterns = [
    path("experiments/f08/articles/<str:article_id>/", article_detail, name="f08_article_detail"),
    path("", include("experiments.wagtail_f06.urls")),
]
