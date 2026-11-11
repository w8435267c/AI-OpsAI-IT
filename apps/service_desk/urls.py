"""统一 IT 服务申请入口路由。"""

from django.urls import path

from apps.service_desk.views import request_entry

app_name = "service_desk"

urlpatterns = [
    path("service-request/<str:kb_no>/", request_entry, name="request_entry"),
]
