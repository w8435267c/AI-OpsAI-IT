"""统一 IT 服务申请入口的受控配置读取。"""

from urllib.parse import urlsplit

from django.conf import settings


def get_configured_service_request_url() -> str | None:
    """返回受控配置的 HTTPS/HTTP 服务入口；任何不安全值均按未配置处理。"""
    value = getattr(settings, "SERVICE_DESK_REQUEST_URL", "")
    if not isinstance(value, str) or not value.strip() or any(char.isspace() for char in value):
        return None

    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    return value
