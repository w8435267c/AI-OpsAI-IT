"""账号与组织视图入口：仅包含本地开发专用的模拟登录。"""

from django.conf import settings
from django.contrib import auth
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .forms import DevLoginForm
from .models import User
from .roles import DEV_IDENTITY_BY_USERNAME, has_real_identity


def _dev_login_available() -> bool:
    """模拟登录必须同时满足 DEBUG=True 与 DEV_LOGIN_ENABLED=True 才可用。"""
    return settings.DEBUG and settings.DEV_LOGIN_ENABLED


def _load_safe_dev_user(username: str):
    """按白名单取开发用户，并复核其仍是安全的开发身份（无密码、无真实身份特征、未禁用）。"""
    if DEV_IDENTITY_BY_USERNAME.get(username) is None:
        return None
    user = User.objects.filter(username=username).first()
    if user is None or not user.is_active or has_real_identity(user):
        return None
    return user


def _safe_next(request) -> str:
    """返回通过校验的同站 next 地址；缺失或不安全时返回空字符串，绝不外跳。"""
    next_url = request.POST.get("next") or request.GET.get("next")
    if not next_url:
        return ""
    if url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return ""


@never_cache
def dev_login(request):
    """本地开发模拟登录：GET 展示选择表单，POST 完成登录或切换身份。"""
    if not _dev_login_available():
        raise Http404
    form = DevLoginForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = _load_safe_dev_user(form.cleaned_data["username"])
            if user is None:
                form.add_error(
                    "username",
                    "所选开发用户不存在或不符合安全要求，"
                    "请先运行 python manage.py create_dev_users。",
                )
            else:
                auth.login(request, user)
                return redirect(_safe_next(request) or "accounts:dev-login")
    return render(request, "accounts/dev_login.html", {"form": form})


@never_cache
@require_POST
def dev_logout(request):
    """本地开发模拟登出：仅允许 POST；开关关闭时同样返回 404。"""
    if not _dev_login_available():
        raise Http404
    auth.logout(request)
    return redirect("accounts:dev-login")
