"""各运行环境共享的 Django 设置。"""

import os
from pathlib import Path

from dotenv import load_dotenv

from apps.knowledge.configuration import parse_it_group_id

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

# 正式员工密码登录的安全默认值。账号由管理员在 Django Admin 中创建或启用，
# 不提供公开注册；失败计数只保存经哈希的来源/用户名组合，绝不记录密码。
LOGIN_URL = "employee-login"
LOGIN_REDIRECT_URL = "knowledge:home"
LOCAL_LOGIN_MAX_FAILURES = 5
LOCAL_LOGIN_THROTTLE_SECONDS = 300

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Asia/Shanghai")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "private_media"

# 私有知识媒体：实际格式由服务端解析，所有文件均需通过独立 ClamAV 扫描后
# 才能发布或读取。生产默认不配置扫描器，业务路径必须失败关闭。
KNOWLEDGE_MEDIA_MAX_IMAGE_BYTES = int(os.getenv("KNOWLEDGE_MEDIA_MAX_IMAGE_BYTES", "5242880"))
KNOWLEDGE_MEDIA_MAX_DOCUMENT_BYTES = int(
    os.getenv("KNOWLEDGE_MEDIA_MAX_DOCUMENT_BYTES", "10485760")
)
KNOWLEDGE_MEDIA_CLAMD_HOST = os.getenv("KNOWLEDGE_MEDIA_CLAMD_HOST", "")
KNOWLEDGE_MEDIA_CLAMD_PORT = int(os.getenv("KNOWLEDGE_MEDIA_CLAMD_PORT", "3310"))
KNOWLEDGE_MEDIA_CLAMD_TIMEOUT_SECONDS = int(
    os.getenv("KNOWLEDGE_MEDIA_CLAMD_TIMEOUT_SECONDS", "15")
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# 本地模拟登录总开关，默认关闭。只有 development.py 读取环境变量
# DJANGO_DEV_LOGIN_ENABLED；production.py 硬编码为 False，无法通过
# 环境变量重新开启；test.py 保持 False，相关测试用 override_settings 开启。
# 模拟登录 View 必须同时满足 DEBUG=True 且本开关为 True 才可用。
DEV_LOGIN_ENABLED = False

# 钉钉 H5 授权码关联状态仅在服务端 Session 中保存；真实身份提供者尚未接入时，
# dingtalk.providers 的默认实现必须失败关闭。此值不是凭据，也不能启用模拟身份。
DINGTALK_SSO_STATE_TTL_SECONDS = 300

# 公司现有 01_ServiceRequest 的受控入口。默认不配置，避免代码编造或接受用户提供的跳转地址。
SERVICE_DESK_REQUEST_URL = ""

# “仅 IT”内容受众绑定：通过环境变量 KNOWLEDGE_IT_USER_GROUP_ID 指定一个
# accounts.UserGroup 主键，作为 it_only 受众的唯一身份来源。缺省未配置（None）。
# 属于权限配置，由部署管理者显式设置；不按显示名称、角色名或部门名猜测 IT 身份。
# 配置缺失、无效或组不存在 / 停用时，不授予 it_only 阅读权限。
KNOWLEDGE_IT_USER_GROUP_ID = parse_it_group_id(os.getenv("KNOWLEDGE_IT_USER_GROUP_ID"))

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
