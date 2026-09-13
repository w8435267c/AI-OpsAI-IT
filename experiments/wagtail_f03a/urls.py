"""仅 Django 测试 Client 使用，不启动 HTTP 服务。"""

from django.contrib import admin
from django.urls import include, path
from wagtail.admin import urls as wagtail_urls

urlpatterns = [
    path("cms/", include(wagtail_urls)),
    path("admin/", admin.site.urls),
]
