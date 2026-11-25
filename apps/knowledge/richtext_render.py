"""Safe, shared HTML rendering for validated knowledge rich-text snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from django.utils.html import conditional_escape, format_html, format_html_join
from django.utils.safestring import SafeString, mark_safe

from apps.knowledge.content import is_richtext_body, validate_richtext_body


class RichTextRenderError(ValueError):
    """A validated snapshot could not be rendered with its authorised media map."""


def render_richtext_html(*, body: object, media_urls: Mapping[UUID, str]) -> SafeString | None:
    """Render only schema-validated nodes and only caller-authorised private media URLs.

    ``None`` intentionally means a legacy plaintext body.  No user-supplied HTML is
    ever marked safe: every tag below is generated from a closed node allow-list.
    """

    if not is_richtext_body(body):
        return None
    normalised, _plaintext = validate_richtext_body(body)

    def inline(nodes: list[dict]) -> SafeString:
        parts: list[str] = []
        for node in nodes:
            if node["type"] == "hardBreak":
                parts.append("<br>")
                continue
            rendered = conditional_escape(node["text"])
            for mark in node["marks"]:
                if mark["type"] == "bold":
                    rendered = format_html("<strong>{}</strong>", rendered)
                elif mark["type"] == "italic":
                    rendered = format_html("<em>{}</em>", rendered)
                elif mark["type"] == "underline":
                    rendered = format_html("<u>{}</u>", rendered)
                elif mark["type"] == "color":
                    rendered = format_html(
                        '<span class="rich-color-{}">{}</span>', mark["color"], rendered
                    )
                elif mark["type"] == "link":
                    rendered = format_html(
                        '<a href="{}" rel="noopener noreferrer" target="_blank">{}</a>',
                        mark["href"],
                        rendered,
                    )
            parts.append(str(rendered))
        return mark_safe("".join(parts))

    def block(node: dict) -> SafeString:
        node_type = node["type"]
        if node_type == "heading":
            return format_html(
                "<h{}>{}</h{}>", node["level"], inline(node["content"]), node["level"]
            )
        if node_type == "paragraph":
            return format_html("<p>{}</p>", inline(node["content"]))
        if node_type in {"orderedList", "bulletList"}:
            tag = "ol" if node_type == "orderedList" else "ul"
            items = format_html_join(
                "", "<li>{}</li>", ((blocks(item["content"]),) for item in node["items"])
            )
            return format_html("<{}>{}</{}>", tag, items, tag)
        if node_type == "codeBlock":
            return format_html(
                '<pre><code data-language="{}">{}</code></pre>', node["language"], node["text"]
            )
        if node_type == "blockquote":
            return format_html("<blockquote>{}</blockquote>", blocks(node["content"]))
        if node_type == "table":
            rows = []
            for row in node["rows"]:
                cells = []
                for cell in row["cells"]:
                    tag = "th" if cell["type"] == "tableHeader" else "td"
                    attrs = {}
                    if cell.get("colspan", 1) != 1:
                        attrs["colspan"] = cell["colspan"]
                    if cell.get("rowspan", 1) != 1:
                        attrs["rowspan"] = cell["rowspan"]
                    cells.append(
                        str(
                            format_html(
                                "<{}{}>{}</{}>",
                                tag,
                                mark_safe(
                                    "".join(f' {name}="{value}"' for name, value in attrs.items())
                                ),
                                inline(cell["content"]),
                                tag,
                            )
                        )
                    )
                rows.append(format_html("<tr>{}</tr>", mark_safe("".join(cells))))
            return format_html(
                '<div class="rich-table-scroll"><table>{}</table></div>',
                mark_safe("".join(map(str, rows))),
            )
        if node_type == "image":
            media_id = UUID(node["media_link_id"])
            url = media_urls.get(media_id)
            if not url:
                raise RichTextRenderError("图片不属于当前可读取的版本媒体。")
            caption = (
                format_html("<figcaption>{}</figcaption>", node["caption"])
                if node["caption"]
                else ""
            )
            return format_html(
                '<figure class="article-image rich-image--{}">'
                '<a href="{}" target="_blank" rel="noopener">'
                '<img src="{}" alt="{}" loading="lazy"></a>{}</figure>',
                node["width"],
                url,
                url,
                node["caption"] or "知识步骤截图",
                mark_safe(str(caption)),
            )
        if node_type == "callout":
            return format_html(
                '<aside class="rich-callout rich-callout--{}">{}</aside>',
                node["kind"],
                blocks(node["content"]),
            )
        raise RichTextRenderError("正文包含无法渲染的节点。")

    def blocks(nodes: list[dict]) -> SafeString:
        return mark_safe("".join(str(block(node)) for node in nodes))

    return blocks(normalised["content"])
