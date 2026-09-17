"""F08 页面合成配置：复用 F07/F06 隔离配置，只增加模板、路由与缓存边界。"""

from copy import deepcopy
from pathlib import Path

from experiments.wagtail_f07.settings import *  # noqa: F403
from experiments.wagtail_f07.settings import MIDDLEWARE as F07_MIDDLEWARE
from experiments.wagtail_f07.settings import TEMPLATES as F07_TEMPLATES

ROOT_URLCONF = "experiments.wagtail_f08.urls"
MIDDLEWARE = [
    "experiments.wagtail_f08.middleware.PrivateArticlePageMiddleware",
    *F07_MIDDLEWARE,
]
TEMPLATES = deepcopy(F07_TEMPLATES)
TEMPLATES[0]["DIRS"] = [
    Path(__file__).resolve().parent / "templates",
    *TEMPLATES[0].get("DIRS", []),
]
