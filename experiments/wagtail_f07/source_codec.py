"""JSONField 用类型封套；每个节点都编码，不解释普通字典的保留键。"""

from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .conversion import ConversionError, _dump, _require

SOURCE_FORMAT = "opsai.typed-source/1"


def _pack(value):
    if value is None or type(value) in (str, bool, int, float):
        _dump(value)
        return ["scalar", value]
    if type(value) is UUID:
        return ["uuid", str(value)]
    if type(value) is datetime:
        if type(value.tzinfo) is timezone:
            offset = value.utcoffset() // timedelta(microseconds=1)
            tz = ["fixed", offset, value.tzname()]
        elif type(value.tzinfo) is ZoneInfo:
            tz = ["zone", value.tzinfo.key]
        else:
            raise ConversionError("来源时间须带标准库时区")
        return ["datetime", value.isoformat(), value.fold, tz]
    if type(value) is list:
        return ["list", [_pack(v) for v in value]]
    if type(value) is dict:
        _require(all(type(k) is str for k in value), "来源字典键必须是字符串")
        return ["dict", [[k, _pack(v)] for k, v in sorted(value.items())]]
    raise ConversionError("不支持的来源类型")


def _unpack(node):
    _require(type(node) is list and len(node) >= 2 and type(node[0]) is str, "损坏的来源节点")
    tag = node[0]
    if tag == "datetime":
        _require(
            len(node) == 4 and type(node[1]) is str and type(node[2]) is int and node[2] in (0, 1),
            "损坏的时间节点",
        )
        spec = node[3]
        _require(type(spec) is list and len(spec) >= 2, "损坏的时区节点")
        if spec[0] == "fixed":
            _require(
                len(spec) == 3 and type(spec[1]) is int and type(spec[2]) is str, "损坏的固定时区"
            )
            tz = timezone(timedelta(microseconds=spec[1]), spec[2])
        elif spec[0] == "zone":
            _require(len(spec) == 2 and type(spec[1]) is str, "损坏的地区时区")
            tz = ZoneInfo(spec[1])
        else:
            raise ConversionError("未知时区类型")
        value = datetime.fromisoformat(node[1]).replace(tzinfo=tz, fold=node[2])
        _require(_pack(value) == node, "时间或时区信息不一致")
        return value
    _require(len(node) == 2, "来源节点长度错误")
    data = node[1]
    if tag == "scalar":
        _require(data is None or type(data) in (str, bool, int, float), "损坏的标量节点")
        _dump(data)
        return data
    if tag == "uuid":
        _require(type(data) is str, "损坏的 UUID 节点")
        return UUID(data)
    if tag == "list":
        _require(type(data) is list, "损坏的列表节点")
        return [_unpack(v) for v in data]
    if tag == "dict":
        _require(type(data) is list, "损坏的字典节点")
        result = {}
        for pair in data:
            _require(type(pair) is list and len(pair) == 2 and type(pair[0]) is str, "损坏的字典项")
            _require(pair[0] not in result, "重复来源字典键")
            result[pair[0]] = _unpack(pair[1])
        return result
    raise ConversionError("未知来源节点类型")


def serialize_source(value):
    try:
        packed = {"format": SOURCE_FORMAT, "value": _pack(value)}
        _dump(packed)
        return packed
    except (RecursionError, OverflowError) as exc:
        raise ConversionError("来源数据过深或超出范围") from exc


def deserialize_source(value):
    _require(type(value) is dict and set(value) == {"format", "value"}, "来源封套字段错误")
    _require(value["format"] == SOURCE_FORMAT, "未知来源序列化版本")
    try:
        return _unpack(value["value"])
    except (ValueError, TypeError, OverflowError, RecursionError, ZoneInfoNotFoundError) as exc:
        raise ConversionError("来源编码无效或无法还原") from exc
