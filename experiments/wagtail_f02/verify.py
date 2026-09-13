"""以白名单环境启动独立检查；只检查框架，不接入业务或数据库。"""

import importlib
import importlib.abc
import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE.parents[1] / ".venv"
SYSTEM_ENV = {"SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_framework():
    violations = []
    sqlite_probes = []

    def deny(reason):
        violations.append(reason)
        raise RuntimeError(reason)

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            name = Path(os.fsdecode(args[0])).name.lower()
            if name == ".env" or name.startswith(".env."):
                deny("禁止打开 .env 文件")
        if event == "sqlite3.connect":
            if args[0] != ":memory:":
                deny("只允许 SQLite 内存探测")
            sqlite_probes.append("memory")
        if event in {"socket.connect", "socket.getaddrinfo"}:
            deny("禁止网络或数据库连接")

    class BlockProjectImports(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in {"config", "apps", "dotenv"}:
                deny("禁止项目 settings、业务 App 或 dotenv 导入")
            return None

    sys.addaudithook(audit)
    sys.meta_path.insert(0, BlockProjectImports())
    sys.path.insert(0, str(HERE))
    allowed = SYSTEM_ENV | {"DJANGO_SETTINGS_MODULE", "PYTHONUTF8", "LC_CTYPE"}
    require(all(key.upper() in allowed for key in os.environ), "子进程环境不在白名单内")
    require(os.environ.get("DJANGO_SETTINGS_MODULE") == "f02_settings", "配置入口异常")
    print("解释器:", sys.executable, flush=True)
    print("Python:", sys.version.split()[0])
    print("独立配置:", HERE / "f02_settings.py")
    for distribution, module_name in [
        ("Django", "django"),
        ("Wagtail", "wagtail"),
        ("psycopg", "psycopg"),
        ("psycopg-binary", "psycopg_binary"),
        ("Pillow", "PIL.Image"),
        ("pillow-heif", "pillow_heif"),
        ("Willow", "willow"),
    ]:
        module = importlib.import_module(module_name)
        require(Path(module.__file__).resolve().is_relative_to(VENV), "导入不来自融合 .venv")
        print(distribution, importlib.metadata.version(distribution), "导入通过")
    print("python-dotenv", importlib.metadata.version("python-dotenv"), "仅核对元数据，禁止加载")

    import django
    from django.conf import settings
    from django.db.backends.base.base import BaseDatabaseWrapper

    def no_database(*args, **kwargs):
        deny("本轮禁止打开 Django 数据库连接")

    BaseDatabaseWrapper.connect = no_database
    require(
        settings.DATABASES
        == {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        "数据库配置不符合隔离要求",
    )
    require(settings.AUTH_USER_MODEL == "auth.User", "本轮仅验证默认用户模型")
    require(not settings.SILENCED_SYSTEM_CHECKS, "不得屏蔽系统检查")
    print("数据库配置: SQLite :memory:；数据库连接被检查脚本禁止")
    django.setup()
    print("django.setup(): 通过")

    from django.core.management import call_command
    from django.db import connections
    from django_tasks import task_backends

    require(
        type(task_backends["default"]).__module__ == "django_tasks.backends.dummy",
        "任务后端必须为本地 DummyBackend",
    )
    call_command("check", fail_level="WARNING")
    require(
        all(connection.connection is None for connection in connections.all()), "发现意外数据库连接"
    )
    require(not violations, "检测到被拦截的隔离违规")
    require(
        not any(name.split(".")[0] in {"config", "apps", "dotenv"} for name in sys.modules),
        "检测到禁止导入的模块",
    )
    print("SQLite 内存探测次数:", len(sqlite_probes))
    print("隔离检查: 无 .env 读取、业务模块加载、Django 数据库或网络连接")


def main():
    require(sys.flags.isolated, "请使用 -I 启动本脚本")
    require(Path(sys.prefix).resolve() == VENV.resolve(), "必须使用融合 .venv 解释器")
    if sys.argv[1:] == ["--child"]:
        check_framework()
        return 0
    require(not sys.argv[1:], "不支持的参数")
    env = {key: value for key, value in os.environ.items() if key.upper() in SYSTEM_ENV}
    env.update(DJANGO_SETTINGS_MODULE="f02_settings", PYTHONUTF8="1")
    return subprocess.call(
        [sys.executable, "-I", "-X", "utf8", str(Path(__file__).resolve()), "--child"],
        env=env,
        cwd=HERE,
    )


if __name__ == "__main__":
    raise SystemExit(main())
