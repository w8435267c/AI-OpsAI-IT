"""Structured-content write contracts for the existing ArticleVersion workflow."""

from datetime import timedelta

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import ROLE_EDITOR, SYSTEM_ROLE_BY_CODE
from apps.knowledge.content import RICHTEXT_BODY_FORMAT
from apps.knowledge.models import (
    ArticleType,
    ArticleVersionMedia,
    AudiencePolicy,
    Category,
    KnowledgeSpace,
    MediaAsset,
    MediaKind,
    MediaScanStatus,
)
from apps.knowledge.services import (
    ARTICLE_VERSION_WRITE_INVALID_INPUT,
    ArticleVersionWriteError,
    autosave_draft,
    create_article,
    manual_save_draft,
)


def _richtext(text: str) -> dict:
    return {
        "format": RICHTEXT_BODY_FORMAT,
        "schema_version": 1,
        "content": [
            {"type": "heading", "level": 1, "content": [{"type": "text", "text": "标题"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": text}]},
        ],
    }


def _richtext_with_image(*, media_link_id: str) -> dict:
    body = _richtext("请核对下图。")
    body["content"].append(
        {
            "type": "image",
            "media_link_id": media_link_id,
            "caption": "登录界面",
            "width": "wide",
        }
    )
    return body


class StructuredContentWriteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0)
        cls.editor = User.objects.create_user(username="richtext-editor")
        cls.editor.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name))
        cls.space = KnowledgeSpace.objects.create(
            code="richtext-space",
            name="富文本测试空间",
            space_type="employee",
            owner=cls.editor,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="richtext-category",
            name="富文本测试分类",
        )

    def create_kwargs(self, **overrides):
        values = {
            "actor": self.editor,
            "space": self.space,
            "category": self.category,
            "article_type": ArticleType.GUIDE,
            "title": "结构化正文",
            "summary": "验证统一正文服务",
            "applicable_scope": {},
            "body_text": "不应成为富文本的权威来源",
            "structured_content": _richtext("第一步：检查网络。"),
            "change_summary": "创建富文本草稿",
            "review_due_at": timezone.now() + timedelta(days=180),
        }
        values.update(overrides)
        return values

    def test_create_derives_plaintext_from_validated_structured_content(self):
        _article, draft = create_article(**self.create_kwargs())

        self.assertEqual(draft.body["format"], RICHTEXT_BODY_FORMAT)
        self.assertEqual(draft.body_plaintext, "标题\n第一步：检查网络。")
        self.assertNotIn("不应成为", draft.body_plaintext)

    def test_autosave_preserves_richtext_snapshot_and_updates_plaintext_projection(self):
        article, draft = create_article(**self.create_kwargs())
        updated = autosave_draft(
            actor=self.editor,
            article=article,
            draft_id=draft.pk,
            expected_lock_version=draft.lock_version,
            title=draft.title,
            summary=draft.summary,
            applicable_scope=draft.applicable_scope,
            body_text="客户端传来的旧纯文本",
            structured_content=_richtext("第二步：重新连接。"),
            change_summary="更新结构化正文",
        )

        self.assertEqual(updated.body["format"], RICHTEXT_BODY_FORMAT)
        self.assertEqual(updated.body_plaintext, "标题\n第二步：重新连接。")

    def test_invalid_structured_content_is_rejected_without_mutating_the_draft(self):
        article, draft = create_article(**self.create_kwargs())
        invalid = _richtext("不应写入")
        invalid["content"][1]["content"][0]["marks"] = [
            {"type": "link", "href": "javascript:alert(1)"}
        ]

        with self.assertRaises(ArticleVersionWriteError) as caught:
            autosave_draft(
                actor=self.editor,
                article=article,
                draft_id=draft.pk,
                expected_lock_version=draft.lock_version,
                title=draft.title,
                summary=draft.summary,
                applicable_scope=draft.applicable_scope,
                body_text="不应写入",
                structured_content=invalid,
                change_summary="无效结构化正文",
            )

        self.assertEqual(caught.exception.code, ARTICLE_VERSION_WRITE_INVALID_INPUT)
        draft.refresh_from_db()
        self.assertEqual(draft.lock_version, 1)
        self.assertEqual(draft.body_plaintext, "标题\n第一步：检查网络。")

    def test_autosave_accepts_only_clean_image_links_owned_by_the_current_draft(self):
        article, draft = create_article(**self.create_kwargs())
        asset = MediaAsset.objects.create(
            kind=MediaKind.IMAGE,
            original_name="screen.png",
            storage_name="tests/structured-content-screen.bin",
            content_type="image/png",
            size_bytes=1,
            sha256="0" * 64,
            scan_status=MediaScanStatus.CLEAN,
            created_by=self.editor,
        )
        link = ArticleVersionMedia.objects.create(
            article_version=draft,
            asset=asset,
            body_position=0,
        )

        updated = autosave_draft(
            actor=self.editor,
            article=article,
            draft_id=draft.pk,
            expected_lock_version=draft.lock_version,
            title=draft.title,
            summary=draft.summary,
            applicable_scope=draft.applicable_scope,
            body_text="不应成为权威来源",
            structured_content=_richtext_with_image(media_link_id=str(link.pk)),
            change_summary="引用受控图片",
        )

        self.assertEqual(updated.body["content"][-1]["media_link_id"], str(link.pk))

        with self.assertRaises(ArticleVersionWriteError) as caught:
            autosave_draft(
                actor=self.editor,
                article=article,
                draft_id=updated.pk,
                expected_lock_version=updated.lock_version,
                title=updated.title,
                summary=updated.summary,
                applicable_scope=updated.applicable_scope,
                body_text="不应成为权威来源",
                structured_content=_richtext_with_image(
                    media_link_id="22222222-2222-2222-2222-222222222222"
                ),
                change_summary="越权图片引用",
            )
        self.assertEqual(caught.exception.code, ARTICLE_VERSION_WRITE_INVALID_INPUT)

    def test_manual_save_remaps_richtext_images_to_the_new_draft_links(self):
        article, draft = create_article(**self.create_kwargs())
        asset = MediaAsset.objects.create(
            kind=MediaKind.IMAGE,
            original_name="next-version.png",
            storage_name="tests/next-version.bin",
            content_type="image/png",
            size_bytes=1,
            sha256="1" * 64,
            scan_status=MediaScanStatus.CLEAN,
            created_by=self.editor,
        )
        original_link = ArticleVersionMedia.objects.create(
            article_version=draft,
            asset=asset,
            body_position=0,
        )
        current = autosave_draft(
            actor=self.editor,
            article=article,
            draft_id=draft.pk,
            expected_lock_version=draft.lock_version,
            title=draft.title,
            summary=draft.summary,
            applicable_scope=draft.applicable_scope,
            body_text="不应成为权威来源",
            structured_content=_richtext_with_image(media_link_id=str(original_link.pk)),
            change_summary="加入图片",
        )

        saved, next_draft = manual_save_draft(
            actor=self.editor,
            article=article,
            draft_id=current.pk,
            expected_lock_version=current.lock_version,
            title=current.title,
            summary=current.summary,
            applicable_scope=current.applicable_scope,
            body_text=current.body_plaintext,
            structured_content=current.body,
            change_summary="保存富文本版本",
        )

        next_link = ArticleVersionMedia.objects.get(article_version=next_draft)
        self.assertEqual(saved.body["content"][-1]["media_link_id"], str(original_link.pk))
        self.assertEqual(next_draft.body["content"][-1]["media_link_id"], str(next_link.pk))
        self.assertNotEqual(next_link.pk, original_link.pk)
