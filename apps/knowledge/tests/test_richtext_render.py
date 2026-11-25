"""Shared rich-text rendering must stay closed to untrusted HTML and media URLs."""

from django.test import SimpleTestCase
from django.utils.safestring import SafeString

from apps.knowledge.content import RICHTEXT_BODY_FORMAT
from apps.knowledge.richtext_render import RichTextRenderError, render_richtext_html

MEDIA_ID = "11111111-1111-1111-1111-111111111111"


class RichTextRenderTests(SimpleTestCase):
    def body(self):
        return {
            "format": RICHTEXT_BODY_FORMAT,
            "schema_version": 1,
            "content": [
                {"type": "heading", "level": 2, "content": [{"type": "text", "text": "标题"}]},
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "<script>", "marks": [{"type": "bold"}]}],
                },
                {"type": "image", "media_link_id": MEDIA_ID, "caption": "截图", "width": "wide"},
            ],
        }

    def test_renders_only_closed_schema_html_and_authorised_media(self):
        rendered = render_richtext_html(
            body=self.body(), media_urls={__import__("uuid").UUID(MEDIA_ID): "/private/image/"}
        )
        self.assertIsInstance(rendered, SafeString)
        self.assertIn("<h2>标题</h2>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn('src="/private/image/"', rendered)
        self.assertIn("rich-image--wide", rendered)

    def test_rich_image_without_authorised_url_fails_closed(self):
        with self.assertRaises(RichTextRenderError):
            render_richtext_html(body=self.body(), media_urls={})

    def test_plaintext_body_is_left_to_legacy_template_path(self):
        self.assertIsNone(
            render_richtext_html(body={"format": "opsai.plaintext/1", "text": "old"}, media_urls={})
        )

    def test_renders_server_validated_table_spans_only(self):
        body = self.body()
        body["content"].insert(
            1,
            {
                "type": "table",
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "tableHeader",
                                "content": [{"type": "text", "text": "标题"}],
                                "colspan": 2,
                            }
                        ]
                    }
                ],
            },
        )
        rendered = render_richtext_html(
            body=body, media_urls={__import__("uuid").UUID(MEDIA_ID): "/private/image/"}
        )
        self.assertIn('<th colspan="2">标题</th>', rendered)
