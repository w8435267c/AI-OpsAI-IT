"""纯合成版本/审核数据，不导入业务模型。"""

import json
import math
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from conversion import (
    BODY_FORMAT,
    FORMAT,
    ConversionError,
    convert_version,
    decode_body,
    encode_body,
    restore_version,
)


def fixture(published=True):
    instant = datetime(2024, 5, 6, 7, 8, 9, 123456, tzinfo=timezone(timedelta(hours=8)))
    version = dict(
        id=UUID(int=1 if published else 2),
        article_id=UUID(int=3),
        version_no=1 if published else 2,
        status="published" if published else "draft",
        title="正式标题" if published else "新草稿",
        summary="中文摘要\n第二行",
        applicable_scope={"系统": ["甲", "乙"], "适用": True, "空": None},
        body={
            "段落": ['中文\n引号"与反斜杠\\', {"数组": [None, True, False, 1, 1.0, -0.0, 10**40]}]
        },
        body_plaintext="派生文本",
        change_summary="保留版本说明",
        created_by_id=10,
        submitted_by_id=11 if published else None,
        submitted_at=instant if published else None,
        published_at=instant + timedelta(hours=2) if published else None,
        created_at=instant - timedelta(days=1),
        updated_at=instant + timedelta(hours=1),
    )
    reviews = (
        [
            dict(
                id=UUID(int=4),
                article_version_id=version["id"],
                review_type="content_review",
                reviewer_id=12,
                decision="approved",
                comment="原审核意见\n保留",
                reviewed_at=instant + timedelta(hours=1),
            )
        ]
        if published
        else []
    )
    return version, reviews


class ConversionTests(unittest.TestCase):
    def same_types(self, actual, expected):
        self.assertIs(type(actual), type(expected))
        self.assertEqual(actual, expected)
        if type(expected) is dict:
            for key in expected:
                self.same_types(actual[key], expected[key])
        elif type(expected) is list:
            for a, e in zip(actual, expected, strict=True):
                self.same_types(a, e)
        elif type(expected) is float and expected == 0:
            self.assertEqual(math.copysign(1, actual), math.copysign(1, expected))
        elif type(expected) is datetime:
            self.assertEqual(actual.isoformat(), expected.isoformat())
            self.assertEqual(actual.fold, expected.fold)
            self.assertIs(type(actual.tzinfo), type(expected.tzinfo))

    def test_published_and_newer_draft_roundtrip(self):
        for published in (True, False):
            with self.subTest(published=published):
                version, reviews = fixture(published)
                converted = convert_version(version, reviews)
                self.same_types(restore_version(converted), (version, reviews))
                restored, records = restore_version(converted)
                self.same_types(restored, version)
                self.same_types(records, reviews)
                self.assertEqual(converted["format"], FORMAT)
                self.assertEqual(set(converted["content"]), {"title", "summary", "body"})
                self.assertEqual(set(converted), {"format", "content", "source"})

    def test_json_values_keep_exact_python_types(self):
        for value in ({}, [], [None, True, 1, 1.0], None, "", 0, False, -0.0, 1e-250):
            with self.subTest(value=value):
                version, reviews = fixture(False)
                version.update(body=value, applicable_scope=value, body_plaintext="")
                restored, _ = restore_version(convert_version(version, reviews))
                self.same_types(restored, version)

    def test_source_identity_times_and_reviews_are_not_new_approval(self):
        version, reviews = fixture()
        version["created_at"] = version["created_at"].replace(fold=1)
        result = convert_version(version, reviews)
        source = result["source"]
        for field in (
            "id",
            "status",
            "applicable_scope",
            "change_summary",
            "created_by_id",
            "created_at",
            "updated_at",
            "submitted_by_id",
            "submitted_at",
            "published_at",
            "body_plaintext",
        ):
            self.same_types(source["version"][field], version[field])
        self.same_types(source["reviews"], reviews)
        self.assertNotIn("imported_by", source)
        self.assertNotIn("live", result["content"])
        self.assertNotIn("task_state", source)

    def test_deterministic_and_no_mutable_aliases(self):
        version, reviews = fixture()
        before = deepcopy((version, reviews))
        a = convert_version(version, reviews)
        b = convert_version(version, reviews)
        self.assertEqual(a, b)
        self.assertEqual(encode_body({"乙": 1, "甲": 2}), encode_body({"甲": 2, "乙": 1}))
        restored, records = restore_version(a)
        restored["applicable_scope"]["系统"].append("变化")
        records[0]["comment"] = "变化"
        self.assertEqual(a, b)
        a["source"]["version"]["applicable_scope"]["系统"].append("变化")
        a["source"]["reviews"][0]["comment"] = "变化"
        self.assertEqual((version, reviews), before)

    def test_missing_and_unknown_fields_fail(self):
        version, reviews = fixture()
        for field in version:
            invalid = deepcopy(version)
            del invalid[field]
            with self.subTest(field=field), self.assertRaises(ConversionError):
                convert_version(invalid, reviews)
        with self.assertRaises(ConversionError):
            convert_version({**version, "future_field": 1}, reviews)
        invalid = deepcopy(reviews)
        del invalid[0]["reviewer_id"]
        with self.assertRaises(ConversionError):
            convert_version(version, invalid)

    def test_unsupported_json_types_fail_without_coercion(self):
        bad = [
            {1: "numeric key"},
            (1, 2),
            {1, 2},
            Decimal("1.1"),
            UUID(int=1),
            b"bytes",
            float("nan"),
            float("inf"),
            "\ud800",
        ]
        cycle = []
        cycle.append(cycle)
        bad.append(cycle)
        for value in bad:
            with self.subTest(type=type(value)), self.assertRaises(ConversionError):
                encode_body(value)

    def test_bad_identity_dates_and_state_fail(self):
        version, reviews = fixture()
        for key, value in (
            ("id", str(version["id"])),
            ("created_by_id", True),
            ("version_no", False),
            ("status", "unknown"),
            ("submitted_by_id", None),
            ("published_at", None),
            ("created_at", datetime(2020, 1, 1)),
            ("summary", None),
            ("title", "长" * 61),
        ):
            with self.subTest(key=key), self.assertRaises(ConversionError):
                convert_version({**version, key: value}, reviews)
        for key, value in (
            ("article_version_id", UUID(int=99)),
            ("decision", "unknown"),
            ("reviewed_at", None),
        ):
            with self.subTest(key=key), self.assertRaises(ConversionError):
                convert_version(version, [{**reviews[0], key: value}])

    def test_broken_or_unknown_body_encoding_fails(self):
        good = json.loads(encode_body({"text": "正文"}))
        for value in (
            "{",
            "[]",
            '{"format":1,"format":2}',
            json.dumps({**good, "format": "unknown"}),
            json.dumps({**good, "payload": {"text": "损坏"}}),
            json.dumps({**good, "sha256": "bad"}),
            json.dumps({**good, "extra": True}),
        ):
            with self.subTest(value=value), self.assertRaises(ConversionError):
                decode_body(value)
        self.assertEqual(good["format"], BODY_FORMAT)

    def test_conversion_envelope_damage_fails(self):
        result = convert_version(*fixture())
        for key in result:
            broken = deepcopy(result)
            del broken[key]
            with self.assertRaises(ConversionError):
                restore_version(broken)
        with self.assertRaises(ConversionError):
            restore_version({**result, "format": "opsai.legacy-version/2"})
        broken = deepcopy(result)
        broken["source"]["version"]["body"] = "must not override encoded body"
        with self.assertRaises(ConversionError):
            restore_version(broken)


if __name__ == "__main__":
    unittest.main()
