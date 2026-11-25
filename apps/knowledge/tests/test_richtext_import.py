"""Conversion contracts for non-DOCX rich-text imports."""

from django.test import SimpleTestCase

from apps.knowledge.content import validate_richtext_body
from apps.knowledge.richtext_import import markdown_content, plaintext_content, richtext_document


class RichTextImportTests(SimpleTestCase):
    def test_plaintext_preserves_paragraph_and_line_boundaries(self):
        body, text = validate_richtext_body(
            richtext_document(content=plaintext_content("第一段\n第二行\n\n第三段"))
        )

        self.assertEqual(text, "第一段\n第二行\n第三段")
        self.assertEqual([node["type"] for node in body["content"]], ["paragraph", "paragraph"])

    def test_markdown_uses_supported_nodes_and_never_emits_html(self):
        markdown = (
            "# 标题\n\n1. 第一步\n2. 第二步\n\n> 注意\n\n"
            "```powershell\nGet-Date\n```\n\n| 名称 | 值 |\n| --- | --- |\n| A | B |"
        )
        content, warnings = markdown_content(markdown)
        body, text = validate_richtext_body(richtext_document(content=content))

        self.assertEqual(warnings, ())
        self.assertEqual(
            [node["type"] for node in body["content"]],
            ["heading", "orderedList", "blockquote", "codeBlock", "table"],
        )
        self.assertIn("Get-Date", text)

    def test_markdown_image_becomes_warning_not_external_request(self):
        content, warnings = markdown_content("说明\n\n![外部图片](https://example.com/image.png)")
        body, _text = validate_richtext_body(richtext_document(content=content))

        self.assertEqual(body["content"][0]["type"], "paragraph")
        self.assertEqual(len(warnings), 1)
