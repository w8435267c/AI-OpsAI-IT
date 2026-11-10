"""钉钉 H5 登录 HTTP 边界；不包含真实钉钉 API 调用。"""

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .providers import get_identity_provider
from .services import SsoFlowError, begin_sso_login, complete_sso_login


@never_cache
@ensure_csrf_cookie
@require_GET
def sso_start(request):
    """创建当前浏览器会话的防重放状态，供受控 H5 客户端提交授权码时关联。"""

    state = begin_sso_login(request, target=request.GET.get("next"))
    return JsonResponse({"state": state})


@never_cache
@require_POST
def sso_complete(request):
    """仅接受授权码和会话状态；身份由服务端提供者验证而非浏览器参数决定。"""

    try:
        target = complete_sso_login(
            request,
            authorization_code=request.POST.get("code", ""),
            state=request.POST.get("state", ""),
            provider=get_identity_provider(),
        )
    except SsoFlowError:
        return HttpResponseForbidden("登录验证失败。")
    return redirect(target)
