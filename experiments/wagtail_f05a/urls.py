from django.contrib import admin
from django.urls import include, path, re_path
from wagtail.admin import urls as wagtail_urls

from experiments.wagtail_f04b.views import closed_operation

from . import views

urlpatterns = [
    path("cms/f05a/<int:pk>/review/", views.review, name="f05a_review"),
    path("cms/f05a/<int:pk>/submit/", views.submit, name="f05a_submit"),
    path("cms/f05a/<int:pk>/reject/", views.reject, name="f05a_reject"),
    re_path(r"^cms/f05a/.*$", closed_operation),
    path("cms/bulk/fusion_f04a/knowledgecontent/<str:action>/", closed_operation),
    re_path(r"^cms/workflows/.*$", closed_operation),
    re_path(r"^cms/users/.*$", closed_operation),
    re_path(r"^cms/groups/.*$", closed_operation),
    path("cms/", include(wagtail_urls)),
    re_path(r"^admin/auth/group/.*$", closed_operation),
    path("admin/", admin.site.urls),
]
