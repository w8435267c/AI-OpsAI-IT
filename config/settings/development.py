"""仅供本地开发使用的设置；数据库为 deploy/compose.yaml 提供的 PostgreSQL。"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-opsai-it-skeleton-only-not-for-production",
)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

# 本地模拟登录开关（仅限本机开发）：默认关闭，需在未跟踪的 .env 中
# 显式设置 DJANGO_DEV_LOGIN_ENABLED=true 并重启 web 服务才会启用；
# 生产与测试设置硬关闭，且生产不受环境变量影响。正式认证由钉钉免登实现。
# 仅识别 1/true/yes/on（不区分大小写），其余值一律视为关闭。
DEV_LOGIN_ENABLED = os.getenv("DJANGO_DEV_LOGIN_ENABLED", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# 本地开发数据库：由 deploy/compose.yaml 的 db 服务提供。
# 变量由 base.py 已加载的根目录 .env 提供；只提示缺失的变量名，不输出任何值。
_REQUIRED_POSTGRES_VARS = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
_missing = [name for name in _REQUIRED_POSTGRES_VARS if not os.getenv(name)]
if _missing:
    raise ImproperlyConfigured(
        "缺少 PostgreSQL 环境变量：{}。请按 README 复制 .env.example 为 .env 并填入本地值。".format(
            ", ".join(_missing)
        )
    )

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        # 就绪检查在数据库停止时快速失败，避免长时间卡住
        "OPTIONS": {"connect_timeout": 3},
    }
}
