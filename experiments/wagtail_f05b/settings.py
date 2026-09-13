"""F05B 服务及 HTTP 实验；只新增受保护的任务批准入口。"""

from experiments.wagtail_f05a.settings import *  # noqa: F403
from experiments.wagtail_f05a.settings import INSTALLED_APPS as F05A_APPS

INSTALLED_APPS = [*F05A_APPS, "experiments.wagtail_f05b.apps.F05BConfig"]

WAGTAIL_FINISH_WORKFLOW_ACTION = "experiments.wagtail_f05b.finish.publish_reviewed"
