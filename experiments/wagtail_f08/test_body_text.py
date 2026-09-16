"""只使用 F07 编码函数生成合成输入，不导入 Django 或数据库。"""

import json
import unittest
from dataclasses import asdict
from unittest.mock import patch

from experiments.wagtail_f07.conversion import encode_body

from . import body_text
from .body_text import convert_encoded_body_to_plaintext


class PlaintextTests(unittest.TestCase):
    def assert_success(self, text):
        result = convert_encoded_body_to_plaintext(encode_body(text))
        self.assertTrue(result.success)
        self.assertEqual(result.code, "ok")
        self.assertIs(type(result.text), str)
        self.assertEqual(result.text, text)
        self.assertEqual(set(asdict(result)), {"success", "text", "code", "reason"})

    def test_chinese_multiline_is_exact(self):
        self.assert_success(
            '网络访问\n\n1. 检查连接。\n2. 提交申请。\n- 引号"与反斜杠\\'.replace("\\n", "\n")
        )

    def test_empty_and_whitespace_are_preserved(self):
        for text in ("", " \t前后空白\r\n ", "\n\n", "\x00原样字符\x01"):
            with self.subTest(text=text):
                self.assert_success(text)

    def test_json_html_and_script_are_literal_text(self):
        for text in (
            '{"text":"不是另一个节点"}',
            encode_body("内层编码也只是文本"),
            '<script>alert("合成")</script><b>标签</b>',
        ):
            with self.subTest(text=text):
                self.assert_success(text)

    def test_nonstring_payloads_are_rejected_without_text(self):
        for payload, code in (
            ({"text": "不能提取此正文"}, "unsupported_mapping"),
            (["不能拼接此正文"], "unsupported_sequence"),
            (1, "unsupported_number"),
            (1.0, "unsupported_number"),
            (True, "unsupported_boolean"),
            (False, "unsupported_boolean"),
            (None, "unsupported_null"),
        ):
            with self.subTest(payload=payload):
                result = convert_encoded_body_to_plaintext(encode_body(payload))
                self.assertFalse(result.success)
                self.assertIsNone(result.text)
                self.assertEqual(result.code, code)
                self.assertEqual(result.reason, "不支持自动转换，需要人工确认")

    def test_invalid_envelopes_fail_without_partial_text(self):
        envelope = json.loads(encode_body("不应在失败中返回的合成正文"))
        damaged = (
            "{",
            "普通正文",
            None,
            1,
            {},
            json.dumps({**envelope, "sha256": "bad"}),
            json.dumps({**envelope, "payload": "被修改的正文"}),
            json.dumps({**envelope, "format": "unknown"}),
            json.dumps({**envelope, "extra": True}),
            json.dumps({k: v for k, v in envelope.items() if k != "payload"}),
            '{"format":1,"format":2}',
        )
        for encoded in damaged:
            with self.subTest(encoded=encoded):
                result = convert_encoded_body_to_plaintext(encoded)
                self.assertFalse(result.success)
                self.assertIsNone(result.text)
                self.assertEqual(result.code, "invalid_encoded_body")
                self.assertEqual(result.reason, "迁移正文封套、格式版本或摘要校验失败")
                self.assertNotIn(envelope["payload"], repr(result))

    def test_repeat_is_deterministic_and_input_unchanged(self):
        for payload in ("合成正文", {"unknown": "保留输入"}):
            encoded = encode_body(payload)
            before = encoded[:]
            first = convert_encoded_body_to_plaintext(encoded)
            self.assertEqual(convert_encoded_body_to_plaintext(encoded), first)
            self.assertEqual(encoded, before)

    def test_delegates_validation_to_f07(self):
        encoded = encode_body("真实解码")
        with patch.object(body_text, "decode_body", wraps=body_text.decode_body) as decoder:
            self.assertEqual(convert_encoded_body_to_plaintext(encoded).text, "真实解码")
        decoder.assert_called_once_with(encoded)

    def test_unexpected_error_is_not_hidden(self):
        with patch.object(body_text, "decode_body", side_effect=RuntimeError("程序错误")):
            with self.assertRaisesRegex(RuntimeError, "程序错误"):
                convert_encoded_body_to_plaintext(encode_body("输入"))
