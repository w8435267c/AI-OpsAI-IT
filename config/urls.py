"""OpsAI-IT 根路由。"""

from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import employee_login, employee_logout
from apps.core.views import live, ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", live, name="health-live"),
    path("health/ready", ready, name="health-ready"),
    path("accounts/login/", employee_login, name="employee-login"),
    path("accounts/logout/", employee_logout, name="employee-logout"),
    # 本地开发专用模拟登录入口；生产环境由开关强制关闭（返回 404）。
    path("dev/", include("apps.accounts.urls")),
    path("dingtalk/", include("apps.dingtalk.urls")),
]

urlpatterns += [
    path("manage/reviews/", include("apps.workflow.urls")),
    path("manage/knowledge/", include("apps.knowledge.manage_urls")),
    path("", include("apps.service_desk.urls")),
    path("", include("apps.search.urls")),
    path("", include("apps.knowledge.urls")),
]
