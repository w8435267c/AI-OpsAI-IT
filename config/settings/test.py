"""不依赖外部系统的自动化测试设置。"""

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "django-insecure-fixed-test-key-not-for-production"
ALLOWED_HOSTS = ["testserver"]

# 模拟登录在测试中默认关闭；模拟登录相关测试使用 override_settings 显式开启。
DEV_LOGIN_ENABLED = False

# “仅 IT”受众绑定在测试中默认未配置；相关测试通过 self.settings / override_settings
# 显式指定临时用户组主键，保证不依赖开发环境的 KNOWLEDGE_IT_USER_GROUP_ID。
KNOWLEDGE_IT_USER_GROUP_ID = None

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
