"""核心健康检查视图。"""

import os
import tempfile

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def live(request):
    """返回不依赖数据库或外部系统的进程存活状态。"""
    return JsonResponse({"status": "ok", "service": "opsai-it"})


@require_GET
def ready(request):
    """就绪检查：数据库可执行轻量查询，且私有附件目录真实可写。

    只返回检查项的成功/失败，不返回异常文本、路径、连接信息或堆栈。
    """
    checks = {
        "database": _database_ready(),
        "private_media": _media_dir_writable(),
    }
    is_ready = all(checks.values())
    return JsonResponse(
        {"status": "ok" if is_ready else "unavailable", "checks": checks},
        status=200 if is_ready else 503,
    )


def _database_ready() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # noqa: BLE001 - 就绪检查必须吞掉一切数据库异常细节
        return False
    return True


def _media_dir_writable() -> bool:
    """通过创建并删除临时文件验证目录真实可写，而非仅检查权限位。"""
    try:
        fd, path = tempfile.mkstemp(prefix=".health-", dir=settings.MEDIA_ROOT)
        os.close(fd)
        os.remove(path)
    except Exception:  # noqa: BLE001 - 同上
        return False
    return True
