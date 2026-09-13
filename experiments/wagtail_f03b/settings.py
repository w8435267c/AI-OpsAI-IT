"""融合角色实验配置：权限解析及开发身份预检需要既有 knowledge App。"""

from experiments.wagtail_f03a.settings import *  # noqa: F403
from experiments.wagtail_f03a.settings import INSTALLED_APPS as F03A_APPS

INSTALLED_APPS = [*F03A_APPS, "apps.knowledge.apps.KnowledgeConfig"]
DEV_LOGIN_ENABLED = False
KNOWLEDGE_IT_USER_GROUP_ID = None
