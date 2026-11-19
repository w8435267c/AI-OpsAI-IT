"""Safe, deliberately small OOXML reader for one knowledge-draft import."""

from __future__ import annotations

import hashlib
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.audit.models import AuditEvent, AuditEventType
from apps.knowledge.media_scanning import scan_private_file
from apps.knowledge.media_services import (
    KnowledgeMediaError,
    _copy_upload_to_private_temp,
    _private_root,
    _verify_docx,
    _verify_image,
)
from apps.knowledge.models import ArticleVersionMedia, MediaAsset, MediaKind, MediaScanStatus
from apps.knowledge.services import ArticleCreationError, create_article

DOCX_IMPORT_INVALID = "DOCX_IMPORT_INVALID"
DOCX_IMPORT_SCAN_FAILED = "DOCX_IMPORT_SCAN_FAILED"
DOCX_IMPORT_FAILED = "DOCX_IMPORT_FAILED"

MAX_DOCX_ENTRIES = 256
MAX_DOCX_UNPACKED_BYTES = 25 * 1024 * 1024
MAX_DOCX_IMAGES = 20

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


class DocxImportError(Exception):
    def __init__(self, code: str, public_message: str):
        self.code = code
        self.public_message = public_message
        super().__init__(public_message)


@dataclass(frozen=True, slots=True)
class ParsedImage:
    name: str
    path: Path
    body_position: int


@dataclass(frozen=True, slots=True)
class ParsedDocx:
    title: str
    body_text: str
    images: tuple[ParsedImage, ...]
    warnings: tuple[str, ...]


def _fail(code: str, message: str) -> None:
    raise DocxImportError(code, message)


def _safe_member_name(name: str) -> bool:
    path = Path(name)
    return not path.is_absolute() and ".." not in path.parts and "\\" not in name


def _document_title(filename: object) -> str:
    stem = Path(str(filename or "")).stem.strip()
    return stem[:60] or "待编辑知识草稿"


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(f".//{{{W_NS}}}t")).strip()


def _list_prefix(
    paragraph: ElementTree.Element,
    counters: dict[str, int],
    number_formats: dict[tuple[str, str], str],
) -> str:
    num_id = paragraph.find(f"./{{{W_NS}}}pPr/{{{W_NS}}}numPr/{{{W_NS}}}numId")
    if num_id is None:
        return ""
    key = num_id.get(f"{{{W_NS}}}val", "default")
    level = paragraph.find(f"./{{{W_NS}}}pPr/{{{W_NS}}}numPr/{{{W_NS}}}ilvl")
    level_value = level.get(f"{{{W_NS}}}val", "0") if level is not None else "0"
    if number_formats.get((key, level_value)) == "bullet":
        return "- "
    counters[key] = counters.get(key, 0) + 1
    # OOXML numbering definitions can be arbitrary. Preserve ordering without
    # pretending to reproduce Word's layout when the definition is unavailable.
    return f"{counters[key]}. " if level_value == "0" else "- "


def _read_number_formats(archive: zipfile.ZipFile) -> dict[tuple[str, str], str]:
    try:
        root = ElementTree.fromstring(archive.read("word/numbering.xml"))
    except KeyError:
        return {}
    except ElementTree.ParseError:
        _fail(DOCX_IMPORT_INVALID, "Word 列表定义损坏，无法导入。")

    abstract_ids: dict[str, str] = {}
    formats: dict[tuple[str, str], str] = {}
    for number in root.findall(f"{{{W_NS}}}num"):
        abstract = number.find(f"./{{{W_NS}}}abstractNumId")
        number_id = number.get(f"{{{W_NS}}}numId")
        if abstract is not None and number_id:
            abstract_ids[number_id] = abstract.get(f"{{{W_NS}}}val", "")
    for abstract in root.findall(f"{{{W_NS}}}abstractNum"):
        abstract_id = abstract.get(f"{{{W_NS}}}abstractNumId")
        for level in abstract.findall(f"{{{W_NS}}}lvl"):
            format_node = level.find(f"./{{{W_NS}}}numFmt")
            level_id = level.get(f"{{{W_NS}}}ilvl", "0")
            if abstract_id and format_node is not None:
                formats[(abstract_id, level_id)] = format_node.get(f"{{{W_NS}}}val", "")
    return {
        (number_id, level): formats.get((abstract_id, level), "")
        for number_id, abstract_id in abstract_ids.items()
        for _abstract, level in formats
        if _abstract == abstract_id
    }


def _read_relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    try:
        root = ElementTree.fromstring(archive.read("word/_rels/document.xml.rels"))
    except (KeyError, ElementTree.ParseError) as exc:
        _fail(DOCX_IMPORT_INVALID, "Word 关系文件损坏，无法安全导入。")
        raise AssertionError from exc
    relationships = {}
    for relationship in root.findall(f"{{{REL_NS}}}Relationship"):
        if relationship.get("TargetMode") == "External":
            _fail(DOCX_IMPORT_INVALID, "Word 包含外部资源引用，不能导入。")
        target = relationship.get("Target")
        relation_id = relationship.get("Id")
        if target and relation_id:
            if not _safe_member_name(target):
                _fail(DOCX_IMPORT_INVALID, "Word 包含不安全的关联路径，无法导入。")
            relationships[relation_id] = str(Path("word") / target).replace("\\", "/")
    return relationships


def _is_title_paragraph(paragraph: ElementTree.Element) -> bool:
    style = paragraph.find(f"./{{{W_NS}}}pPr/{{{W_NS}}}pStyle")
    if style is None:
        return False
    return style.get(f"{{{W_NS}}}val", "").casefold() in {"title", "标题"}


def _sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def parse_docx_import(*, upload) -> ParsedDocx:
    """Validate, scan and extract a bounded subset of OOXML into private temp files."""

    temp_path, _size, _digest = _copy_upload_to_private_temp(
        upload, max_bytes=settings.KNOWLEDGE_MEDIA_MAX_DOCUMENT_BYTES
    )
    image_paths: list[Path] = []
    completed = False
    try:
        _verify_docx(temp_path, Path(upload.name).suffix.lower())
        scan = scan_private_file(temp_path)
        if scan.status != "clean":
            _fail(DOCX_IMPORT_SCAN_FAILED, "Word 文件未通过安全扫描，未创建草稿。")
        with zipfile.ZipFile(temp_path) as archive:
            entries = archive.infolist()
            if (
                len(entries) > MAX_DOCX_ENTRIES
                or sum(item.file_size for item in entries) > MAX_DOCX_UNPACKED_BYTES
            ):
                _fail(DOCX_IMPORT_INVALID, "Word 解包内容超过安全限制，无法导入。")
            if any(not _safe_member_name(item.filename) for item in entries):
                _fail(DOCX_IMPORT_INVALID, "Word 包含不安全的文件路径，无法导入。")
            names = {item.filename for item in entries}
            forbidden = ("word/vbaproject.bin", "word/embeddings/", "word/activeX/")
            if any(name.lower().startswith(forbidden) for name in names):
                _fail(DOCX_IMPORT_INVALID, "Word 包含宏或嵌入对象，不能导入。")
            try:
                document = ElementTree.fromstring(archive.read("word/document.xml"))
            except (KeyError, ElementTree.ParseError) as exc:
                _fail(DOCX_IMPORT_INVALID, "Word 正文损坏，无法导入。")
                raise AssertionError from exc
            relationships = _read_relationships(archive)
            number_formats = _read_number_formats(archive)
            body_parts: list[str] = []
            images: list[ParsedImage] = []
            warnings: list[str] = []
            counters: dict[str, int] = {}
            title = ""
            for child in document.findall(f"./{{{W_NS}}}body/*"):
                if child.tag == f"{{{W_NS}}}tbl":
                    warnings.append("表格未转换，请在草稿中补充。")
                    continue
                if child.tag != f"{{{W_NS}}}p":
                    continue
                text = _paragraph_text(child)
                is_title = not title and text and _is_title_paragraph(child)
                if is_title:
                    title = text[:60]
                elif text:
                    body_parts.append(_list_prefix(child, counters, number_formats) + text)
                if child.findall(f".//{{{WP_NS}}}anchor"):
                    warnings.append("浮动图片未转换，请在草稿中手动补充。")
                for inline in child.findall(f".//{{{WP_NS}}}inline"):
                    for blip in inline.findall(f".//{{{A_NS}}}blip"):
                        relation_id = blip.get(f"{{{R_NS}}}embed")
                        target = relationships.get(relation_id or "")
                        if target is None or target not in names:
                            _fail(DOCX_IMPORT_INVALID, "Word 图片关系无效，无法导入。")
                        if len(images) >= MAX_DOCX_IMAGES:
                            _fail(DOCX_IMPORT_INVALID, "Word 图片数量超过安全限制，无法导入。")
                        suffix = Path(target).suffix.lower()
                        if suffix not in {".png", ".jpg", ".jpeg"}:
                            warnings.append("存在非 PNG/JPEG 图片，未转换。")
                            continue
                        extracted = (
                            _private_root()
                            / ".incoming"
                            / (f"docx-{uuid.uuid4().hex}-{Path(target).name}")
                        )
                        extracted.parent.mkdir(parents=True, exist_ok=True)
                        extracted.write_bytes(archive.read(target))
                        if extracted.stat().st_size > settings.KNOWLEDGE_MEDIA_MAX_IMAGE_BYTES:
                            _fail(DOCX_IMPORT_INVALID, "Word 内嵌图片超过 5 MB 大小限制。")
                        _verify_image(extracted, suffix)
                        image_scan = scan_private_file(extracted)
                        if image_scan.status != "clean":
                            _fail(
                                DOCX_IMPORT_SCAN_FAILED, "Word 内嵌图片未通过安全扫描，未创建草稿。"
                            )
                        image_paths.append(extracted)
                        images.append(ParsedImage(Path(target).name, extracted, len(body_parts)))
            if not body_parts:
                _fail(DOCX_IMPORT_INVALID, "Word 未包含可导入的正文段落，未创建草稿。")
            if not title:
                title = _document_title(upload.name)
            if not title.strip():
                title = _document_title(upload.name)
            # The existing employee reader treats each ``splitlines`` result as
            # one body paragraph.  Use one newline here so a Word paragraph and
            # its media position retain the same numbering after save/reopen.
            body_text = "\n".join(body_parts).strip()
            result = ParsedDocx(
                title,
                body_text,
                tuple(images),
                tuple(warnings),
            )
            completed = True
            return result
    except KnowledgeMediaError as exc:
        _fail(DOCX_IMPORT_INVALID, exc.public_message)
    finally:
        temp_path.unlink(missing_ok=True)
        # Ownership is transferred to the ParsedDocx only after successful return.
        # Failure must never leave extracted blobs in the private incoming area.
        if not completed:
            for image_path in image_paths:
                image_path.unlink(missing_ok=True)


def import_docx_draft(*, actor, upload, form_data) -> tuple[object, ParsedDocx]:
    """Create a new draft and its scanned image links, or leave no draft behind."""

    parsed = parse_docx_import(upload=upload)
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
                change_summary="从 Word 导入创建草稿",
                review_due_at=form_data["review_due_at"],
                owner=form_data.get("owner"),
                audience_policy=form_data["audience_policy"],
                effective_at=form_data["effective_at"],
            )
            for order, image in enumerate(parsed.images):
                suffix = Path(image.name).suffix.lower()
                _kind, content_type, _max_bytes = _verify_image(image.path, suffix)
                asset = MediaAsset(
                    kind=MediaKind.IMAGE,
                    original_name=image.name,
                    storage_name=f"media/{UUID(str(draft.pk))}/{order:04d}.bin",
                    content_type=content_type,
                    size_bytes=image.path.stat().st_size,
                    sha256=_sha256_file(image.path),
                    scan_status=MediaScanStatus.CLEAN,
                    scan_message="扫描通过。",
                    scanned_at=timezone.now(),
                    created_by=actor,
                )
                asset.full_clean()
                asset.save()
                destination = _private_root() / asset.storage_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(image.path, destination)
                stored_paths.append(destination)
                ArticleVersionMedia.objects.create(
                    article_version=draft,
                    asset=asset,
                    display_order=order,
                    body_position=image.body_position,
                    caption="",
                )
            AuditEvent.objects.create(
                event_type=AuditEventType.MEDIA_UPLOADED,
                actor=actor,
                article=article,
                article_version=draft,
                metadata={"source": "docx_import", "image_count": len(parsed.images)},
            )
            return article, parsed
    except (
        ArticleCreationError,
        DatabaseError,
        OSError,
        KnowledgeMediaError,
        ValidationError,
    ) as exc:
        for stored_path in stored_paths:
            stored_path.unlink(missing_ok=True)
        if isinstance(exc, ArticleCreationError):
            raise
        _fail(DOCX_IMPORT_FAILED, "Word 导入失败，未创建草稿。")
    finally:
        for image in parsed.images:
            image.path.unlink(missing_ok=True)
