"""迁移正文到普通文本的纯转换；不产生审核或员工读取资格。"""

from dataclasses import dataclass

from experiments.wagtail_f07.conversion import ConversionError, decode_body


@dataclass(frozen=True)
class PlaintextResult:
    success: bool
    text: str | None
    code: str
    reason: str


def convert_encoded_body_to_plaintext(encoded_body):
    """委托 F07 校验，仅原样返回字符串；失败 text=None，不提供部分正文。

    输出是普通字符串，未经 HTML 清洗，未来页面必须按普通文本转义。
    摘要一致不证明来源可信或已经批准，转换成功不授权发布或员工读取。
    """
    try:
        payload = decode_body(encoded_body)
    except ConversionError:
        return PlaintextResult(
            False, None, "invalid_encoded_body", "迁移正文封套、格式版本或摘要校验失败"
        )
    if type(payload) is str:
        return PlaintextResult(True, payload, "ok", "已转换为普通文本，仍需编辑确认与审核")
    codes = {
        dict: "unsupported_mapping",
        list: "unsupported_sequence",
        int: "unsupported_number",
        float: "unsupported_number",
        bool: "unsupported_boolean",
        type(None): "unsupported_null",
    }
    return PlaintextResult(
        False,
        None,
        codes.get(type(payload), "unsupported_payload"),
        "不支持自动转换，需要人工确认",
    )
