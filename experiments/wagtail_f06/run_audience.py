"""不启用 Wagtail 的受众专项：合成配置、内存 SQLite、禁止真实配置与联网。"""

import importlib.abc
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYSTEM_ENV = {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "COMSPEC", "PATHEXT"}


def child():
    violations = []

    def deny():
        violations.append(True)
        raise RuntimeError("禁止真实配置、Wagtail、.env、网络或持久数据库")

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0]))
            if (
                path.name.lower().startswith(".env")
                or path.resolve() == (ROOT / "config/settings/base.py").resolve()
            ):
                deny()
        if event == "sqlite3.connect" and str(args[0]) not in {
            ":memory:",
            "file:memorydb_default?mode=memory&cache=shared",
        }:
            deny()
        if event in {"socket.connect", "socket.getaddrinfo"}:
            deny()

    class Guard(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in {"config", "dotenv", "wagtail", "experiments"}:
                deny()
            return None

    sys.addaudithook(audit)
    sys.meta_path.insert(0, Guard())
    sys.path.insert(0, str(ROOT))
    from django.conf import settings

    settings.configure(
        SECRET_KEY="synthetic-audience-test-only",
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "apps.accounts",
            "apps.knowledge",
        ],
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
                "TEST": {"NAME": ":memory:"},
            }
        },
        AUTH_USER_MODEL="accounts.User",
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        USE_TZ=True,
        TIME_ZONE="Asia/Shanghai",
        KNOWLEDGE_IT_USER_GROUP_ID=None,
        PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    )
    import django
    from django.core.management import call_command

    django.setup()
    call_command("check", databases=["default"])
    from django.db import connections
    from django.test.runner import DiscoverRunner

    class Runner(DiscoverRunner):
        def setup_databases(self, **kwargs):
            call_command("migrate", interactive=False, verbosity=0)
            return None

        def teardown_databases(self, old_config, **kwargs):
            connections.close_all()

    result = Runner(verbosity=1).run_tests(["apps.knowledge.tests.test_selectors"])
    if violations:
        raise RuntimeError("隔离防护发现违规访问")
    print("隔离核验：未启用 Wagtail；未访问真实配置、.env、网络或持久库。")
    return result


if __name__ == "__main__":
    if sys.argv[1:] == ["--child"]:
        raise SystemExit(child())
    if sys.argv[1:]:
        raise SystemExit("此 runner 不接受测试范围或配置覆盖参数")
    env = {k: v for k, v in os.environ.items() if k.upper() in SYSTEM_ENV}
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()), "--child"],
            cwd=ROOT,
            env=env,
        )
    )
