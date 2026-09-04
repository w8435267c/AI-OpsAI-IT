"""OpsAI-IT 根路由。"""

from django.contrib import admin
from django.urls import path

from apps.core.views import live, ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", live, name="health-live"),
    path("health/ready", ready, name="health-ready"),
]
