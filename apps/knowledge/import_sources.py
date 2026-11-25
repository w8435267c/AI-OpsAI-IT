"""Private retention of successfully scanned import originals."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from uuid import UUID

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.knowledge.media_services import _private_root
from apps.knowledge.models import (
    ArticleVersion,
    ArticleVersionImportSource,
    MediaAsset,
    MediaKind,
    MediaScanStatus,
)

CONTENT_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
}


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def retain_import_source(
    *,
    draft: ArticleVersion,
    actor,
    source_path: Path,
    original_name: str,
    source_format: str,
    conversion_warnings: tuple[str, ...],
) -> tuple[ArticleVersionImportSource, Path]:
    """Copy a parser-owned, clean temporary file to private storage for this version.

    The caller owns transaction rollback and removes the returned destination if a
    later write fails.  No employee-facing media link is created here.
    """

    if source_format not in CONTENT_TYPES or not source_path.is_file():
        raise ValidationError("导入源文件无效，未保留。")
    destination = _private_root() / f"sources/{UUID(str(draft.pk))}/{source_format}.bin"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, destination)
    try:
        asset = MediaAsset(
            kind=MediaKind.DOCUMENT,
            original_name=Path(original_name).name,
            storage_name=str(destination.relative_to(_private_root())).replace("\\", "/"),
            content_type=CONTENT_TYPES[source_format],
            size_bytes=source_path.stat().st_size,
            sha256=sha256_file(source_path),
            scan_status=MediaScanStatus.CLEAN,
            scan_message="扫描通过。",
            scanned_at=timezone.now(),
            created_by=actor,
        )
        asset.full_clean()
        asset.save(force_insert=True)
        source = ArticleVersionImportSource(
            article_version=draft,
            asset=asset,
            source_format=source_format,
            conversion_warnings=list(conversion_warnings),
        )
        source.full_clean()
        source.save(force_insert=True)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return source, destination
