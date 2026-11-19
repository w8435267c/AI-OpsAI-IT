"""实际文件格式验证和 ClamAV 失败关闭边界。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.knowledge.media_scanning import (
    _classify_clamd_reply,
    _read_clamd_reply,
    scan_private_file,
)
from apps.knowledge.media_services import (
    KnowledgeMediaError,
    _scan_asset,
    _validate_actual_format,
)
from apps.knowledge.models import MediaScanStatus


class _ReplySocket:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def recv(self, _size):
        item = next(self.chunks)
        if isinstance(item, BaseException):
            raise item
        return item


class ClamdReplyTests(SimpleTestCase):
    def test_segmented_clean_reply_is_read_to_nul_terminator(self):
        reply = _read_clamd_reply(_ReplySocket([b"stream: ", b"OK\0"]))
        self.assertEqual(reply, b"stream: OK\0")
        self.assertEqual(_classify_clamd_reply(reply).status, "clean")

    def test_segmented_found_reply_is_detected_without_signature_assumption(self):
        reply = _read_clamd_reply(_ReplySocket([b"stream: Example", b" threat FOUND\0"]))
        self.assertEqual(_classify_clamd_reply(reply).status, "infected")

    def test_error_empty_and_incomplete_replies_fail_closed(self):
        for reply in (b"stream: ERROR\0", b"", b"stream: OK"):
            with self.subTest(reply=reply):
                self.assertEqual(_classify_clamd_reply(reply).status, "failed")

    def test_timeout_fails_closed(self):
        with self.assertRaises(TimeoutError):
            _read_clamd_reply(_ReplySocket([TimeoutError()]))


class MediaScanPersistenceTests(SimpleTestCase):
    def test_detected_scan_result_is_persisted_as_infected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.bin"
            path.write_bytes(b"sample")

            class Asset:
                scan_status = MediaScanStatus.PENDING
                scan_message = ""
                scanned_at = None
                saved_fields = None

                def save(self, *, update_fields):
                    self.saved_fields = update_fields

            asset = Asset()
            with patch(
                "apps.knowledge.media_scanning.scan_private_file",
                return_value=type("Result", (), {"status": "infected", "message": "detected"})(),
            ):
                _scan_asset(asset, path)

        self.assertEqual(asset.scan_status, "infected")
        self.assertEqual(asset.scan_message, "detected")
        self.assertEqual(asset.saved_fields, ("scan_status", "scan_message", "scanned_at"))


class MediaFormatValidationTests(SimpleTestCase):
    def test_svg_disguised_as_png_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe.png"
            path.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
            with self.assertRaises(KnowledgeMediaError):
                _validate_actual_format(path, path.name)

    def test_macro_named_docx_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe.docm"
            path.write_bytes(b"not-a-docx")
            with self.assertRaises(KnowledgeMediaError):
                _validate_actual_format(path, path.name)

    @override_settings(KNOWLEDGE_MEDIA_CLAMD_HOST="")
    def test_unconfigured_scanner_fails_closed(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.bin"
            path.write_bytes(b"sample")
            result = scan_private_file(path)
        self.assertEqual(result.status, "failed")
