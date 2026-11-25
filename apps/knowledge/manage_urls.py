"""正式知识管理区路由。"""

from django.urls import path

from apps.knowledge.manage_views import (
    manage_article_autosave,
    manage_article_create,
    manage_article_docx_import,
    manage_article_edit,
    manage_article_history,
    manage_article_history_detail,
    manage_article_history_media_content,
    manage_article_import_source,
    manage_article_list,
    manage_article_manual_save,
    manage_article_media_content,
    manage_article_media_remove,
    manage_article_media_upload,
    manage_article_preview,
    manage_article_restore,
)

app_name = "knowledge_manage"

urlpatterns = [
    path("", manage_article_list, name="list"),
    path("new/", manage_article_create, name="create"),
    path("new/import-docx/", manage_article_docx_import, name="docx_import"),
    path("<str:kb_no>/autosave/", manage_article_autosave, name="autosave"),
    path("<str:kb_no>/save/", manage_article_manual_save, name="save"),
    path("<str:kb_no>/media/upload/", manage_article_media_upload, name="media_upload"),
    path("<str:kb_no>/media/<uuid:media_id>/", manage_article_media_content, name="media_content"),
    path(
        "<str:kb_no>/media/<uuid:media_id>/remove/",
        manage_article_media_remove,
        name="media_remove",
    ),
    path("<str:kb_no>/preview/", manage_article_preview, name="preview"),
    path("<str:kb_no>/history/", manage_article_history, name="history"),
    path(
        "<str:kb_no>/history/<uuid:version_id>/",
        manage_article_history_detail,
        name="history_detail",
    ),
    path(
        "<str:kb_no>/history/<uuid:version_id>/media/<uuid:media_id>/",
        manage_article_history_media_content,
        name="history_media_content",
    ),
    path(
        "<str:kb_no>/history/<uuid:version_id>/source/",
        manage_article_import_source,
        name="import_source",
    ),
    path(
        "<str:kb_no>/history/<uuid:version_id>/restore/",
        manage_article_restore,
        name="restore",
    ),
    path("<str:kb_no>/edit/", manage_article_edit, name="edit"),
]
