from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def live(request):
    """返回不依赖数据库或外部系统的进程存活状态。"""
    return JsonResponse({"status": "ok", "service": "opsai-it"})
