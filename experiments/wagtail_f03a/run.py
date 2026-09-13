"""F03A 隔离入口：只在内存中通过已有迁移建表并运行专项请求测试。"""

import importlib.abc
import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SYSTEM_ENV = {"SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}
SETTINGS = "experiments.wagtail_f03a.settings"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


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

    class BlockImports(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in {"config", "dotenv"}:
                deny("禁止主项目配置或 dotenv 导入")
            if fullname.startswith("apps.") and not fullname.startswith("apps.accounts"):
                deny("本轮只允许 accounts 业务 App")
            return None

    sys.addaudithook(audit)
    sys.meta_path.insert(0, BlockImports())
    sys.path.insert(0, str(ROOT))
    allowed = SYSTEM_ENV | {"DJANGO_SETTINGS_MODULE", "PYTHONUTF8", "LC_CTYPE"}
    require(all(key.upper() in allowed for key in os.environ), "环境白名单不匹配")
    require(os.environ.get("DJANGO_SETTINGS_MODULE") == SETTINGS, "settings 入口不匹配")

    import django
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connections
    from django.db.backends.base.base import BaseDatabaseWrapper
    from django.test.runner import DiscoverRunner

    def assert_memory():
        require(set(settings.DATABASES) == {"default"}, "仅允许 default 数据库")
        db = settings.DATABASES["default"]
        require(db["ENGINE"] == "django.db.backends.sqlite3", "数据库必须为 SQLite")
        require(db["NAME"] == db["TEST"]["NAME"] == ":memory:", "禁止持久数据库")
        require(not db.get("HOST") and not db.get("PASSWORD"), "禁止外部数据库配置")
        require(not settings.MIGRATION_MODULES, "禁止替换已有迁移")
        require(not settings.SILENCED_SYSTEM_CHECKS, "禁止屏蔽检查")

    original_connect = BaseDatabaseWrapper.connect

    def guarded_connect(connection):
        assert_memory()
        require(connection.vendor == "sqlite", "禁止外部数据库连接")
        require(connection.settings_dict["NAME"] == ":memory:", "禁止文件数据库")
        return original_connect(connection)

    BaseDatabaseWrapper.connect = guarded_connect
    assert_memory()
    print("解释器:", sys.executable, flush=True)
    print("配置:", HERE / "settings.py")
    print("Python:", sys.version.split()[0])
    for name in ("Django", "Wagtail"):
        print(name, importlib.metadata.version(name))
    print("迁移前断言通过: SQLite :memory: / TEST :memory:")
    django.setup()

    class MemoryRunner(DiscoverRunner):
        # 默认 DiscoverRunner 会调用 migrate(run_syncdb=True)，本轮显式禁止该旁路。
        def setup_databases(self, **kwargs):
            assert_memory()
            call_command(
                "migrate", database="default", run_syncdb=False, interactive=False, verbosity=1
            )
            return None

        def teardown_databases(self, old_config, **kwargs):
            connections.close_all()
            # 内存数据库随隔离子进程退出销毁，不创建或删除任何持久文件。

    runner = MemoryRunner(verbosity=2, interactive=False, parallel=1)
    failures = runner.run_tests(["experiments.wagtail_f03a.test_access"])
    require(not violations, "隔离哨兵发现违规")
    print("隔离检查: 无 .env 读取、主配置加载或外部连接")
    return bool(failures)


def main():
    require(sys.flags.isolated, "必须使用 -I 启动")
    require(Path(sys.prefix).resolve() == ROOT / ".venv", "必须使用融合 .venv")
    if sys.argv[1:] == ["--child"]:
        return child()
    require(not sys.argv[1:], "不支持额外参数")
    env = {key: value for key, value in os.environ.items() if key.upper() in SYSTEM_ENV}
    env.update(DJANGO_SETTINGS_MODULE=SETTINGS, PYTHONUTF8="1")
    return subprocess.call(
        [sys.executable, "-I", "-X", "utf8", str(Path(__file__).resolve()), "--child"],
        cwd=HERE,
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
