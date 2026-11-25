"""Versioned, server-validated knowledge-body formats."""

from __future__ import annotations

from copy import deepcopy
from urllib.parse import urlparse
from uuid import UUID

PLAINTEXT_BODY_FORMAT = "opsai.plaintext/1"
RICHTEXT_BODY_FORMAT = "opsai.richtext/1"
RICHTEXT_SCHEMA_VERSION = 1

MAX_CONTENT_NODES = 2_000
MAX_CONTENT_DEPTH = 12
MAX_CONTENT_TEXT_CHARS = 200_000
MAX_LINK_LENGTH = 2_048
MAX_TABLE_SPAN = 20
SAFE_TEXT_COLORS = frozenset(
    {"black", "gray", "red", "orange", "yellow", "green", "blue", "purple"}
)
_INLINE_NODE_TYPES = frozenset({"text", "hardBreak"})
_BLOCK_NODE_TYPES = frozenset(
    {
        "heading",
        "paragraph",
        "orderedList",
        "bulletList",
        "codeBlock",
        "blockquote",
        "table",
        "image",
        "callout",
    }
)
_MARK_TYPES = frozenset({"bold", "italic", "underline", "color", "link"})


class RichTextContentError(ValueError):
    """Raised when untrusted structured content cannot become a version snapshot."""


def build_plaintext_body(body_text: str) -> tuple[dict[str, str], str]:
    """Keep the historical body contract for existing callers and versions."""

    if not isinstance(body_text, str):
        raise ValueError("正文必须是字符串。")
    if not body_text.strip():
        raise ValueError("正文不能为空。")
    return {"format": PLAINTEXT_BODY_FORMAT, "text": body_text}, body_text


def _invalid(message: str) -> None:
    raise RichTextContentError(message)


def _text(value: object, *, field: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        _invalid(f"富文本{field}必须是字符串。")
    if not allow_empty and not value.strip():
        _invalid(f"富文本{field}不能为空。")
    return value


def _safe_link(value: object) -> str:
    href = _text(value, field="链接地址")
    if len(href) > MAX_LINK_LENGTH:
        _invalid("富文本链接地址过长。")
    parsed = urlparse(href)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        _invalid("富文本链接仅允许完整的 HTTP 或 HTTPS 地址。")
    return href


def _normalise_marks(value: object) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        _invalid("富文本标记必须是数组。")
    marks: list[dict[str, str]] = []
    seen: set[str] = set()
    for mark in value:
        if not isinstance(mark, dict):
            _invalid("富文本标记必须是对象。")
        mark_type = mark.get("type")
        if mark_type not in _MARK_TYPES or mark_type in seen:
            _invalid("富文本包含不支持或重复的文字标记。")
        seen.add(mark_type)
        if mark_type == "color":
            color = mark.get("color")
            if color not in SAFE_TEXT_COLORS:
                _invalid("富文本颜色不在允许范围内。")
            marks.append({"type": "color", "color": color})
        elif mark_type == "link":
            marks.append({"type": "link", "href": _safe_link(mark.get("href"))})
        else:
            if set(mark) != {"type"}:
                _invalid("富文本样式标记包含不支持的属性。")
            marks.append({"type": mark_type})
    return marks


def _normalise_inline(node: object, *, depth: int, state: dict[str, int]) -> dict:
    if not isinstance(node, dict) or node.get("type") not in _INLINE_NODE_TYPES:
        _invalid("富文本行内节点无效。")
    node_type = node["type"]
    if node_type == "hardBreak":
        if set(node) != {"type"}:
            _invalid("换行节点包含不支持的属性。")
        return {"type": node_type}
    text = _text(node.get("text"), field="文本", allow_empty=True)
    state["chars"] += len(text)
    return {"type": "text", "text": text, "marks": _normalise_marks(node.get("marks"))}


def _normalise_inline_content(
    value: object, *, depth: int, state: dict[str, int], allow_empty: bool = False
) -> list[dict]:
    if not isinstance(value, list):
        _invalid("富文本内容不能为空。")
    if not value and not allow_empty:
        _invalid("富文本内容不能为空。")
    return [_normalise_node(item, depth=depth + 1, state=state, inline_only=True) for item in value]


def _normalise_node(
    node: object,
    *,
    depth: int,
    state: dict[str, int],
    inline_only: bool = False,
) -> dict:
    state["nodes"] += 1
    if state["nodes"] > MAX_CONTENT_NODES or depth > MAX_CONTENT_DEPTH:
        _invalid("富文本内容超过安全复杂度限制。")
    if inline_only:
        return _normalise_inline(node, depth=depth, state=state)
    if not isinstance(node, dict):
        _invalid("富文本节点必须是对象。")
    node_type = node.get("type")
    if node_type not in _BLOCK_NODE_TYPES:
        _invalid("富文本包含不支持的节点。")
    if node_type in {"heading", "paragraph"}:
        # Tiptap deliberately represents an empty paragraph (and an empty
        # heading while it is being edited) as an empty content array.  It is
        # a valid structural node, not an empty article; the document-level
        # readable-text check below remains the non-empty-body guard.
        content = _normalise_inline_content(
            node.get("content"), depth=depth, state=state, allow_empty=True
        )
        result = {"type": node_type, "content": content}
        if node_type == "heading":
            level = node.get("level")
            if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 6:
                _invalid("标题级别必须是 1 到 6。")
            result["level"] = level
        return result
    if node_type in {"orderedList", "bulletList"}:
        items = node.get("items")
        if not isinstance(items, list) or not items:
            _invalid("列表必须包含至少一个列表项。")
        normalised_items = []
        for item in items:
            if not isinstance(item, dict) or set(item) != {"content"}:
                _invalid("列表项包含不支持的属性。")
            content = item["content"]
            if not isinstance(content, list) or not content:
                _invalid("列表项内容不能为空。")
            normalised_items.append(
                {
                    "content": [
                        _normalise_node(child, depth=depth + 1, state=state) for child in content
                    ]
                }
            )
        return {"type": node_type, "items": normalised_items}
    if node_type == "codeBlock":
        text = _text(node.get("text"), field="代码块", allow_empty=True)
        language = node.get("language", "")
        if not isinstance(language, str) or len(language) > 32:
            _invalid("代码块语言无效。")
        state["chars"] += len(text)
        return {"type": node_type, "text": text, "language": language}
    if node_type == "blockquote":
        content = node.get("content")
        if not isinstance(content, list) or not content:
            _invalid("引用内容不能为空。")
        return {
            "type": node_type,
            "content": [_normalise_node(child, depth=depth + 1, state=state) for child in content],
        }
    if node_type == "table":
        rows = node.get("rows")
        if not isinstance(rows, list) or not rows:
            _invalid("表格必须包含至少一行。")
        normalised_rows = []
        column_count = None
        active_rowspans: list[int] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"cells"}:
                _invalid("表格行包含不支持的属性。")
            cells = row["cells"]
            if not isinstance(cells, list) or not cells:
                _invalid("表格行不能为空。")
            normalised_cells = []
            covered = [span > 0 for span in active_rowspans]
            next_rowspans = [max(span - 1, 0) for span in active_rowspans]
            cursor = 0
            for cell in cells:
                if not isinstance(cell, dict) or set(cell) - {
                    "type",
                    "content",
                    "colspan",
                    "rowspan",
                }:
                    _invalid("表格单元格包含不支持的属性。")
                if cell["type"] not in {"tableCell", "tableHeader"}:
                    _invalid("表格单元格类型无效。")
                normalised_cell = {
                    "type": cell["type"],
                    "content": _normalise_inline_content(
                        cell["content"], depth=depth + 1, state=state, allow_empty=True
                    ),
                }
                for span_name in ("colspan", "rowspan"):
                    span = cell.get(span_name, 1)
                    if (
                        not isinstance(span, int)
                        or isinstance(span, bool)
                        or not 1 <= span <= MAX_TABLE_SPAN
                    ):
                        _invalid("表格合并单元格范围无效。")
                    if span != 1:
                        normalised_cell[span_name] = span
                while cursor < len(covered) and covered[cursor]:
                    cursor += 1
                colspan = normalised_cell.get("colspan", 1)
                rowspan = normalised_cell.get("rowspan", 1)
                if column_count is not None and cursor + colspan > column_count:
                    _invalid("表格合并单元格超出列范围。")
                while len(covered) < cursor + colspan:
                    covered.append(False)
                    next_rowspans.append(0)
                if any(covered[cursor : cursor + colspan]):
                    _invalid("表格合并单元格相互重叠。")
                for column in range(cursor, cursor + colspan):
                    covered[column] = True
                    next_rowspans[column] = max(next_rowspans[column], rowspan - 1)
                cursor += colspan
                normalised_cells.append(normalised_cell)
            if column_count is None:
                column_count = len(covered)
            elif len(covered) != column_count or not all(covered):
                _invalid("表格各行列数必须一致。")
            normalised_rows.append({"cells": normalised_cells})
            active_rowspans = next_rowspans
        return {"type": node_type, "rows": normalised_rows}
    if node_type == "image":
        if set(node) - {"type", "media_link_id", "caption", "width"}:
            _invalid("图片节点包含不支持的属性。")
        media_link_id = _text(node.get("media_link_id"), field="图片版本媒体 ID")
        try:
            media_link_id = str(UUID(media_link_id))
        except (TypeError, ValueError) as exc:
            raise RichTextContentError("图片只能引用当前版本的内部媒体 ID。") from exc
        caption = _text(node.get("caption", ""), field="图片说明", allow_empty=True)
        width = node.get("width", "full")
        if width not in {"full", "wide", "half"}:
            _invalid("图片宽度无效。")
        return {
            "type": node_type,
            "media_link_id": media_link_id,
            "caption": caption,
            "width": width,
        }
    # callout
    kind = node.get("kind")
    if kind not in {"callout", "warning", "info"}:
        _invalid("提示框类型无效。")
    content = node.get("content")
    if not isinstance(content, list) or not content:
        _invalid("提示框内容不能为空。")
    return {
        "type": "callout",
        "kind": kind,
        "content": [_normalise_node(child, depth=depth + 1, state=state) for child in content],
    }


def validate_richtext_body(body: object) -> tuple[dict, str]:
    """Validate untrusted JSON and derive its only searchable text projection."""

    if not isinstance(body, dict):
        _invalid("富文本正文必须是对象。")
    if (
        body.get("format") != RICHTEXT_BODY_FORMAT
        or body.get("schema_version") != RICHTEXT_SCHEMA_VERSION
    ):
        _invalid("富文本正文格式或 schema_version 无效。")
    if set(body) != {"format", "schema_version", "content"}:
        _invalid("富文本正文包含不支持的顶层属性。")
    content = body.get("content")
    if not isinstance(content, list) or not content:
        _invalid("富文本正文不能为空。")
    state = {"nodes": 0, "chars": 0}
    normalised = [_normalise_node(node, depth=1, state=state) for node in content]
    if state["chars"] > MAX_CONTENT_TEXT_CHARS:
        _invalid("富文本正文超过安全大小限制。")
    plaintext = richtext_to_plaintext({"content": normalised})
    if not plaintext.strip():
        _invalid("富文本正文不包含可读取文本。")
    return (
        {
            "format": RICHTEXT_BODY_FORMAT,
            "schema_version": RICHTEXT_SCHEMA_VERSION,
            "content": normalised,
        },
        plaintext,
    )


def richtext_to_plaintext(body: dict) -> str:
    """Render only text values into a deterministic search/index projection."""

    def inline_text(nodes: list[dict]) -> str:
        return "".join("\n" if node["type"] == "hardBreak" else node["text"] for node in nodes)

    def block_text(node: dict) -> list[str]:
        node_type = node["type"]
        if node_type in {"heading", "paragraph"}:
            return [inline_text(node["content"])]
        if node_type == "codeBlock":
            return [node["text"]]
        if node_type == "image":
            return [node["caption"]] if node["caption"] else []
        if node_type in {"blockquote", "callout"}:
            return [part for child in node["content"] for part in block_text(child)]
        if node_type in {"orderedList", "bulletList"}:
            return [
                part
                for item in node["items"]
                for child in item["content"]
                for part in block_text(child)
            ]
        if node_type == "table":
            return [
                " | ".join(inline_text(cell["content"]) for cell in row["cells"])
                for row in node["rows"]
            ]
        return []

    return "\n".join(part for node in body["content"] for part in block_text(node)).strip()


def richtext_media_link_ids(body: dict) -> frozenset[UUID]:
    """Return only internal version-media references from a validated rich snapshot."""

    def descendants(nodes: list[dict]) -> list[dict]:
        result: list[dict] = []
        for node in nodes:
            result.append(node)
            if node["type"] in {"blockquote", "callout"}:
                result.extend(descendants(node["content"]))
            elif node["type"] in {"orderedList", "bulletList"}:
                for item in node["items"]:
                    result.extend(descendants(item["content"]))
        return result

    if not is_richtext_body(body):
        return frozenset()
    return frozenset(
        UUID(node["media_link_id"])
        for node in descendants(body["content"])
        if node["type"] == "image"
    )


def remap_richtext_media_links(body: object, link_id_map: dict[UUID, UUID]) -> dict:
    """Copy a version snapshot and remap only its internal media-link references."""

    copied = copy_body(body)
    if not is_richtext_body(copied):
        return copied

    def rewrite(nodes: list[dict]) -> None:
        for node in nodes:
            if node["type"] == "image":
                source_id = UUID(node["media_link_id"])
                if source_id in link_id_map:
                    node["media_link_id"] = str(link_id_map[source_id])
            elif node["type"] in {"blockquote", "callout"}:
                rewrite(node["content"])
            elif node["type"] in {"orderedList", "bulletList"}:
                for item in node["items"]:
                    rewrite(item["content"])

    rewrite(copied["content"])
    return copied


def build_body_content(
    *, body_text: str | None, structured_content: object | None = None
) -> tuple[dict, str]:
    """Choose exactly one authoritative body input and produce its text projection."""

    if structured_content is not None:
        return validate_richtext_body(structured_content)
    if body_text is None:
        raise ValueError("正文不能为空。")
    return build_plaintext_body(body_text)


def is_richtext_body(body: object) -> bool:
    return isinstance(body, dict) and body.get("format") == RICHTEXT_BODY_FORMAT


def copy_body(body: object) -> dict:
    """Return a defensive body copy for version fan-out services."""

    return deepcopy(body) if isinstance(body, dict) else {}
