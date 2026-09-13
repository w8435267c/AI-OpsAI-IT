"""仅安装实验模型，不注册 Snippet 后台。"""

from experiments.wagtail_f03b.settings import *  # noqa: F403
from experiments.wagtail_f03b.settings import INSTALLED_APPS as F03B_APPS

INSTALLED_APPS = [*F03B_APPS, "experiments.wagtail_f04a.apps.F04AConfig"]
