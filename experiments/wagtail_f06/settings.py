"""F06 HTTP 合成配置：沿用会话认证、账号状态后端和 F05B 发布配置。"""

from experiments.wagtail_f05b.settings import *  # noqa: F403
from experiments.wagtail_f05b.settings import MIDDLEWARE as F05B_MIDDLEWARE

ROOT_URLCONF = "experiments.wagtail_f06.urls"
MIDDLEWARE = [
    "experiments.wagtail_f06.middleware.PrivateDetailResponseMiddleware",
    *F05B_MIDDLEWARE,
]
