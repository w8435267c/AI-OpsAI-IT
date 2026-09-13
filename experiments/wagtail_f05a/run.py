"""白名单子进程：只生成实验迁移或在内存库验证。"""

import importlib.abc
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from experiments.wagtail_f03a.run import SYSTEM_ENV, require  # noqa: E402


def child(mode):
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
    require(all(k.upper() in allowed for k in os.environ), "环境必须为白名单")
    require(
        os.environ.get("DJANGO_SETTINGS_MODULE") == "experiments.wagtail_f05a.settings", "配置错误"
    )
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
    print("解释器:", sys.executable, "配置:", HERE / "settings.py", flush=True)
    if mode == "makemigrations":
        call_command("makemigrations", "fusion_f04a", "fusion_f05a", interactive=False)
        result = 0
    else:
        call_command("makemigrations", check=True, dry_run=True, interactive=False)

        class Runner(DiscoverRunner):
            def setup_databases(self, **kwargs):
                assert_memory()
                call_command("migrate", run_syncdb=False, interactive=False, verbosity=0)
                return None

            def teardown_databases(self, old_config, **kwargs):
                connections.close_all()

        result = Runner(verbosity=2, interactive=False).run_tests(
            ["experiments.wagtail_f05a.tests"]
        )
    require(not violations, "存在隔离违规")
    print("隔离检查通过；SQLite :memory:；无真实配置或外部连接。")
    return bool(result)


def main():
    require(sys.flags.isolated, "必须使用 -I")
    require(Path(sys.prefix).resolve() == ROOT / ".venv", "必须使用融合环境")
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        require(sys.argv[2] in {"test", "makemigrations"}, "参数错误")
        return child(sys.argv[2])
    require(sys.argv[1:] in ([], ["makemigrations"]), "参数错误")
    mode = "makemigrations" if sys.argv[1:] else "test"
    env = {k: v for k, v in os.environ.items() if k.upper() in SYSTEM_ENV}
    env.update(DJANGO_SETTINGS_MODULE="experiments.wagtail_f05a.settings", PYTHONUTF8="1")
    return subprocess.call(
        [sys.executable, "-I", "-X", "utf8", str(Path(__file__).resolve()), "--child", mode],
        cwd=ROOT,
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
