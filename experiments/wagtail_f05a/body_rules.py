"""提交审核与批准发布共用的最小正文规则；不判断内容质量，不解码迁移封套。"""

EMPTY_BODY_CODE = "empty_body"
EMPTY_BODY_REASON = "正文不能为空或仅包含空白，请补充后提交审核。"


class EmptyBodyRejected(Exception):
    """受审正文不是字符串，或去掉首尾空白后为空；异常不携带正文内容。"""

    def __init__(self, code=EMPTY_BODY_CODE, reason=EMPTY_BODY_REASON):
        self.code = code
        self.reason = reason
        super().__init__(reason)


def require_nonempty_body(body):
    """只校验“存在非空白字符的字符串”；不修改正文，也不填充占位文本。

    草稿暂存不调用本函数：空正文允许保存为草稿，只是不能提交审核或批准发布。
    本轮不判断内容质量、不解码迁移封套、不做 HTML 清洗或其他内容规则。
    """
    if not isinstance(body, str) or not body.strip():
        raise EmptyBodyRejected()
    return body


def require_revision_body(revision):
    """从服务端修订快照读取正文后校验；不接受客户端传来的正文。"""
    content = revision.content
    return require_nonempty_body(content.get("body") if isinstance(content, dict) else None)
