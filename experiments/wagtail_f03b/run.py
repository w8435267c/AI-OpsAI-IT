"""F03B 两种独立内存配置的测试入口；不修改 F03A 入口契约。"""

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
        raise RuntimeError("禁止 .env、真实配置、外部网络或非内存数据库访问")

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
            if mode == "default" and fullname.split(".")[0] == "wagtail":
                deny()
            return None

    sys.addaudithook(audit)
    sys.meta_path.insert(0, Guard())
    allowed = SYSTEM_ENV | {"DJANGO_SETTINGS_MODULE", "PYTHONUTF8", "LC_CTYPE"}
    require(all(k.upper() in allowed for k in os.environ), "环境不在白名单")
    module = "default_settings" if mode == "default" else "settings"
    require(
        os.environ.get("DJANGO_SETTINGS_MODULE") == f"experiments.wagtail_f03b.{module}",
        "配置入口不匹配",
    )
    import django
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connections
    from django.test.runner import DiscoverRunner

    def assert_memory():
        require(set(settings.DATABASES) == {"default"}, "仅允许 default")
        db = settings.DATABASES["default"]
        require(db["ENGINE"] == "django.db.backends.sqlite3", "仅允许 SQLite")
        require(db["NAME"] == db["TEST"]["NAME"] == ":memory:", "仅允许内存库")
        require(not db.get("HOST") and not db.get("PASSWORD"), "禁止外部连接配置")
        require(
            not settings.MIGRATION_MODULES and not settings.SILENCED_SYSTEM_CHECKS,
            "不得替换迁移或屏蔽检查",
        )

    assert_memory()
    print("解释器:", sys.executable, "配置:", settings.SETTINGS_MODULE, flush=True)
    django.setup()

    class Runner(DiscoverRunner):
        def setup_databases(self, **kwargs):
            assert_memory()
            call_command("migrate", run_syncdb=False, interactive=False, verbosity=0)
            return None

        def teardown_databases(self, old_config, **kwargs):
            connections.close_all()

    labels = (
        [
            "experiments.wagtail_f03b.test_default",
            "apps.accounts.tests.test_roles",
            "apps.accounts.tests.test_dev_users",
        ]
        if mode == "default"
        else ["experiments.wagtail_f03b.test_profiles", "experiments.wagtail_f03b.test_access"]
    )
    failures = Runner(verbosity=2, interactive=False, parallel=1).run_tests(labels)
    require(not violations, "检测到隔离违规")
    if mode == "default":
        require(
            not any(n == "wagtail" or n.startswith("wagtail.") for n in sys.modules),
            "默认进程不得加载 Wagtail",
        )
    print("隔离核验通过；未访问持久库或外部网络。")
    return bool(failures)


def main():
    require(sys.flags.isolated, "必须使用 -I")
    require(Path(sys.prefix).resolve() == ROOT / ".venv", "必须使用融合 .venv")
    if len(sys.argv) == 3 and sys.argv[1] == "--child" and sys.argv[2] in {"default", "fusion"}:
        return child(sys.argv[2])
    require(sys.argv[1:] in ([], ["default"], ["fusion"]), "参数仅允许 default 或 fusion")
    modes = sys.argv[1:] or ["fusion", "default"]
    failures = 0
    for mode in modes:
        env = {k: v for k, v in os.environ.items() if k.upper() in SYSTEM_ENV}
        module = "default_settings" if mode == "default" else "settings"
        env.update(DJANGO_SETTINGS_MODULE=f"experiments.wagtail_f03b.{module}", PYTHONUTF8="1")
        failures |= subprocess.call(
            [sys.executable, "-I", "-X", "utf8", str(Path(__file__).resolve()), "--child", mode],
            cwd=HERE,
            env=env,
        )
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
