"""生成 F08D-2 合成员工详情页 HTML；只使用内存库和现有视图/模板。"""

import importlib.abc
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from experiments.wagtail_f03a.run import SYSTEM_ENV, require  # noqa: E402

SETTINGS = "experiments.wagtail_f08.settings"


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
    from django.test import Client
    from django.urls import reverse

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
    call_command("migrate", run_syncdb=False, interactive=False, verbosity=0)

    from experiments.wagtail_f04a.models import KnowledgeContent
    from experiments.wagtail_f05a.services import submit
    from experiments.wagtail_f05b.services import approve_review
    from experiments.wagtail_f06.test_readers import DetailTests

    fixture = DetailTests(methodName="test_published_without_legacy_pointer_and_whitelist")
    fixture.setUp()
    title = "Windows 客户端日志采集与故障排查"
    summary = "合成预览：普通文本正式快照；标签、脚本与 JSON 外观均应显示为文字。"
    body = (
        "适用范围：Windows 10 / Windows 11\n"
        "\n"
        "操作步骤：\n"
        "  1. 打开事件查看器，确认系统时间与故障时间一致。\n"
        "  2. 收集 C:\\Program Files\\OpsAI\\logs\\agent-output.log。\n"
        "  3. 将日志编号记录为 INC-2026-0001，不要粘贴账号或密钥。\n"
        "\n"
        "内部缩进示例：\n"
        "    服务名称：OpsAI Agent\n"
        "    启动类型：自动\n"
        "\n"
        "长连续文本：ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\n"
        "\n"
        "以下内容必须作为普通文字显示：\n"
        '<script>alert("offline-preview")</script>\n'
        '<section data-kind="demo">这不是 HTML 区块</section>\n'
        '{"format": "plaintext", "render": "escaped"}'
    )
    content = KnowledgeContent.objects.get(pk=fixture.content.pk)
    content.title, content.summary, content.body = title, summary, body
    revision = content.save_revision(user=fixture.creator)
    state = submit(content.pk, revision.pk, fixture.submitter)
    approve_review(state.current_task_state_id, fixture.reviewer)

    client = Client()
    fixture.employee.set_password("synthetic-f08d2-preview")
    fixture.employee.save(update_fields=["password"])
    require(
        client.login(
            username=fixture.employee.username,
            password="synthetic-f08d2-preview",
        ),
        "合成员工登录失败",
    )
    url = reverse("f08_article_detail", args=[fixture.article.pk])
    response = client.get(url)
    require(response.status_code == 200, f"页面响应不是 200：{response.status_code}")
    require(response["Cache-Control"] == "private, no-store", "缓存头不符合预期")
    html = response.content.decode("utf-8")
    require("&lt;script&gt;" in html and "<script>alert" not in html, "脚本外观文本未转义")
    require("white-space: pre-wrap" in html, "正文换行样式缺失")

    output_dir = Path(tempfile.mkdtemp(prefix="opsai-f08d2-preview-", dir=ROOT.parent))
    require(ROOT not in output_dir.parents and output_dir != ROOT, "预览目录必须位于仓库外")
    output_path = output_dir / "article-detail.html"
    require(not output_path.exists(), "不得覆盖已有预览文件")
    output_path.write_bytes(response.content)
    client.cookies.clear()
    require(not violations, "存在隔离违规")
    print("F08D2_PREVIEW_URL=" + url)
    print("F08D2_PREVIEW_HTML=" + str(output_path.resolve()))
    print("F08D2_PREVIEW_REVISION=" + str(revision.pk))
    print("合成数据离线页面预览已生成；SQLite :memory:；未保存登录 Cookie 或会话标识。")


def main():
    require(sys.flags.isolated, "必须使用 -I")
    require(Path(sys.prefix).resolve() == ROOT / ".venv", "必须使用融合工作目录的现有 .venv")
    if sys.argv[1:] == ["--child"]:
        child()
        return 0
    require(not sys.argv[1:], "本轮不接受参数")
    environment = {key: value for key, value in os.environ.items() if key.upper() in SYSTEM_ENV}
    environment.update(DJANGO_SETTINGS_MODULE=SETTINGS, PYTHONUTF8="1")
    return subprocess.call(
        [
            sys.executable,
            "-I",
            "-B",
            "-X",
            "utf8",
            str(HERE / "preview_page.py"),
            "--child",
        ],
        cwd=ROOT,
        env=environment,
    )


if __name__ == "__main__":
    raise SystemExit(main())
