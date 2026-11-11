"""生产环境设置；所有敏感项均必须由环境变量提供。"""

import os

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
