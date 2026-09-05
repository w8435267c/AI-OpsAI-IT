"""不依赖外部系统的自动化测试设置。"""

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "django-insecure-fixed-test-key-not-for-production"
ALLOWED_HOSTS = ["testserver"]

# 模拟登录在测试中默认关闭；模拟登录相关测试使用 override_settings 显式开启。
DEV_LOGIN_ENABLED = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
