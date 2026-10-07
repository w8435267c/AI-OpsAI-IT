"""Task 12 正式文章正文的最小编码边界。"""

from __future__ import annotations

PLAINTEXT_BODY_FORMAT = "opsai.plaintext/1"


def build_plaintext_body(body_text: str) -> tuple[dict[str, str], str]:
    """从唯一的纯文本输入同时生成权威正文与派生纯文本。"""
    if not isinstance(body_text, str):
        raise ValueError("正文必须是字符串。")
    if not body_text.strip():
        raise ValueError("正文不能为空。")
    return {"format": PLAINTEXT_BODY_FORMAT, "text": body_text}, body_text
