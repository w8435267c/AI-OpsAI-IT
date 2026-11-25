"""Server-side structured content schema and compatibility contracts."""

from django.test import SimpleTestCase

from apps.knowledge.content import (
    PLAINTEXT_BODY_FORMAT,
    RICHTEXT_BODY_FORMAT,
    RichTextContentError,
    build_body_content,
    richtext_media_link_ids,
    richtext_to_plaintext,
    validate_richtext_body,
)


def _document():
    return {
        "format": RICHTEXT_BODY_FORMAT,
        "schema_version": 1,
        "content": [
            {
                "type": "heading",
                "level": 1,
                "content": [{"type": "text", "text": "网络处理", "marks": [{"type": "bold"}]}],
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "第一步：检查 VPN",
                        "marks": [{"type": "color", "color": "blue"}],
                    },
                    {"type": "hardBreak"},
                    {
                        "type": "text",
                        "text": "查看说明",
                        "marks": [{"type": "link", "href": "https://example.com/help"}],
                    },
                ],
            },
            {
                "type": "table",
                "rows": [
                    {
                        "cells": [
                            {"type": "tableHeader", "content": [{"type": "text", "text": "项目"}]}
                        ]
                    },
                    {
                        "cells": [
                            {"type": "tableCell", "content": [{"type": "text", "text": "VPN"}]}
                        ]
                    },
                ],
            },
            {
                "type": "image",
                "media_link_id": "11111111-1111-1111-1111-111111111111",
                "caption": "登录页面",
                "width": "wide",
            },
        ],
    }


class RichTextContentTests(SimpleTestCase):
    def test_valid_document_has_deterministic_plaintext_projection(self):
        body, plaintext = validate_richtext_body(_document())
        self.assertEqual(body["format"], RICHTEXT_BODY_FORMAT)
        self.assertEqual(plaintext, "网络处理\n第一步：检查 VPN\n查看说明\n项目\nVPN\n登录页面")
        self.assertEqual(richtext_to_plaintext(body), plaintext)
        self.assertEqual(
            {str(value) for value in richtext_media_link_ids(body)},
            {"11111111-1111-1111-1111-111111111111"},
        )

    def test_legacy_plaintext_remains_supported(self):
        body, plaintext = build_body_content(body_text="旧正文", structured_content=None)
        self.assertEqual(body, {"format": PLAINTEXT_BODY_FORMAT, "text": "旧正文"})
        self.assertEqual(plaintext, "旧正文")

    def test_html_script_external_image_and_unknown_nodes_are_rejected(self):
        cases = (
            {
                "format": RICHTEXT_BODY_FORMAT,
                "schema_version": 1,
                "content": [{"type": "html", "value": "<script>"}],
            },
            {
                "format": RICHTEXT_BODY_FORMAT,
                "schema_version": 1,
                "content": [
                    {
                        "type": "image",
                        "media_link_id": "https://example.com/a.png",
                        "caption": "",
                        "width": "full",
                    }
                ],
            },
            {
                "format": RICHTEXT_BODY_FORMAT,
                "schema_version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "x",
                                "marks": [{"type": "link", "href": "javascript:alert(1)"}],
                            }
                        ],
                    }
                ],
            },
        )
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(RichTextContentError):
                    validate_richtext_body(value)

    def test_unsupported_and_duplicate_marks_remain_rejected(self):
        for marks in (
            [{"type": "textStyle"}],
            [{"type": "bold"}, {"type": "bold"}],
        ):
            with self.subTest(marks=marks):
                document = _document()
                document["content"][1]["content"][0]["marks"] = marks
                with self.assertRaises(RichTextContentError):
                    validate_richtext_body(document)

    def test_table_cell_spans_are_normalised_and_invalid_spans_are_rejected(self):
        document = _document()
        document["content"][2]["rows"] = [
            {
                "cells": [
                    {
                        "type": "tableHeader",
                        "content": [{"type": "text", "text": "标题"}],
                        "colspan": 2,
                    }
                ]
            },
            {
                "cells": [
                    {"type": "tableCell", "content": [{"type": "text", "text": "左"}]},
                    {"type": "tableCell", "content": [{"type": "text", "text": "右"}]},
                ]
            },
        ]
        body, _ = validate_richtext_body(document)
        self.assertEqual(body["content"][2]["rows"][0]["cells"][0]["colspan"], 2)

        document["content"][2]["rows"][0]["cells"][0]["colspan"] = 0
        with self.assertRaises(RichTextContentError):
            validate_richtext_body(document)

    def test_tiptap_empty_structural_nodes_are_valid_when_document_has_readable_text(self):
        document = _document()
        document["content"].insert(1, {"type": "paragraph", "content": []})
        document["content"][3]["rows"][0]["cells"][0]["content"] = []

        body, plaintext = validate_richtext_body(document)

        self.assertEqual(body["content"][1], {"type": "paragraph", "content": []})
        self.assertEqual(body["content"][3]["rows"][0]["cells"][0]["content"], [])
        self.assertIn("VPN", plaintext)

    def test_document_with_only_empty_tiptap_structural_nodes_is_still_rejected(self):
        document = {
            "format": RICHTEXT_BODY_FORMAT,
            "schema_version": 1,
            "content": [{"type": "paragraph", "content": []}],
        }

        with self.assertRaises(RichTextContentError):
            validate_richtext_body(document)
