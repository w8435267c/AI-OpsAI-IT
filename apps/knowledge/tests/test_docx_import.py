"""单篇 Word 导入草稿的安全边界与管理入口。"""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.knowledge.docx_import import DocxImportError, import_docx_draft, parse_docx_import
from apps.knowledge.manage_readers import get_manage_working_article_detail
from apps.knowledge.media_scanning import ScanResult
from apps.knowledge.models import (
    Article,
    ArticleVersionImportSource,
    ArticleVersionMedia,
    MediaScanStatus,
    VersionStatus,
)
from apps.knowledge.tests.test_manage_article_create import ManageArticleCreateBase


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (4, 4), "blue").save(output, format="PNG")
    return output.getvalue()


def _docx_bytes(
    *,
    include_image=True,
    image_bytes=None,
    table=False,
    external=False,
    lists=False,
    absolute_image_target=False,
    unrelated_external=False,
) -> bytes:
    image = (
        """
      <w:r><w:drawing><wp:inline><a:graphic><a:graphicData>
      <pic:pic><pic:blipFill><a:blip r:embed="rIdImage"/></pic:blipFill></pic:pic>
      </a:graphicData></a:graphic></wp:inline></w:drawing></w:r>
    """
        if include_image
        else ""
    )
    table_xml = (
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        if table
        else ""
    )
    list_xml = (
        """
      <w:p><w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr>
      <w:r><w:t>有序步骤</w:t></w:r></w:p>
      <w:p><w:pPr><w:numPr><w:numId w:val="2"/></w:numPr></w:pPr>
      <w:r><w:t>无序提示</w:t></w:r></w:p>
    """
        if lists
        else ""
    )
    document = f"""<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
      xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
      xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>
      <w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>网络排障</w:t></w:r></w:p>
      <w:p><w:r><w:t>第一步：检查网络。</w:t></w:r></w:p>
      <w:p><w:r><w:t>第二步：检查截图。</w:t></w:r>{image}</w:p>
      <w:p><w:r><w:t>第三步：确认恢复。</w:t></w:r></w:p>{list_xml}{table_xml}
      </w:body></w:document>"""
    relationship_target = (
        "https://example.invalid/image.png"
        if external
        else "/word/media/step.png"
        if absolute_image_target
        else "media/step.png"
    )
    target_mode = ' TargetMode="External"' if external else ""
    unrelated_relationship = (
        '<Relationship Id="rIdHyperlink" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        'Target="https://example.invalid/help" TargetMode="External"/>'
        if unrelated_external
        else ""
    )
    relationships = f'''<?xml version="1.0" encoding="UTF-8"?>
      <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rIdImage" Type="image" Target="{relationship_target}"{target_mode}/>
      {unrelated_relationship}
      </Relationships>'''
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", relationships)
        archive.writestr(
            "word/numbering.xml",
            """<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0">
              <w:numFmt w:val="decimal"/></w:lvl></w:abstractNum>
              <w:abstractNum w:abstractNumId="2"><w:lvl w:ilvl="0">
              <w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>
              <w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num>
              <w:num w:numId="2"><w:abstractNumId w:val="2"/></w:num>
            </w:numbering>""",
        )
        if include_image:
            archive.writestr("word/media/step.png", image_bytes or _png_bytes())
    return output.getvalue()


class DocxImportTests(ManageArticleCreateBase):
    def _upload(self, payload=None, name="guide.docx"):
        return SimpleUploadedFile(
            name,
            payload if payload is not None else _docx_bytes(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    def _import_data(self):
        return {
            "space": self.editor_space,
            "category": self.editor_category,
            "article_type": "guide",
            "applicable_scope": {},
            "audience_policy": "all_employees",
            "effective_at": None,
            "review_due_at": timezone.now() + timedelta(days=180),
        }

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="scanner")
    def test_import_creates_only_a_scanned_draft_and_keeps_image_position(self):
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.docx_import.scan_private_file",
                return_value=ScanResult("clean", "ok"),
            ):
                article, parsed = import_docx_draft(
                    actor=self.editor, upload=self._upload(), form_data=self._import_data()
                )

            draft = article.latest_working_version
            draft.refresh_from_db()
            link = ArticleVersionMedia.objects.get(article_version=draft)
            self.assertEqual(article.current_published_version_id, None)
            self.assertEqual(draft.status, VersionStatus.DRAFT)
            self.assertEqual(parsed.title, "网络排障")
            self.assertEqual(
                draft.body_plaintext.splitlines(),
                ["第一步：检查网络。", "第二步：检查截图。", "第三步：确认恢复。"],
            )
            self.assertEqual(link.body_position, 2)
            self.assertEqual(link.asset.scan_status, MediaScanStatus.CLEAN)
            self.assertTrue((Path(directory) / link.asset.storage_name).is_file())
            self.assertEqual(draft.body["format"], "opsai.richtext/1")
            self.assertEqual(draft.body["content"][2]["type"], "image")
            self.assertEqual(draft.body["content"][2]["media_link_id"], str(link.pk))
            source = ArticleVersionImportSource.objects.get(article_version=draft)
            self.assertEqual(source.source_format, "docx")
            self.assertEqual(source.asset.scan_status, MediaScanStatus.CLEAN)
            self.assertTrue((Path(directory) / source.asset.storage_name).is_file())
            detail = get_manage_working_article_detail(actor=self.editor, kb_no=article.kb_no)
            self.assertEqual(detail.draft_id, draft.pk)
            self.assertEqual(detail.status, VersionStatus.DRAFT)

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="scanner")
    def test_scanner_failure_rejects_without_article_or_private_residue(self):
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.docx_import.scan_private_file",
                return_value=ScanResult("failed", "offline"),
            ):
                with self.assertRaises(DocxImportError):
                    import_docx_draft(
                        actor=self.editor, upload=self._upload(), form_data=self._import_data()
                    )

            self.assertFalse(Article.objects.exists())
            self.assertEqual(list(Path(directory).rglob("*")), [Path(directory) / ".incoming"])

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="scanner")
    def test_parser_reports_table_and_rejects_external_resource(self):
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.docx_import.scan_private_file",
                return_value=ScanResult("clean", "ok"),
            ):
                parsed = parse_docx_import(upload=self._upload(_docx_bytes(table=True)))
                self.assertTrue(any(node["type"] == "table" for node in parsed.content))
                for image in parsed.images:
                    image.path.unlink()
                with self.assertRaises(DocxImportError):
                    parse_docx_import(upload=self._upload(_docx_bytes(external=True)))

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="scanner")
    def test_parser_accepts_package_absolute_image_target_and_ignores_unrelated_external_link(self):
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.docx_import.scan_private_file",
                return_value=ScanResult("clean", "ok"),
            ):
                parsed = parse_docx_import(
                    upload=self._upload(
                        _docx_bytes(absolute_image_target=True, unrelated_external=True)
                    )
                )
            try:
                self.assertEqual(len(parsed.images), 1)
                self.assertEqual(parsed.images[0].body_position, 2)
            finally:
                for image in parsed.images:
                    image.path.unlink()

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="scanner")
    def test_invalid_embedded_image_leaves_no_private_temp_file(self):
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.docx_import.scan_private_file",
                return_value=ScanResult("clean", "ok"),
            ):
                with self.assertRaises(DocxImportError):
                    parse_docx_import(upload=self._upload(_docx_bytes(image_bytes=b"not-a-png")))

            self.assertEqual(list((Path(directory) / ".incoming").glob("*")), [])

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="scanner")
    def test_parser_preserves_ordered_and_unordered_lists(self):
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.docx_import.scan_private_file",
                return_value=ScanResult("clean", "ok"),
            ):
                parsed = parse_docx_import(upload=self._upload(_docx_bytes(lists=True)))
            try:
                self.assertIn("1. 有序步骤", parsed.body_text)
                self.assertIn("- 无序提示", parsed.body_text)
            finally:
                for image in parsed.images:
                    image.path.unlink()

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="scanner")
    def test_import_page_requires_editor_and_repeated_token_is_idempotent(self):
        client = Client()
        client.force_login(self.editor)
        payload = self.valid_data()
        payload.pop("title")
        payload.pop("summary")
        payload.pop("body_text")
        payload.pop("change_summary")
        payload.update(
            {
                "import_token": "d046e26c-fcc8-4db7-bd7a-8ad9e6419fd8",
                "document_file": self._upload(),
            }
        )
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.docx_import.scan_private_file",
                return_value=ScanResult("clean", "ok"),
            ):
                first = client.post(reverse("knowledge_manage:docx_import"), payload)
                payload["document_file"] = self._upload()
                second = client.post(reverse("knowledge_manage:docx_import"), payload)

        self.assertEqual(first.status_code, 303)
        self.assertEqual(second.status_code, 303)
        self.assertEqual(Article.objects.count(), 1)
        self.assertEqual(first["Location"], second["Location"])

    def test_employee_cannot_open_import_endpoint(self):
        client = Client()
        client.force_login(self.employee)
        response = client.post(reverse("knowledge_manage:docx_import"), {})
        self.assertEqual(response.status_code, 403)

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="scanner")
    def test_former_docx_field_name_remains_accepted_during_upgrade(self):
        client = Client()
        client.force_login(self.editor)
        payload = self.valid_data()
        for field in ("title", "summary", "body_text", "change_summary"):
            payload.pop(field)
        payload.update(
            {
                "import_token": "8b3c4bd7-f8ea-41b6-97af-0de1f60c3553",
                "docx_file": self._upload(),
            }
        )
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.docx_import.scan_private_file",
                return_value=ScanResult("clean", "ok"),
            ):
                response = client.post(reverse("knowledge_manage:docx_import"), payload)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(Article.objects.count(), 1)

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="scanner")
    def test_invalid_docx_relationship_returns_editor_error_not_500(self):
        client = Client()
        client.force_login(self.editor)
        payload = self.valid_data()
        for field in ("title", "summary", "body_text", "change_summary"):
            payload.pop(field)
        payload.update(
            {
                "import_token": "9fbf318d-dc1a-4b04-bb0a-16de0d1acaae",
                "document_file": self._upload(_docx_bytes(external=True)),
            }
        )
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.docx_import.scan_private_file",
                return_value=ScanResult("clean", "ok"),
            ):
                response = client.post(reverse("knowledge_manage:docx_import"), payload)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Word 包含外部图片引用，不能导入。", status_code=400)
        self.assertFalse(Article.objects.exists())
