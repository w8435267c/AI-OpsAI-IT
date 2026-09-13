"""F06 专用路由，不改动正式或 F05B URL 配置。"""

from django.urls import include, path

from .views import article_detail

urlpatterns = [
    # 字符串交由详情函数解析 UUID，非法值也得到相同 JSON 404。
    path("experiments/f06/articles/<str:article_id>/", article_detail, name="f06_article_detail"),
    path("", include("experiments.wagtail_f05a.urls")),
]
