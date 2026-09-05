"""OpsAI-IT 根路由。"""

from django.contrib import admin
from django.urls import include, path

from apps.core.views import live, ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", live, name="health-live"),
    path("health/ready", ready, name="health-ready"),
    # 本地开发专用模拟登录入口；生产环境由开关强制关闭（返回 404）。
    path("dev/", include("apps.accounts.urls")),
]
