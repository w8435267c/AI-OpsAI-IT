"""仅供本地骨架验证使用的开发设置。"""

import os

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

# 骨架阶段临时使用 SQLite；正式本地开发将在 Docker 阶段切换到 PostgreSQL。
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}
