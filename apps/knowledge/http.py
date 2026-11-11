"""正式员工只读页面共用的 HTTP 边界。"""

from collections.abc import Callable
from functools import wraps

from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.models import AccountStatus


def _private_no_store(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "private, no-store"
    return response


def has_active_employee_identity(user: object) -> bool:
    """确认请求主体是可用的正式员工账号。"""
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and getattr(user, "account_status", None) == AccountStatus.ACTIVE
    )


def employee_get_page(
    view: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    """将页面限制为有效员工的 GET 请求，并统一禁止共享缓存。"""

    @wraps(view)
    def wrapped(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if request.method != "GET":
            response = HttpResponse("仅支持 GET 请求。", status=405)
            response["Allow"] = "GET"
            return _private_no_store(response)

        user = request.user
        if not has_active_employee_identity(user):
            return _private_no_store(HttpResponse("需要有效员工身份。", status=401))

        return _private_no_store(view(request, *args, **kwargs))

    # 端点只接受 GET；避免 CSRF 中间件抢先返回 403，确保非 GET 统一为 405。
    return csrf_exempt(wrapped)


def employee_post_request(
    view: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    """将状态变更限制为有效员工的 POST 请求，并保留 Django CSRF 防护。"""

    @wraps(view)
    def wrapped(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if request.method != "POST":
            response = HttpResponse("仅支持 POST 请求。", status=405)
            response["Allow"] = "POST"
            return _private_no_store(response)
        if not has_active_employee_identity(request.user):
            return _private_no_store(HttpResponse("需要有效员工身份。", status=401))
        return _private_no_store(view(request, *args, **kwargs))

    return wrapped
