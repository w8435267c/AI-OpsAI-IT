"""Small, safe converters from parsed text into the knowledge rich-text schema."""

from __future__ import annotations

import re

from apps.knowledge.content import RICHTEXT_BODY_FORMAT

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_IMAGE = re.compile(r"!\[[^]]*]\([^)]*\)")
_LINK = re.compile(r"\[([^]]+)]\((https?://[^\s)]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_UNDERLINE = re.compile(r"__([^_]+)__")


def _text(value: str, marks: list[dict] | None = None) -> dict:
    return {"type": "text", "text": value, "marks": marks or []}


def _inline(value: str) -> list[dict]:
    """Conservatively recognise safe Markdown inline markup without HTML."""

    tokens: list[dict] = []
    pattern = re.compile(rf"{_LINK.pattern}|{_BOLD.pattern}|{_UNDERLINE.pattern}|{_ITALIC.pattern}")
    cursor = 0
    for match in pattern.finditer(value):
        if match.start() > cursor:
            tokens.append(_text(value[cursor : match.start()]))
        if match.group(1) is not None:
            tokens.append(_text(match.group(1), [{"type": "link", "href": match.group(2)}]))
        elif match.group(3) is not None:
            tokens.append(_text(match.group(3), [{"type": "bold"}]))
        elif match.group(4) is not None:
            tokens.append(_text(match.group(4), [{"type": "underline"}]))
        else:
            tokens.append(_text(match.group(5), [{"type": "italic"}]))
        cursor = match.end()
    if cursor < len(value):
        tokens.append(_text(value[cursor:]))
    return tokens or [_text("")]


def plaintext_content(body_text: str) -> list[dict]:
    """Preserve paragraph boundaries and intentional line breaks without inventing formatting."""

    blocks: list[dict] = []
    for paragraph in re.split(r"\n\s*\n", body_text.strip()):
        lines = paragraph.splitlines()
        inline: list[dict] = []
        for index, line in enumerate(lines):
            if index:
                inline.append({"type": "hardBreak"})
            inline.extend(_inline(line))
        blocks.append({"type": "paragraph", "content": inline or [_text("")]})
    return blocks


def _table_row(line: str, *, header: bool) -> dict:
    values = [item.strip() for item in line.strip().strip("|").split("|")]
    return {
        "cells": [
            {"type": "tableHeader" if header else "tableCell", "content": _inline(value)}
            for value in values
        ]
    }


def markdown_content(source: str) -> tuple[list[dict], tuple[str, ...]]:
    """Convert the supported Markdown subset; never emit raw HTML or resources."""

    warnings: list[str] = []
    text = _IMAGE.sub("", source)
    if text != source:
        warnings.append("Markdown 图片引用未导入，请在草稿中手动添加受控图片。")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[dict] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("```"):
            language = line[3:].strip()[:32]
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index == len(lines):
                warnings.append("Markdown 代码块未闭合，按代码文本导入。")
            else:
                index += 1
            blocks.append(
                {"type": "codeBlock", "language": language, "text": "\n".join(code_lines)}
            )
            continue
        if match := _HEADING.match(line):
            blocks.append(
                {
                    "type": "heading",
                    "level": len(match.group(1)),
                    "content": _inline(match.group(2)),
                }
            )
            index += 1
            continue
        if index + 1 < len(lines) and "|" in line and _TABLE_SEPARATOR.match(lines[index + 1]):
            rows = [_table_row(line, header=True)]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(_table_row(lines[index], header=False))
                index += 1
            widths = {len(row["cells"]) for row in rows}
            if len(widths) == 1:
                blocks.append({"type": "table", "rows": rows})
            else:
                warnings.append("Markdown 表格列数不一致，按普通文本导入。")
                blocks.extend(plaintext_content("\n".join(lines[index - len(rows) - 1 : index])))
            continue
        if match := _QUOTE.match(line):
            quote_lines: list[str] = []
            while index < len(lines) and (item := _QUOTE.match(lines[index])):
                quote_lines.append(item.group(1))
                index += 1
            blocks.append(
                {"type": "blockquote", "content": plaintext_content("\n".join(quote_lines))}
            )
            continue
        ordered = _ORDERED.match(line)
        bullet = _BULLET.match(line)
        if ordered or bullet:
            expression = _ORDERED if ordered else _BULLET
            list_type = "orderedList" if ordered else "bulletList"
            items = []
            while index < len(lines) and (item := expression.match(lines[index])):
                items.append(
                    {"content": [{"type": "paragraph", "content": _inline(item.group(1))}]}
                )
                index += 1
            blocks.append({"type": list_type, "items": items})
            continue
        paragraph_lines = [line]
        index += 1
        while index < len(lines) and lines[index].strip():
            if (
                lines[index].startswith("```")
                or _HEADING.match(lines[index])
                or _QUOTE.match(lines[index])
                or _ORDERED.match(lines[index])
                or _BULLET.match(lines[index])
            ):
                break
            paragraph_lines.append(lines[index])
            index += 1
        inline: list[dict] = []
        for position, paragraph_line in enumerate(paragraph_lines):
            if position:
                inline.append({"type": "hardBreak"})
            inline.extend(_inline(paragraph_line))
        blocks.append({"type": "paragraph", "content": inline})
    return blocks, tuple(warnings)


def richtext_document(*, content: list[dict]) -> dict:
    return {"format": RICHTEXT_BODY_FORMAT, "schema_version": 1, "content": content}
