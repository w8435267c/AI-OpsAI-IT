"""Bounded, fail-closed parsers for the first multi-format import batch."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.knowledge.docx_import import DocxImportError, import_docx_draft, parse_docx_import
from apps.knowledge.import_sources import retain_import_source
from apps.knowledge.media_scanning import scan_private_file
from apps.knowledge.media_services import _copy_upload_to_private_temp
from apps.knowledge.richtext_import import markdown_content, plaintext_content, richtext_document
from apps.knowledge.services import ArticleCreationError, autosave_draft, create_article

try:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
except ImportError:  # pragma: no cover - dependency is verified by packaging checks.
    PdfReader = None
    PdfReadError = Exception


DOCUMENT_IMPORT_INVALID = "DOCUMENT_IMPORT_INVALID"
DOCUMENT_IMPORT_SCAN_FAILED = "DOCUMENT_IMPORT_SCAN_FAILED"
DOCUMENT_IMPORT_FAILED = "DOCUMENT_IMPORT_FAILED"
MAX_PDF_PAGES = 100
MAX_PDF_CONTENT_BYTES_PER_PAGE = 2 * 1024 * 1024
MAX_IMPORTED_TEXT_CHARS = 200_000
_SUPPORTED = {".docx", ".pdf", ".txt", ".md"}
_PDF_HEADER = b"%PDF-"
_MARKDOWN_HTML = re.compile(r"<\s*/?(?:script|style|iframe|object|embed|img|[a-z][^>]*)\b", re.I)


class DocumentImportError(Exception):
    def __init__(self, code: str, public_message: str):
        self.code = code
        self.public_message = public_message
        super().__init__(public_message)


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    title: str
    body_text: str
    warnings: tuple[str, ...]
    source_format: str
    content: tuple[dict, ...] = ()
    source_path: Path | None = None


def _title(filename: object) -> str:
    return Path(str(filename or "")).stem.strip()[:60] or "待编辑知识草稿"


def _safe_text(value: str, *, filename: object) -> tuple[str, str]:
    lines = [line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    body = "\n".join(lines).strip()
    if not body:
        raise DocumentImportError(DOCUMENT_IMPORT_INVALID, "文档未包含可导入的文本正文。")
    if len(body) > MAX_IMPORTED_TEXT_CHARS:
        raise DocumentImportError(DOCUMENT_IMPORT_INVALID, "提取文本超过安全限制，未创建草稿。")
    return _title(filename), body


def _title_from_pdf_text(*, fallback: str, body: str) -> str:
    """Use only an unambiguous short first line as a PDF title candidate."""
    first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if (
        first_line
        and len(first_line) <= 60
        and not re.match(r"^(page|第\s*\d+\s*页)\b", first_line, re.I)
    ):
        return first_line
    return fallback


def _parse_pdf(path: Path, filename: object) -> ParsedDocument:
    with path.open("rb") as source:
        header = source.read(len(_PDF_HEADER))
    if not header.startswith(_PDF_HEADER):
        raise DocumentImportError(DOCUMENT_IMPORT_INVALID, "文件扩展名与实际 PDF 格式不一致。")
    if PdfReader is None:
        raise DocumentImportError(DOCUMENT_IMPORT_FAILED, "PDF 解析组件不可用，未创建草稿。")
    try:
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            raise DocumentImportError(
                DOCUMENT_IMPORT_INVALID, "加密 PDF 不能导入，请提供未加密副本。"
            )
        if not 1 <= len(reader.pages) <= MAX_PDF_PAGES:
            raise DocumentImportError(DOCUMENT_IMPORT_INVALID, "PDF 页数超过安全限制。")
        pages = []
        for page in reader.pages:
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > MAX_PDF_CONTENT_BYTES_PER_PAGE:
                raise DocumentImportError(DOCUMENT_IMPORT_INVALID, "PDF 页面内容超过安全限制。")
            pages.append((page.extract_text(extraction_mode="layout") or "").strip())
    except DocumentImportError:
        raise
    except (OSError, PdfReadError, ValueError) as exc:
        raise DocumentImportError(
            DOCUMENT_IMPORT_INVALID, "PDF 损坏或无法可靠解析，未创建草稿。"
        ) from exc
    title, body = _safe_text("\n\n".join(part for part in pages if part), filename=filename)
    title = _title_from_pdf_text(fallback=title, body=body)
    return ParsedDocument(
        title,
        body,
        ("PDF 图片和复杂表格未转换。",),
        "pdf",
        tuple(plaintext_content(body)),
    )


def _parse_text(path: Path, filename: object, suffix: str) -> ParsedDocument:
    raw = path.read_bytes()
    if b"\0" in raw:
        raise DocumentImportError(
            DOCUMENT_IMPORT_INVALID,
            "文本文件包含二进制内容，未创建草稿。",
        )
    decoded = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            decoded = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise DocumentImportError(
            DOCUMENT_IMPORT_INVALID, "文本编码无法可靠识别，请转换为 UTF-8 后重试。"
        )
    warnings: list[str] = []
    if suffix == ".md":
        if _MARKDOWN_HTML.search(decoded):
            raise DocumentImportError(
                DOCUMENT_IMPORT_INVALID, "Markdown 不能包含原始 HTML 或脚本。"
            )
        headings = re.findall(r"^\s{0,3}#\s+(.+?)\s*$", decoded, re.M)
        title = headings[0].strip()[:60] if headings else _title(filename)
        content, markdown_warnings = markdown_content(decoded)
        warnings.extend(markdown_warnings)
    else:
        title = _title(filename)
        content = plaintext_content(decoded)
    _, body = _safe_text(decoded, filename=filename)
    return ParsedDocument(title, body, tuple(warnings), suffix[1:], tuple(content))


def parse_document_import(*, upload, retain_source: bool = False) -> ParsedDocument:
    suffix = Path(str(getattr(upload, "name", ""))).suffix.lower()
    if suffix not in _SUPPORTED:
        raise DocumentImportError(DOCUMENT_IMPORT_INVALID, "仅支持 .docx、.pdf、.txt 和 .md 文档。")
    if suffix == ".docx":
        try:
            parsed = parse_docx_import(upload=upload)
        except DocxImportError as exc:
            raise DocumentImportError(exc.code, exc.public_message) from exc
        return ParsedDocument(
            parsed.title,
            parsed.body_text,
            parsed.warnings,
            "docx",
            tuple(parsed.content),
        )
    temp, _size, _digest = _copy_upload_to_private_temp(
        upload, max_bytes=settings.KNOWLEDGE_MEDIA_MAX_DOCUMENT_BYTES
    )
    completed = False
    try:
        scan = scan_private_file(temp)
        if scan.status != "clean":
            raise DocumentImportError(
                DOCUMENT_IMPORT_SCAN_FAILED, "文档未通过安全扫描，未创建草稿。"
            )
        parsed = (
            _parse_pdf(temp, upload.name)
            if suffix == ".pdf"
            else _parse_text(temp, upload.name, suffix)
        )
        completed = True
        return ParsedDocument(
            parsed.title,
            parsed.body_text,
            parsed.warnings,
            parsed.source_format,
            parsed.content,
            temp if retain_source else None,
        )
    finally:
        if not retain_source or not completed:
            temp.unlink(missing_ok=True)


def import_document_draft(*, actor, upload, form_data):
    """Create one new draft through the existing Article service; never publish."""
    if Path(str(upload.name)).suffix.lower() == ".docx":
        try:
            return import_docx_draft(actor=actor, upload=upload, form_data=form_data)
        except DocxImportError as exc:
            # Keep one public error contract for every format so a known Word
            # parse failure returns the editor to the form instead of a 500.
            raise DocumentImportError(exc.code, exc.public_message) from exc
    parsed = parse_document_import(upload=upload, retain_source=True)
    stored_paths: list[Path] = []
    try:
        with transaction.atomic():
            article, draft = create_article(
                actor=actor,
                space=form_data["space"],
                category=form_data["category"],
                article_type=form_data["article_type"],
                title=parsed.title,
                summary=parsed.body_text[:500],
                applicable_scope=form_data["applicable_scope"],
                body_text=parsed.body_text,
                change_summary="从知识文档导入创建草稿",
                review_due_at=form_data["review_due_at"],
                owner=form_data.get("owner"),
                audience_policy=form_data["audience_policy"],
                effective_at=form_data["effective_at"],
            )
            if parsed.source_path is None:
                raise DocumentImportError(DOCUMENT_IMPORT_FAILED, "导入源文件未保留，未创建草稿。")
            _source, stored_source_path = retain_import_source(
                draft=draft,
                actor=actor,
                source_path=parsed.source_path,
                original_name=upload.name,
                source_format=parsed.source_format,
                conversion_warnings=parsed.warnings,
            )
            stored_paths.append(stored_source_path)
            autosave_draft(
                actor=actor,
                article=article,
                draft_id=draft.pk,
                expected_lock_version=draft.lock_version,
                title=draft.title,
                summary=draft.summary,
                applicable_scope=draft.applicable_scope,
                body_text=parsed.body_text,
                structured_content=richtext_document(content=list(parsed.content)),
                change_summary=draft.change_summary,
            )
            return article, parsed
    except (ArticleCreationError, DocumentImportError):
        for stored_path in stored_paths:
            stored_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        for stored_path in stored_paths:
            stored_path.unlink(missing_ok=True)
        raise DocumentImportError(DOCUMENT_IMPORT_FAILED, "文档导入失败，未创建草稿。") from exc
    finally:
        if parsed.source_path is not None:
            parsed.source_path.unlink(missing_ok=True)
