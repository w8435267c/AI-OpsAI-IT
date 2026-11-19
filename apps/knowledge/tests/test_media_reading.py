"""版本媒体的员工读取边界测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.knowledge.media_services import ensure_version_media_publishable
from apps.knowledge.models import (
    ArticleVersionMedia,
    AudienceEffect,
    AudiencePolicy,
    AudienceType,
    MediaAsset,
    MediaKind,
    MediaScanStatus,
)
from apps.knowledge.readers import get_employee_article_detail
from apps.knowledge.tests.test_selectors import _add_audience, _mk_article, _mk_user, _publish


class VersionMediaReadingTests(TestCase):
    def setUp(self):
        self.reader = _mk_user(username="media-reader")
        self.other = _mk_user(username="media-other")
        self.article, self.version = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        _add_audience(
            self.article,
            AudienceType.USER,
            effect=AudienceEffect.DENY,
            user=self.other,
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.reader)

    def _link(self, *, kind=MediaKind.IMAGE, status=MediaScanStatus.CLEAN):
        asset = MediaAsset.objects.create(
            kind=kind,
            original_name="guide.docx" if kind == MediaKind.DOCUMENT else "step.png",
            storage_name=f"media/test-{MediaAsset.objects.count()}.bin",
            content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if kind == MediaKind.DOCUMENT
                else "image/png"
            ),
            size_bytes=3,
            sha256="a" * 64,
            scan_status=status,
            scan_message="扫描通过。",
            created_by=self.reader,
        )
        return ArticleVersionMedia.objects.create(
            article_version=self.version,
            asset=asset,
            body_position=0 if kind == MediaKind.IMAGE else None,
        )

    def test_employee_detail_only_exposes_clean_media_of_current_published_version(self):
        clean = self._link()
        self._link(status=MediaScanStatus.FAILED)

        detail = get_employee_article_detail(self.reader, self.article.kb_no)

        self.assertEqual([item.link_id for item in detail.media], [clean.pk])

    @override_settings(MEDIA_ROOT=Path(settings.BASE_DIR) / "private_media_test_placeholder")
    def test_unauthorized_media_link_is_not_found_and_clean_document_is_downloaded_with_audit(self):
        with TemporaryDirectory() as directory:
            with self.settings(MEDIA_ROOT=Path(directory)):
                link = self._link(kind=MediaKind.DOCUMENT)
                path = Path(directory) / link.asset.storage_name
                path.parent.mkdir(parents=True)
                path.write_bytes(b"docx")
                url = reverse("knowledge:media_content", args=[self.article.kb_no, link.pk])

                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn("private, no-store", response["Cache-Control"])
                response.close()

                self.client.force_login(self.other)
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_non_clean_media_blocks_publish_gate(self):
        self._link(status=MediaScanStatus.PENDING)
        with self.assertRaisesMessage(Exception, "存在未通过扫描的媒体"):
            ensure_version_media_publishable(version=self.version)
