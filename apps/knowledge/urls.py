"""正式员工知识页面路由。"""

from django.urls import path

from apps.knowledge.views import employee_category_detail, employee_home

app_name = "knowledge"

urlpatterns = [
    path("", employee_home, name="home"),
    path(
        "categories/<uuid:category_id>/",
        employee_category_detail,
        name="category_detail",
    ),
]
