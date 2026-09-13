"""F05A 独立配置，替换 F04B 注册 App，复用其设置和认证链。"""

from experiments.wagtail_f04b.settings import *  # noqa: F403
from experiments.wagtail_f04b.settings import INSTALLED_APPS as F04B_APPS

INSTALLED_APPS = [app for app in F04B_APPS if app != "experiments.wagtail_f04b.apps.F04BConfig"] + [
    "experiments.wagtail_f05a.apps.F05AConfig",
]
ROOT_URLCONF = "experiments.wagtail_f05a.urls"
WAGTAIL_FINISH_WORKFLOW_ACTION = "experiments.wagtail_f05a.policy.forbid_finish"
WAGTAIL_WORKFLOW_REQUIRE_REAPPROVAL_ON_EDIT = True
