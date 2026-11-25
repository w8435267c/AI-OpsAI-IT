"""审核工作台路由。"""

from django.urls import path

from .views import (
    review_detail,
    review_import_source,
    review_media_content,
    review_queue,
    reviewed_by_me,
    submit_for_review,
)

app_name = "workflow"

urlpatterns = [
    path("", review_queue, name="queue"),
    path("reviewed/", reviewed_by_me, name="reviewed"),
    path("submissions/<str:kb_no>/", submit_for_review, name="submission"),
    path("<uuid:version_id>/media/<uuid:media_id>/", review_media_content, name="media"),
    path("<uuid:version_id>/source/", review_import_source, name="import_source"),
    path("<uuid:version_id>/", review_detail, name="detail"),
]
