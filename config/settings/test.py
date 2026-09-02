"""不依赖外部系统的自动化测试设置。"""

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "django-insecure-fixed-test-key-not-for-production"
ALLOWED_HOSTS = ["testserver"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
