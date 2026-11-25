"""First-batch non-DOCX import parser contracts."""

from datetime import timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from apps.knowledge.document_import import DocumentImportError, parse_document_import
from apps.knowledge.manage_readers import get_manage_working_article_detail
from apps.knowledge.media_scanning import ScanResult
from apps.knowledge.models import Article, ArticleVersionImportSource, VersionStatus
from apps.knowledge.tests.test_manage_article_create import ManageArticleCreateBase


def _pdf_with_text(text: bytes) -> bytes:
    """Create a minimal text-layer PDF without adding a PDF-generation dependency."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}  # noqa: SLF001
            )
        }
    )
    contents = DecodedStreamObject()
    contents.set_data(b"BT /F1 12 Tf 72 720 Td (" + text + b") Tj ET")
    page[NameObject("/Contents")] = writer._add_object(contents)  # noqa: SLF001
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _pdf_with_chinese_text() -> bytes:
    """Create a small PDF with an explicit ToUnicode map for Chinese extraction."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    descriptor = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/FontDescriptor"),
            NameObject("/FontName"): NameObject("/OpsAITest"),
            NameObject("/Flags"): NumberObject(4),
            NameObject("/FontBBox"): ArrayObject([NumberObject(0)] * 4),
            NameObject("/ItalicAngle"): NumberObject(0),
            NameObject("/Ascent"): NumberObject(880),
            NameObject("/Descent"): NumberObject(-120),
            NameObject("/CapHeight"): NumberObject(700),
            NameObject("/StemV"): NumberObject(80),
        }
    )
    cid_font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/CIDFontType2"),
            NameObject("/BaseFont"): NameObject("/OpsAITest"),
            NameObject("/CIDSystemInfo"): DictionaryObject(
                {
                    NameObject("/Registry"): TextStringObject("Adobe"),
                    NameObject("/Ordering"): TextStringObject("Identity"),
                    NameObject("/Supplement"): NumberObject(0),
                }
            ),
            NameObject("/FontDescriptor"): writer._add_object(descriptor),  # noqa: SLF001
        }
    )
    to_unicode = DecodedStreamObject()
    to_unicode.set_data(
        b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def "
        b"/CMapName /OpsAITest def /CMapType 2 def 1 begincodespacerange "
        b"<0000> <FFFF> endcodespacerange 2 beginbfchar <0001> <4E2D> <0002> <6587> "
        b"endbfchar endcmap CMapName currentdict /CMap defineresource pop end end"
    )
    type0_font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type0"),
            NameObject("/BaseFont"): NameObject("/OpsAITest"),
            NameObject("/Encoding"): NameObject("/Identity-H"),
            NameObject("/DescendantFonts"): ArrayObject([writer._add_object(cid_font)]),  # noqa: SLF001
            NameObject("/ToUnicode"): writer._add_object(to_unicode),  # noqa: SLF001
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(type0_font)})}
    )
    contents = DecodedStreamObject()
    contents.set_data(b"BT /F1 12 Tf 72 720 Td <00010002> Tj ET")
    page[NameObject("/Contents")] = writer._add_object(contents)  # noqa: SLF001
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("test-only-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _many_page_pdf(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class DocumentImportParserTests(SimpleTestCase):
    def parse(self, name: str, content: bytes):
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.document_import.scan_private_file",
                return_value=ScanResult("clean", "ok"),
            ):
                return parse_document_import(upload=SimpleUploadedFile(name, content))

    def test_utf8_text_keeps_paragraphs_and_uses_filename_title(self):
        parsed = self.parse("网络检查.txt", "第一步\n\n第二步".encode())
        self.assertEqual(parsed.title, "网络检查")
        self.assertEqual(parsed.body_text, "第一步\n\n第二步")
        self.assertEqual(parsed.source_format, "txt")

    def test_common_chinese_text_encoding_is_decoded(self):
        parsed = self.parse("编码.txt", "中文步骤".encode("gb18030"))
        self.assertEqual(parsed.body_text, "中文步骤")

    def test_markdown_drops_heading_marker_and_reports_image_reference(self):
        parsed = self.parse("guide.md", "# 标题\n\n- 步骤\n![本地](step.png)".encode())
        self.assertEqual(parsed.title, "标题")
        self.assertIn("步骤", parsed.body_text)
        self.assertTrue(parsed.warnings)

    def test_markdown_raw_html_is_rejected(self):
        with self.assertRaises(DocumentImportError) as ctx:
            self.parse("unsafe.md", b"# title\n<script>alert(1)</script>")
        self.assertEqual(ctx.exception.code, "DOCUMENT_IMPORT_INVALID")

    def test_fake_pdf_extension_is_rejected_by_signature(self):
        with self.assertRaises(DocumentImportError) as ctx:
            self.parse("fake.pdf", b"not a pdf")
        self.assertEqual(ctx.exception.code, "DOCUMENT_IMPORT_INVALID")

    def test_text_layer_pdf_is_extracted(self):
        parsed = self.parse("guide.pdf", _pdf_with_text(b"Step one"))
        self.assertEqual(parsed.source_format, "pdf")
        self.assertEqual(parsed.title, "Step one")
        self.assertIn("Step one", parsed.body_text)

    def test_chinese_text_layer_pdf_is_extracted(self):
        parsed = self.parse("chinese.pdf", _pdf_with_chinese_text())
        self.assertIn("中文", parsed.body_text)

    def test_scanned_pdf_without_text_layer_is_rejected(self):
        with self.assertRaises(DocumentImportError) as ctx:
            self.parse("scan.pdf", _pdf_with_text(b""))
        self.assertEqual(ctx.exception.code, "DOCUMENT_IMPORT_INVALID")

    def test_encrypted_pdf_is_rejected(self):
        with self.assertRaises(DocumentImportError) as ctx:
            self.parse("encrypted.pdf", _encrypted_pdf())
        self.assertEqual(ctx.exception.code, "DOCUMENT_IMPORT_INVALID")

    def test_pdf_page_limit_is_enforced(self):
        with self.assertRaises(DocumentImportError) as ctx:
            self.parse("large.pdf", _many_page_pdf(101))
        self.assertEqual(ctx.exception.code, "DOCUMENT_IMPORT_INVALID")

    def test_corrupt_pdf_is_rejected(self):
        with self.assertRaises(DocumentImportError) as ctx:
            self.parse("corrupt.pdf", b"%PDF-1.7\nnot a valid PDF")
        self.assertEqual(ctx.exception.code, "DOCUMENT_IMPORT_INVALID")

    def test_pdf_content_stream_limit_is_enforced(self):
        with self.assertRaises(DocumentImportError) as ctx:
            self.parse("stream.pdf", _pdf_with_text(b"a" * (2 * 1024 * 1024 + 1)))
        self.assertEqual(ctx.exception.code, "DOCUMENT_IMPORT_INVALID")

    def test_binary_text_is_rejected(self):
        with self.assertRaises(DocumentImportError) as ctx:
            self.parse("binary.txt", b"valid\x00invalid")
        self.assertEqual(ctx.exception.code, "DOCUMENT_IMPORT_INVALID")

    def test_unknown_text_encoding_is_rejected(self):
        with self.assertRaises(DocumentImportError) as ctx:
            self.parse("unknown.txt", b"\xff")
        self.assertEqual(ctx.exception.code, "DOCUMENT_IMPORT_INVALID")

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="scanner")
    def test_scan_failure_stops_before_parse(self):
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.document_import.scan_private_file",
                return_value=ScanResult("failed", "offline"),
            ):
                with self.assertRaises(DocumentImportError) as ctx:
                    parse_document_import(upload=SimpleUploadedFile("guide.txt", b"body"))
        self.assertEqual(ctx.exception.code, "DOCUMENT_IMPORT_SCAN_FAILED")


class DocumentImportDraftTests(ManageArticleCreateBase):
    def _form_data(self):
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
    def test_clean_text_import_creates_a_draft_only(self):
        from apps.knowledge.document_import import import_document_draft

        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.document_import.scan_private_file",
                return_value=ScanResult("clean", "ok"),
            ):
                article, parsed = import_document_draft(
                    actor=self.editor,
                    upload=SimpleUploadedFile("guide.txt", b"first\n\nsecond"),
                    form_data=self._form_data(),
                )

        self.assertEqual(parsed.source_format, "txt")
        self.assertIsNone(article.current_published_version_id)
        draft = article.latest_working_version
        draft.refresh_from_db()
        self.assertEqual(draft.status, VersionStatus.DRAFT)
        self.assertEqual(draft.body["format"], "opsai.richtext/1")
        self.assertEqual(
            ArticleVersionImportSource.objects.get(article_version=draft).source_format,
            "txt",
        )

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="scanner")
    def test_txt_markdown_and_pdf_imports_open_the_editor_draft_reader(self):
        from apps.knowledge.document_import import import_document_draft

        samples = (
            ("guide.txt", b"first\n\nsecond"),
            ("guide.md", b"# Markdown title\n\n- step"),
            ("guide.pdf", _pdf_with_text(b"PDF title")),
        )
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.document_import.scan_private_file",
                return_value=ScanResult("clean", "ok"),
            ):
                for name, content in samples:
                    with self.subTest(name=name):
                        article, _parsed = import_document_draft(
                            actor=self.editor,
                            upload=SimpleUploadedFile(name, content),
                            form_data=self._form_data(),
                        )
                        detail = get_manage_working_article_detail(
                            actor=self.editor, kb_no=article.kb_no
                        )
                        self.assertEqual(detail.draft_id, article.latest_working_version_id)
                        self.assertEqual(detail.status, VersionStatus.DRAFT)

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="scanner")
    def test_scan_failure_leaves_no_article_or_private_file(self):
        from apps.knowledge.document_import import import_document_draft

        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)):
            with patch(
                "apps.knowledge.document_import.scan_private_file",
                return_value=ScanResult("failed", "offline"),
            ):
                with self.assertRaises(DocumentImportError):
                    import_document_draft(
                        actor=self.editor,
                        upload=SimpleUploadedFile("guide.txt", b"body"),
                        form_data=self._form_data(),
                    )

            self.assertFalse(Article.objects.exists())
            self.assertEqual(list(Path(directory).rglob("*")), [Path(directory) / ".incoming"])
