"""旧版本纯数据转换；无 Django/Wagtail 依赖，不产生发布或审核证据。"""

import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

FORMAT = "opsai.legacy-version/1"
BODY_FORMAT = "opsai.legacy-body/1"
VERSION_FIELDS = frozenset(
    "id article_id version_no status title summary applicable_scope body "
    "body_plaintext change_summary created_by_id submitted_by_id submitted_at published_at "
    "created_at updated_at".split()
)
REVIEW_FIELDS = frozenset(
    "id article_version_id review_type reviewer_id decision comment reviewed_at".split()
)
CONTENT_FIELDS = frozenset(("title", "summary", "body"))


class ConversionError(ValueError):
    """输入字段、数据类型或编码不符合本格式；错误不包含正文值。"""


def _require(ok, message):
    if not ok:
        raise ConversionError(message)


def _keys(value, expected, name):
    _require(type(value) is dict and set(value) == set(expected), name + "字段缺失或包含未知字段")


def _json_value(value):
    if value is None or type(value) in (bool, int):
        return
    if type(value) is str:
        _require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), "不支持孤立代理字符")
        return
    if type(value) is float:
        _require(math.isfinite(value), "不支持非有限浮点数")
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str, "JSON 对象键必须是字符串")
            _json_value(key)
            _json_value(item)
        return
    raise ConversionError("不支持的 JSON 数据类型")


def _dump(value):
    try:
        _json_value(value)
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (RecursionError, ValueError) as exc:
        raise ConversionError("JSON 数据无法无损编码（类型、数值或循环/深度异常）") from exc


def _digest(payload):
    return hashlib.sha256(_dump(payload).encode("utf-8")).hexdigest()


def encode_body(body):
    """编码 JSON 值；摘要用于检测意外损坏，不是可信签名或批准凭证。"""
    return _dump({"format": BODY_FORMAT, "payload": body, "sha256": _digest(body)})


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, "编码含重复 JSON 键")
        result[key] = value
    return result


def decode_body(encoded):
    _require(type(encoded) is str, "正文编码必须是字符串")
    try:
        envelope = json.loads(encoded, object_pairs_hook=_pairs)
    except (ValueError, RecursionError) as exc:
        raise ConversionError("正文编码损坏") from exc
    _keys(envelope, ("format", "payload", "sha256"), "正文编码")
    _require(envelope["format"] == BODY_FORMAT, "未知正文格式版本")
    _require(envelope["sha256"] == _digest(envelope["payload"]), "正文编码完整性不一致")
    return envelope["payload"]


def _time(value, nullable=False):
    if value is None and nullable:
        return
    _require(type(value) is datetime, "时间必须是 datetime，不接受猜测解析")
    _require(isinstance(value.tzinfo, (timezone, ZoneInfo)), "时间须带标准库时区")


def _id(value, nullable=False):
    _require(
        (nullable and value is None) or (type(value) is int and value > 0), "账号 ID 必须是正整数"
    )


def _text(value, limit=None):
    _require(type(value) is str, "文本字段必须是字符串")
    _require(limit is None or len(value) <= limit, "文本字段超过旧模型长度")
    _json_value(value)


def _validate(version, reviews):
    _keys(version, VERSION_FIELDS, "旧版本")
    _require(
        type(version["id"]) is UUID and type(version["article_id"]) is UUID,
        "版本/文章 ID 必须是 UUID",
    )
    _require(type(version["version_no"]) is int and version["version_no"] > 0, "版本号必须是正整数")
    _require(
        type(version["status"]) is str
        and version["status"] in {"draft", "in_review", "rejected", "published", "superseded"},
        "未知旧版本状态",
    )
    for field, limit in (
        ("title", 60),
        ("summary", 500),
        ("change_summary", 500),
        ("body_plaintext", None),
    ):
        _text(version[field], limit)
    _dump(version["applicable_scope"])
    _dump(version["body"])
    _id(version["created_by_id"])
    _id(version["submitted_by_id"], nullable=True)
    for field in ("created_at", "updated_at"):
        _time(version[field])
    for field in ("submitted_at", "published_at"):
        _time(version[field], nullable=True)
    if version["status"] != "draft":
        _require(
            version["submitted_by_id"] is not None and version["submitted_at"] is not None,
            "非草稿缺少提交身份或时间",
        )
    if version["status"] == "published":
        _require(version["published_at"] is not None, "旧正式版本缺少发布时间")
    _require(type(reviews) is list, "审核来源必须显式提供列表")
    ids = set()
    for review in reviews:
        _keys(review, REVIEW_FIELDS, "审核来源")
        _require(type(review["id"]) is UUID and review["id"] not in ids, "审核 ID 缺失或重复")
        ids.add(review["id"])
        _require(
            type(review["article_version_id"]) is UUID
            and review["article_version_id"] == version["id"],
            "审核来源不属于旧版本",
        )
        _require(
            type(review["review_type"]) is str
            and review["review_type"] in {"content_review", "periodic_review", "emergency_review"},
            "未知审核类型",
        )
        _require(
            type(review["decision"]) is str
            and review["decision"]
            in {"approved", "rejected", "continue_valid", "revision_required", "offline"},
            "未知审核结论",
        )
        _id(review["reviewer_id"])
        _text(review["comment"])
        _time(review["reviewed_at"])


def convert_version(version, reviews):
    """接收 values() 形状的完整普通字典与审核列表；不读取任何关系。

    来源保留原生 UUID/datetime，属于内存纯数据结构，不宣称可直接存 JSONField。
    未来导入操作者/导入时间必须另外记录，不占用历史作者或审核时间字段。
    """
    _validate(version, reviews)
    return {
        "format": FORMAT,
        "content": {
            "title": version["title"],
            "summary": version["summary"],
            "body": encode_body(version["body"]),
        },
        "source": {
            "version": deepcopy({k: v for k, v in version.items() if k not in CONTENT_FIELDS}),
            "reviews": deepcopy(reviews),
        },
    }


def restore_version(converted):
    """返回 (version, reviews)，恢复结构、值和类型；不恢复 JSON 排版或对象共享关系。"""
    _keys(converted, ("format", "content", "source"), "转换结果")
    _require(converted["format"] == FORMAT, "未知转换格式版本")
    _keys(converted["content"], CONTENT_FIELDS, "内容")
    _keys(converted["source"], ("version", "reviews"), "来源")
    _keys(converted["source"]["version"], VERSION_FIELDS - CONTENT_FIELDS, "版本来源")
    version = deepcopy(converted["source"]["version"])
    version.update(
        title=converted["content"]["title"],
        summary=converted["content"]["summary"],
        body=decode_body(converted["content"]["body"]),
    )
    reviews = deepcopy(converted["source"]["reviews"])
    _validate(version, reviews)
    return version, reviews
