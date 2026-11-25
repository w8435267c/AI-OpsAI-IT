"""版本媒体的私有存储、格式验证、扫描和草稿写入服务。"""

from __future__ import annotations

import hashlib
import os
import tempfile
import zipfile
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.db.models import Max
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from apps.audit.models import AuditEvent, AuditEventType
from apps.knowledge.manage_readers import (
    ManageWorkingArticleReadError,
    get_manage_working_article_detail,
)
from apps.knowledge.models import (
    Article,
    ArticleVersion,
    ArticleVersionMedia,
    MediaAsset,
    MediaKind,
    MediaScanStatus,
    VersionStatus,
)
from apps.knowledge.services import (
    ArticleVersionWriteError,
    _has_article_version_object_access,
    _resolve_article_version_write_context,
)

MEDIA_NOT_FOUND_OR_INACCESSIBLE = "MEDIA_NOT_FOUND_OR_INACCESSIBLE"
MEDIA_INVALID_INPUT = "MEDIA_INVALID_INPUT"
MEDIA_NOT_EDITABLE = "MEDIA_NOT_EDITABLE"
MEDIA_SCAN_NOT_CLEAN = "MEDIA_SCAN_NOT_CLEAN"
MEDIA_STORAGE_FAILED = "MEDIA_STORAGE_FAILED"


class KnowledgeMediaError(Exception):
    def __init__(self, code: str, public_message: str):
        self.code = code
        self.public_message = public_message
        super().__init__(public_message)


def get_draft_media(*, actor, kb_no: str):
    """编辑页面只返回当前 working DRAFT 的媒体，不暴露其他版本。"""

    try:
        detail = get_manage_working_article_detail(actor=actor, kb_no=kb_no)
    except ManageWorkingArticleReadError as exc:
        raise KnowledgeMediaError(
            MEDIA_NOT_FOUND_OR_INACCESSIBLE, "草稿不存在或不可访问。"
        ) from exc
    return (
        ArticleVersionMedia.objects.filter(article_version_id=detail.draft_id, is_active=True)
        .select_related("asset")
        .order_by("display_order", "pk")
    )


def get_draft_media_link(*, actor, kb_no: str, media_id):
    """Resolve one clean active current-draft asset for an authorised manager only."""

    try:
        detail = get_manage_working_article_detail(actor=actor, kb_no=kb_no)
    except ManageWorkingArticleReadError:
        return None
    try:
        link = ArticleVersionMedia.objects.select_related("asset", "article_version__article").get(
            pk=media_id,
            article_version_id=detail.draft_id,
            is_active=True,
            asset__scan_status=MediaScanStatus.CLEAN,
        )
    except ArticleVersionMedia.DoesNotExist:
        return None
    path = _private_root() / link.asset.storage_name
    return (link, path) if path.is_file() else None


def get_history_media(*, actor, kb_no: str, version_id):
    """Return only clean image links belonging to one authorised history snapshot."""

    from apps.knowledge.version_readers import (
        ArticleVersionHistoryReadError,
        get_article_version_history_detail,
    )

    try:
        detail = get_article_version_history_detail(actor=actor, kb_no=kb_no, version_id=version_id)
    except ArticleVersionHistoryReadError:
        return None
    return ArticleVersionMedia.objects.filter(
        article_version_id=detail.version_id,
        is_active=True,
        asset__kind=MediaKind.IMAGE,
        asset__scan_status=MediaScanStatus.CLEAN,
    ).select_related("asset")


def get_history_media_link(*, actor, kb_no: str, version_id, media_id):
    """Resolve a clean image only after exact history-version access checks."""

    links = get_history_media(actor=actor, kb_no=kb_no, version_id=version_id)
    if links is None:
        return None
    try:
        link = links.get(pk=media_id)
    except ArticleVersionMedia.DoesNotExist:
        return None
    path = _private_root() / link.asset.storage_name
    return (link, path) if path.is_file() else None


def get_employee_media_link(*, actor, kb_no: str, media_id):
    """按员工受众和当前发布版本取媒体；失败时不泄露资源存在性。"""

    from apps.knowledge.readers import employee_visible_articles

    article = employee_visible_articles(actor, base=Article.objects.filter(kb_no=kb_no)).first()
    if article is None or article.current_published_version_id is None:
        return None
    try:
        link = ArticleVersionMedia.objects.select_related("asset", "article_version").get(
            pk=media_id,
            article_version_id=article.current_published_version_id,
            is_active=True,
            asset__scan_status=MediaScanStatus.CLEAN,
        )
    except ArticleVersionMedia.DoesNotExist:
        return None
    path = _private_root() / link.asset.storage_name
    if not path.is_file():
        return None
    return link, path


def _raise_invalid(message: str) -> None:
    raise KnowledgeMediaError(MEDIA_INVALID_INPUT, message)


def _private_root() -> Path:
    root = Path(settings.MEDIA_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _extension(name: object) -> str:
    if not isinstance(name, str):
        _raise_invalid("文件名无效。")
    return Path(name).suffix.lower()


def _copy_upload_to_private_temp(upload, *, max_bytes: int) -> tuple[Path, int, str]:
    if upload is None or not hasattr(upload, "chunks"):
        _raise_invalid("请选择要上传的文件。")
    root = _private_root()
    incoming = root / ".incoming"
    incoming.mkdir(exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    handle = tempfile.NamedTemporaryFile(dir=incoming, delete=False)
    path = Path(handle.name)
    try:
        with handle:
            for chunk in upload.chunks():
                total += len(chunk)
                if total > max_bytes:
                    _raise_invalid(f"文件超过 {max_bytes // (1024 * 1024)} MB 大小限制。")
                digest.update(chunk)
                handle.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    if total == 0:
        path.unlink(missing_ok=True)
        _raise_invalid("不能上传空文件。")
    return path, total, digest.hexdigest()


def _verify_image(path: Path, suffix: str) -> tuple[str, str, int]:
    if suffix not in {".png", ".jpg", ".jpeg"}:
        _raise_invalid("正文插图仅支持 PNG、JPEG 格式。")
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            actual = image.format
    except (UnidentifiedImageError, OSError, ValueError):
        _raise_invalid("文件内容不是有效的 PNG 或 JPEG 图片。")
    accepted = {
        ".png": ("PNG", "image/png"),
        ".jpg": ("JPEG", "image/jpeg"),
        ".jpeg": ("JPEG", "image/jpeg"),
    }
    expected, content_type = accepted[suffix]
    if actual != expected:
        _raise_invalid("文件扩展名与实际图片格式不一致。")
    return MediaKind.IMAGE, content_type, settings.KNOWLEDGE_MEDIA_MAX_IMAGE_BYTES


def _verify_docx(path: Path, suffix: str) -> tuple[str, str, int]:
    if suffix != ".docx":
        _raise_invalid("附件仅支持 .docx 格式，不接受宏文档。")
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if archive.testzip() is not None:
                _raise_invalid("Word 文件损坏，无法上传。")
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                _raise_invalid("文件内容不是有效的 .docx 文档。")
            content_types = archive.read("[Content_Types].xml").lower()
    except (OSError, zipfile.BadZipFile, KeyError):
        _raise_invalid("文件内容不是有效的 .docx 文档。")
    if b"macroenabled" in content_types or any("vbaproject" in name.lower() for name in names):
        _raise_invalid("不接受包含宏的 Word 文档。")
    return (
        MediaKind.DOCUMENT,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        settings.KNOWLEDGE_MEDIA_MAX_DOCUMENT_BYTES,
    )


def _validate_actual_format(path: Path, name: object) -> tuple[str, str, int]:
    suffix = _extension(name)
    if suffix in {".png", ".jpg", ".jpeg"}:
        return _verify_image(path, suffix)
    return _verify_docx(path, suffix)


def _scan_asset(asset: MediaAsset, path: Path) -> None:
    from apps.knowledge.media_scanning import scan_private_file

    result = scan_private_file(path)
    asset.scan_status = result.status
    asset.scan_message = result.message
    asset.scanned_at = timezone.now()
    asset.save(update_fields=("scan_status", "scan_message", "scanned_at"))


def upload_draft_media(
    *, actor, kb_no: str, draft_id, upload, caption: object, body_position: object
):
    """上传到私有区、扫描并创建当前 DRAFT 的版本关联。"""

    try:
        detail = get_manage_working_article_detail(actor=actor, kb_no=kb_no)
    except ManageWorkingArticleReadError as exc:
        raise KnowledgeMediaError(
            MEDIA_NOT_FOUND_OR_INACCESSIBLE, "草稿不存在或不可访问。"
        ) from exc
    if str(detail.draft_id) != str(draft_id):
        raise KnowledgeMediaError(MEDIA_NOT_EDITABLE, "该草稿已更新，请刷新后再上传文件。")
    if not isinstance(caption, str) or len(caption) > 500:
        _raise_invalid("图片说明不能超过 500 个字符。")

    suffix = _extension(getattr(upload, "name", None))
    initial_limit = (
        settings.KNOWLEDGE_MEDIA_MAX_IMAGE_BYTES
        if suffix in {".png", ".jpg", ".jpeg"}
        else settings.KNOWLEDGE_MEDIA_MAX_DOCUMENT_BYTES
    )
    temp_path, size_bytes, digest = _copy_upload_to_private_temp(upload, max_bytes=initial_limit)
    try:
        kind, content_type, max_bytes = _validate_actual_format(
            temp_path, getattr(upload, "name", None)
        )
        if size_bytes > max_bytes:
            _raise_invalid(f"文件超过 {max_bytes // (1024 * 1024)} MB 大小限制。")
        if kind == MediaKind.IMAGE:
            try:
                position = int(body_position)
            except (TypeError, ValueError):
                _raise_invalid("请填写插入到正文第几段后。")
            if position < 0:
                _raise_invalid("图片插入位置不能小于 0。")
        else:
            position = None
            if caption.strip():
                _raise_invalid("Word 附件不支持图片说明。")

        with transaction.atomic():
            draft = (
                ArticleVersion.objects.select_for_update()
                .select_related("article")
                .get(pk=detail.draft_id)
            )
            current_actor, current_article, is_admin = _resolve_article_version_write_context(
                actor=actor, article=draft.article
            )
            if draft.status != VersionStatus.DRAFT or not _has_article_version_object_access(
                actor=current_actor, article=current_article, is_admin=is_admin
            ):
                raise KnowledgeMediaError(MEDIA_NOT_FOUND_OR_INACCESSIBLE, "草稿不存在或不可访问。")
            asset = MediaAsset(
                kind=kind,
                original_name=Path(upload.name).name,
                storage_name=f"media/{UUID(str(draft.pk))}/{os.urandom(16).hex()}.bin",
                content_type=content_type,
                size_bytes=size_bytes,
                sha256=digest,
                scan_status=MediaScanStatus.PENDING,
                created_by=current_actor,
            )
            asset.full_clean()
            asset.save(force_insert=True)
            destination = _private_root() / asset.storage_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temp_path, destination)
            _scan_asset(asset, destination)
            display_order = (
                draft.media_links.filter(is_active=True).aggregate(maximum=Max("display_order"))[
                    "maximum"
                ]
                or -1
            ) + 1
            link = ArticleVersionMedia(
                article_version=draft,
                asset=asset,
                display_order=display_order,
                body_position=position,
                caption=caption.strip(),
            )
            link.full_clean()
            link.save(force_insert=True)
            AuditEvent.objects.create(
                event_type=AuditEventType.MEDIA_UPLOADED,
                actor=current_actor,
                article=draft.article,
                article_version=draft,
                metadata={
                    "media_id": str(asset.pk),
                    "kind": kind,
                    "scan_status": asset.scan_status,
                },
            )
            return link
    except KnowledgeMediaError:
        raise
    except (ArticleVersionWriteError, ValidationError, DatabaseError, OSError) as exc:
        raise KnowledgeMediaError(MEDIA_STORAGE_FAILED, "文件保存失败，请稍后重试。") from exc
    finally:
        temp_path.unlink(missing_ok=True)


def remove_draft_media(*, actor, kb_no: str, draft_id, media_id) -> None:
    try:
        detail = get_manage_working_article_detail(actor=actor, kb_no=kb_no)
    except ManageWorkingArticleReadError as exc:
        raise KnowledgeMediaError(
            MEDIA_NOT_FOUND_OR_INACCESSIBLE, "草稿不存在或不可访问。"
        ) from exc
    if str(detail.draft_id) != str(draft_id):
        raise KnowledgeMediaError(MEDIA_NOT_EDITABLE, "该草稿已更新，请刷新后再操作。")
    try:
        with transaction.atomic():
            link = (
                ArticleVersionMedia.objects.select_for_update()
                .select_related("article_version__article")
                .get(pk=media_id, article_version_id=detail.draft_id, is_active=True)
            )
            current_actor, current_article, is_admin = _resolve_article_version_write_context(
                actor=actor, article=link.article_version.article
            )
            if (
                link.article_version.status != VersionStatus.DRAFT
                or not _has_article_version_object_access(
                    actor=current_actor, article=current_article, is_admin=is_admin
                )
            ):
                raise KnowledgeMediaError(MEDIA_NOT_FOUND_OR_INACCESSIBLE, "媒体不存在或不可访问。")
            link.is_active = False
            link.save(update_fields=("is_active",))
    except ArticleVersionMedia.DoesNotExist as exc:
        raise KnowledgeMediaError(
            MEDIA_NOT_FOUND_OR_INACCESSIBLE, "媒体不存在或不可访问。"
        ) from exc


def copy_active_media_links(*, source: ArticleVersion, destination: ArticleVersion) -> dict:
    """创建新工作版本时复制关联，而非共享可变关联；资产文件保持不可变。"""

    link_id_map = {}
    for link in source.media_links.filter(is_active=True).select_related("asset"):
        copied_link = ArticleVersionMedia.objects.create(
            article_version=destination,
            asset=link.asset,
            display_order=link.display_order,
            body_position=link.body_position,
            caption=link.caption,
        )
        link_id_map[link.pk] = copied_link.pk
    return link_id_map


def ensure_version_media_publishable(*, version: ArticleVersion) -> None:
    """发布路径的服务端门禁；任何非 clean 状态均拒绝。"""

    non_clean = version.media_links.filter(is_active=True).exclude(
        asset__scan_status=MediaScanStatus.CLEAN
    )
    if non_clean.exists():
        raise KnowledgeMediaError(MEDIA_SCAN_NOT_CLEAN, "存在未通过扫描的媒体，不能发布。")
