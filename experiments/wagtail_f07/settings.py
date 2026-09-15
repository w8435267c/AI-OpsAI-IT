"""只在合成 F07 演练中安装来源模型。"""

from experiments.wagtail_f06.settings import *  # noqa: F403
from experiments.wagtail_f06.settings import INSTALLED_APPS as F06_APPS

INSTALLED_APPS = [*F06_APPS, "experiments.wagtail_f07.apps.F07Config"]
