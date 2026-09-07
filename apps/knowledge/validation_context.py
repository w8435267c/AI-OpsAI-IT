"""仅供 Admin 联合表单使用的实例级校验上下文，不来自 HTTP 字段。"""

from contextlib import contextmanager
from contextvars import ContextVar

pending_article = ContextVar("pending_article", default=None)
pending_audience = ContextVar("pending_audience", default=None)


@contextmanager
def joint_validation(variable, instance):
    token = variable.set(instance)
    try:
        yield
    finally:
        variable.reset(token)
