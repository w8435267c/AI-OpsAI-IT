"""F08D-1 页面专项与 F06 详情读取回归；合成配置、内存库及审计防护。"""

import importlib.abc
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from experiments.wagtail_f03a.run import SYSTEM_ENV, require  # noqa: E402

SETTINGS = "experiments.wagtail_f08.settings"
LABELS = [
    "experiments.wagtail_f08.test_page",
    "experiments.wagtail_f06.test_readers",
]


def child():
    violations = []

    def deny(message):
        violations.append(message)
        raise RuntimeError(message)

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            name = Path(os.fsdecode(args[0])).name.lower()
            if name == ".env" or name.startswith(".env."):
                deny("禁止读取 .env 文件")
        if event == "sqlite3.connect" and args[0] != ":memory:":
            deny("仅允许 SQLite :memory: 连接")
        if event in {"socket.connect", "socket.getaddrinfo"}:
            deny("禁止外部网络连接")

    class Guard(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in {"config", "dotenv"}:
                deny("禁止导入真实配置或 dotenv")
            return None

    sys.addaudithook(audit)
    sys.meta_path.insert(0, Guard())
    allowed = SYSTEM_ENV | {"DJANGO_SETTINGS_MODULE", "PYTHONUTF8", "LC_CTYPE"}
    require(all(key.upper() in allowed for key in os.environ), "环境必须为白名单")
    require(os.environ.get("DJANGO_SETTINGS_MODULE") == SETTINGS, "配置错误")
    import django
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connections
    from django.test.runner import DiscoverRunner

    def assert_memory():
        require(set(settings.DATABASES) == {"default"}, "只允许 default")
        database = settings.DATABASES["default"]
        require(database["ENGINE"] == "django.db.backends.sqlite3", "只允许 SQLite")
        require(database["NAME"] == database["TEST"]["NAME"] == ":memory:", "只允许内存库")
        require(
            not settings.MIGRATION_MODULES and not settings.SILENCED_SYSTEM_CHECKS,
            "不得关闭迁移或屏蔽检查",
        )

    assert_memory()
    django.setup()
    print("解释器:", sys.executable, "配置:", settings.SETTINGS_MODULE, flush=True)
    print("测试标签:", ", ".join(LABELS), flush=True)
    call_command("makemigrations", check=True, dry_run=True, interactive=False)

    class Runner(DiscoverRunner):
        def setup_databases(self, **kwargs):
            assert_memory()
            call_command("migrate", run_syncdb=False, interactive=False, verbosity=0)
            return None

        def teardown_databases(self, old_config, **kwargs):
            connections.close_all()

    result = Runner(verbosity=2, interactive=False).run_tests(LABELS)
    require(not violations, "存在隔离违规")
    print("隔离检查通过；SQLite :memory:；无真实配置、.env 或外部连接。")
    return bool(result)


def main():
    require(sys.flags.isolated, "必须使用 -I")
    require(Path(sys.prefix).resolve() == ROOT / ".venv", "必须使用融合工作目录的现有 .venv")
    if sys.argv[1:] == ["--child"]:
        return child()
    require(not sys.argv[1:], "本轮不接受参数")
    environment = {key: value for key, value in os.environ.items() if key.upper() in SYSTEM_ENV}
    environment.update(DJANGO_SETTINGS_MODULE=SETTINGS, PYTHONUTF8="1")
    return subprocess.call(
        [sys.executable, "-I", "-B", "-X", "utf8", str(HERE / "run_page.py"), "--child"],
        cwd=ROOT,
        env=environment,
    )


if __name__ == "__main__":
    raise SystemExit(main())
