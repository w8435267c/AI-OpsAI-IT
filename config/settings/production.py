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
