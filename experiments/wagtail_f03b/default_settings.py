"""未启用 Wagtail 的独立兼容配置，不导入任何生产配置。"""

from experiments.wagtail_f03b.settings import *  # noqa: F403

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts.apps.AccountsConfig",
    "apps.knowledge.apps.KnowledgeConfig",
]
ROOT_URLCONF = "experiments.wagtail_f03b.default_urls"
