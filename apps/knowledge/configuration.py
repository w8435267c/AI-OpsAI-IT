"""不依赖 Django 初始化的内容受众配置解析。"""

MAX_USER_GROUP_ID = 2**63 - 1  # UserGroup 的 BigAutoField：有符号 64 位正整数。


def parse_it_group_id(value):
    """接受正整数或至多 19 位 ASCII 十进制字符串；其他输入失败关闭。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1 <= value <= MAX_USER_GROUP_ID else None
    if not isinstance(value, str) or len(value) > 19:
        return None
    if not value or not value.isascii() or not value.isdecimal():
        return None
    try:
        parsed = int(value)
    except (ValueError, OverflowError):
        return None
    return parsed if 1 <= parsed <= MAX_USER_GROUP_ID else None
