"""正式员工知识页面路由。"""

from django.urls import path

from apps.knowledge.views import (
    employee_article_detail,
    employee_category_detail,
    employee_home,
)

app_name = "knowledge"

urlpatterns = [
    path("", employee_home, name="home"),
    path(
        "categories/<uuid:category_id>/",
        employee_category_detail,
        name="category_detail",
    ),
    path("kb/<str:kb_no>/", employee_article_detail, name="article_detail"),
]
