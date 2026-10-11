"""正式知识管理页面共用的 HTTP 边界。"""

from collections.abc import Callable
from functools import wraps

from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.accounts.models import AccountStatus


def _private_no_store(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "private, no-store"
    return response


def _manage_page(
    view: Callable[..., HttpResponse],
    *,
    allowed_methods: tuple[str, ...],
    json_errors: bool = False,
) -> Callable[..., HttpResponse]:
    """限制请求方法与有效业务账号，并统一禁止共享缓存。"""

    @wraps(view)
    def wrapped(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if request.method not in allowed_methods:
            allow = ", ".join(allowed_methods)
            if json_errors:
                response = JsonResponse(
                    {
                        "ok": False,
                        "error": {
                            "code": "METHOD_NOT_ALLOWED",
                            "message": f"仅支持 {allow} 请求。",
                        },
                    },
                    status=405,
                )
            else:
                response = HttpResponse(f"仅支持 {allow} 请求。", status=405)
            response["Allow"] = allow
            return _private_no_store(response)

        user = request.user
        if (
            not user.is_authenticated
            or not user.is_active
            or getattr(user, "account_status", None) != AccountStatus.ACTIVE
        ):
            if json_errors:
                return _private_no_store(
                    JsonResponse(
                        {
                            "ok": False,
                            "error": {
                                "code": "ACCOUNT_INACTIVE",
                                "message": "需要有效员工身份。",
                            },
                        },
                        status=401,
                    )
                )
            return _private_no_store(HttpResponse("需要有效员工身份。", status=401))

        return _private_no_store(view(request, *args, **kwargs))

    return wrapped


def manage_get_page(
    view: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    """限制为有效业务账号的 GET 请求。"""

    return _manage_page(view, allowed_methods=("GET",))


def manage_get_post_page(
    view: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    """限制为有效业务账号的 GET/POST 请求。"""

    return _manage_page(view, allowed_methods=("GET", "POST"))


def manage_post_json_page(
    view: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    """限制为有效业务账号的 POST JSON 请求。"""

    return _manage_page(view, allowed_methods=("POST",), json_errors=True)
