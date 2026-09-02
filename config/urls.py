"""OpsAI-IT 根路由。"""

from django.contrib import admin
from django.urls import path

from apps.core.views import live

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", live, name="health-live"),
]
