"""生产环境设置；所有敏感项均必须由环境变量提供。"""

import os
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ImproperlyConfigured(f"缺少必需的环境变量：{name}")
    return value


DEBUG = False
SECRET_KEY = _required_env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = [
    host.strip() for host in _required_env("DJANGO_ALLOWED_HOSTS").split(",") if host.strip()
]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS 必须至少包含一个主机名")


def _parse_csrf_trusted_origins() -> list[str]:
    """只接受显式声明的 HTTPS 可信来源；未配置时保留 Django 的同源保护。"""
    raw_origins = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "")
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    for origin in origins:
        parsed = urlparse(origin)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
            raise ImproperlyConfigured(
                "DJANGO_CSRF_TRUSTED_ORIGINS 必须是以 https:// 开头的来源列表"
            )
    return origins


CSRF_TRUSTED_ORIGINS = _parse_csrf_trusted_origins()

# 模拟登录在生产环境强制关闭：此处硬编码，不读取任何环境变量，
# 即使设置 DJANGO_DEV_LOGIN_ENABLED 也无法开启；正式认证仅可使用受控的员工密码登录
# 或未来单独接入并验证的钉钉身份提供者。
DEV_LOGIN_ENABLED = False

# 正式员工密码登录仅在 HTTPS 会话中使用；开发与测试设置不继承这些强制值。
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"

# Web 容器不发布宿主机端口，唯一允许的入口是受控 Caddy 反向代理。
# 仅信任由同一内部 Docker 网络上的 Caddy 写入的协议头。
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# HSTS 只有在负责人确认真实 HTTPS 证书、域名和客户端兼容性后才能启用。
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _required_env("POSTGRES_DB"),
        "USER": _required_env("POSTGRES_USER"),
        "PASSWORD": _required_env("POSTGRES_PASSWORD"),
        "HOST": _required_env("POSTGRES_HOST"),
        "PORT": _required_env("POSTGRES_PORT"),
    }
}
