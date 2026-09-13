"""F03A 仅复用 F02 的无凭据公共实验设置。"""

from experiments.wagtail_f02.f02_settings import *  # noqa: F403
from experiments.wagtail_f02.f02_settings import INSTALLED_APPS as F02_APPS

INSTALLED_APPS = [*F02_APPS, "django.contrib.admin", "apps.accounts.apps.AccountsConfig"]
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["experiments.wagtail_f03a.auth.AccountStateBackend"]
ROOT_URLCONF = "experiments.wagtail_f03a.urls"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    }
}
# 只对合成测试用户加速密码校验，不改变生产哈希器或 dev_* 身份。
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
WAGTAIL_SITE_NAME = "F03A account access experiment"
