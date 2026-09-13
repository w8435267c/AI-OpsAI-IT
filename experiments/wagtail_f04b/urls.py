"""实验 URL；先拦截该模型的通用批量操作，再挂载 Wagtail。"""

from django.contrib import admin
from django.urls import include, path
from wagtail.admin import urls as wagtail_urls

from .views import closed_operation

urlpatterns = [
    path("cms/bulk/fusion_f04a/knowledgecontent/<str:action>/", closed_operation),
    path("cms/", include(wagtail_urls)),
    path("admin/", admin.site.urls),
]
