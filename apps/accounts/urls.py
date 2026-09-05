"""账号与组织路由（当前仅本地开发模拟登录）。"""

from django.urls import path

from .views import dev_login, dev_logout

app_name = "accounts"

urlpatterns = [
    path("login/", dev_login, name="dev-login"),
    path("logout/", dev_logout, name="dev-logout"),
]
