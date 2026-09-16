"""F08C 集成、F08 纯函数及 F07 转换回归；合成配置、内存库与白名单/审计防护。"""

import importlib.abc
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from experiments.wagtail_f03a.run import SYSTEM_ENV, require  # noqa: E402

# 复用 F07 合成配置；本轮不新增 App、模型、迁移或配置。
SETTINGS = "experiments.wagtail_f07.settings"
LABELS = [
    "experiments.wagtail_f08.test_integration",
    "experiments.wagtail_f08.test_body_text",
    # F07 转换回归以裸模块名导入 conversion，与 F07 runner 一致按其目录收集。
    "test_conversion",
]


def child():
    violations = []

    def deny():
        violations.append(True)
        raise RuntimeError("禁止真实配置、.env、外部网络或非内存数据库")

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            if Path(os.fsdecode(args[0])).name.lower().startswith(".env"):
                deny()
        if event == "sqlite3.connect" and args[0] != ":memory:":
            deny()
        if event in {"socket.connect", "socket.getaddrinfo"}:
            deny()

    class Guard(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in {"config", "dotenv"}:
                deny()
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
        db = settings.DATABASES["default"]
        require(db["ENGINE"] == "django.db.backends.sqlite3", "只允许 SQLite")
        require(db["NAME"] == db["TEST"]["NAME"] == ":memory:", "只允许内存库")
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

    # 只影响裸标签 test_conversion 的导入路径，不改变合成配置或数据库。
    sys.path.insert(0, str(ROOT / "experiments" / "wagtail_f07"))
    result = Runner(verbosity=2, interactive=False).run_tests(LABELS)
    require(not violations, "存在隔离违规")
    print("隔离检查通过；SQLite :memory:；无真实配置或外部连接。")
    return bool(result)


def main():
    require(sys.flags.isolated, "必须使用 -I")
    require(Path(sys.prefix).resolve() == ROOT / ".venv", "必须使用融合工作目录的现有 .venv")
    if sys.argv[1:] == ["--child"]:
        return child()
    require(not sys.argv[1:], "本轮不接受参数")
    env = {key: value for key, value in os.environ.items() if key.upper() in SYSTEM_ENV}
    env.update(DJANGO_SETTINGS_MODULE=SETTINGS, PYTHONUTF8="1")
    return subprocess.call(
        [sys.executable, "-I", "-B", "-X", "utf8", str(HERE / "run_integration.py"), "--child"],
        cwd=ROOT,
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
