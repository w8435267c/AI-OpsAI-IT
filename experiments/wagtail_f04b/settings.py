"""仅增加后台注册，不增加模型或迁移。"""

from experiments.wagtail_f04a.settings import *  # noqa: F403
from experiments.wagtail_f04a.settings import INSTALLED_APPS as F04A_APPS

INSTALLED_APPS = [*F04A_APPS, "experiments.wagtail_f04b.apps.F04BConfig"]
ROOT_URLCONF = "experiments.wagtail_f04b.urls"
# 上游自动保存会提交 overwrite_revision_id；本轮仅提供手动追加草稿。
WAGTAIL_AUTOSAVE_INTERVAL = 0
