"""默认兼容进程不加载 Wagtail URL。"""

from django.contrib import admin
from django.urls import path

urlpatterns = [path("admin/", admin.site.urls)]
