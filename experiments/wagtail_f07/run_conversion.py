"""纯 unittest 入口：禁止框架、数据库驱动、真实配置和网络访问。"""

import importlib.abc
import os
import sys
import unittest
from pathlib import Path


def main():
    if not sys.flags.isolated:
        raise RuntimeError("必须使用 -I 启动")
    violations = []

    def deny():
        violations.append(True)
        raise RuntimeError("纯数据测试禁止框架、数据库、.env 或网络访问")

    class Guard(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in {
                "django",
                "wagtail",
                "apps",
                "config",
                "dotenv",
                "sqlite3",
                "psycopg",
            }:
                deny()
            return None

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            if Path(os.fsdecode(args[0])).name.lower().startswith(".env"):
                deny()
        if event in {"sqlite3.connect", "socket.connect", "socket.getaddrinfo"}:
            deny()

    sys.meta_path.insert(0, Guard())
    sys.addaudithook(audit)
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    suite = unittest.defaultTestLoader.discover(str(here), pattern="test_conversion.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if violations:
        raise RuntimeError("检测到隔离违规")
    print("纯标准库测试；无框架、数据库或真实配置访问。")
    return not result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(main())
