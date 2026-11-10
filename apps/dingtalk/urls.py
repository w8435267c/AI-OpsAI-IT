"""钉钉 H5 登录路由。"""

from django.urls import path

from .views import sso_complete, sso_start

app_name = "dingtalk"

urlpatterns = [
    path("sso/start/", sso_start, name="sso-start"),
    path("sso/complete/", sso_complete, name="sso-complete"),
]
