"""各运行环境共享的 Django 设置。"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]

# 本地可选加载真实 .env；仓库仅保存不含敏感信息的 .env.example。
load_dotenv(BASE_DIR / ".env")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core.apps.CoreConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.knowledge.apps.KnowledgeConfig",
    "apps.search.apps.SearchConfig",
    "apps.workflow.apps.WorkflowConfig",
    "apps.dingtalk.apps.DingtalkConfig",
    "apps.service_desk.apps.ServiceDeskConfig",
    "apps.audit.apps.AuditConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Asia/Shanghai")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "private_media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# 本地模拟登录总开关，默认关闭。只有 development.py 读取环境变量
# DJANGO_DEV_LOGIN_ENABLED；production.py 硬编码为 False，无法通过
# 环境变量重新开启；test.py 保持 False，相关测试用 override_settings 开启。
# 模拟登录 View 必须同时满足 DEBUG=True 且本开关为 True 才可用。
DEV_LOGIN_ENABLED = False

# “仅 IT”内容受众绑定：通过环境变量 KNOWLEDGE_IT_USER_GROUP_ID 指定一个
# accounts.UserGroup 主键，作为 it_only 受众的唯一身份来源。缺省未配置（None）。
# 属于权限配置，由部署管理者显式设置；不按显示名称、角色名或部门名猜测 IT 身份。
# 配置缺失、无效或组不存在 / 停用时，不授予 it_only 阅读权限。
_it_user_group_id = os.getenv("KNOWLEDGE_IT_USER_GROUP_ID")
KNOWLEDGE_IT_USER_GROUP_ID = (
    int(_it_user_group_id) if _it_user_group_id and _it_user_group_id.strip().isdigit() else None
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{asctime} {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
    },
}
