from pathlib import Path

from django.test import SimpleTestCase


class RichTextDisplayStyleContractTests(SimpleTestCase):
    def test_all_richtext_read_views_use_the_shared_display_container(self):
        root = Path(__file__).resolve().parents[3]
        templates = (
            root / "templates/knowledge/article_detail.html",
            root / "templates/knowledge/manage/preview.html",
            root / "templates/knowledge/manage/history_detail.html",
            root / "templates/workflow/review_detail.html",
        )
        for template in templates:
            self.assertIn("richtext-body", template.read_text(encoding="utf-8"))

    def test_shared_table_styles_keep_mobile_scrolling_local(self):
        root = Path(__file__).resolve().parents[3]
        css = (root / "static/css/opsai.css").read_text(encoding="utf-8")
        self.assertIn(".richtext-body .rich-table-scroll", css)
        self.assertIn("overflow-x: auto", css)
        self.assertIn(".richtext-body .rich-table-scroll th", css)
        self.assertIn("overflow-wrap: anywhere", css)
