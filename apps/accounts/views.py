"""账号与组织视图入口：正式员工密码登录与本地开发模拟登录彼此隔离。"""

import hashlib

from django.conf import settings
from django.contrib import auth
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .forms import DevLoginForm, EmployeeAuthenticationForm
from .models import User
from .roles import DEV_IDENTITY_BY_USERNAME, dev_user_deviation


def _dev_login_available() -> bool:
    """模拟登录必须同时满足 DEBUG=True 与 DEV_LOGIN_ENABLED=True 才可用。"""
    return settings.DEBUG and settings.DEV_LOGIN_ENABLED


def _load_safe_dev_user(username: str):
    """按白名单取开发用户，并严格复核其仍是安全的开发身份。

    任何偏差（可用密码、超级管理员状态、staff 漂移、禁用/离职、
    身份字段、系统角色组或直接权限）都安全拒绝且绝不自动修复；
    拒绝原因不透露给登录页面，只给出统一的安全提示。
    """
    identity = DEV_IDENTITY_BY_USERNAME.get(username)
    if identity is None:
        return None
    user = User.objects.filter(username=username).first()
    if user is None:
        return None
    if dev_user_deviation(user, identity) is not None:
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


def _login_rate_limit_key(request) -> str:
    """对来源地址与用户名的组合限速，缓存键不保存明文用户名或密码。"""
    username = request.POST.get("username", "").strip().casefold()
    source = request.META.get("REMOTE_ADDR", "")
    subject = f"{source}\x00{username}".encode()
    digest = hashlib.sha256(subject).hexdigest()
    return f"accounts:employee-login-failure:{digest}"


def _is_login_rate_limited(request) -> bool:
    return cache.get(_login_rate_limit_key(request), 0) >= settings.LOCAL_LOGIN_MAX_FAILURES


def _record_login_failure(request) -> None:
    key = _login_rate_limit_key(request)
    if not cache.add(key, 1, timeout=settings.LOCAL_LOGIN_THROTTLE_SECONDS):
        cache.incr(key)


@never_cache
def employee_login(request):
    """正式员工密码登录；不提供注册、账号创建或权限授予能力。"""
    safe_next = _safe_next(request)
    form = EmployeeAuthenticationForm(request=request, data=request.POST or None)

    if request.method == "POST":
        if _is_login_rate_limited(request):
            response = HttpResponse("登录尝试过于频繁，请稍后再试。", status=429)
            response["Retry-After"] = str(settings.LOCAL_LOGIN_THROTTLE_SECONDS)
            return response
        if form.is_valid():
            cache.delete(_login_rate_limit_key(request))
            auth.login(request, form.get_user())
            return redirect(safe_next or settings.LOGIN_REDIRECT_URL)
        _record_login_failure(request)

    return render(request, "accounts/employee_login.html", {"form": form, "next": safe_next})


@never_cache
@require_POST
def employee_logout(request):
    """正式登录只允许通过受 CSRF 保护的 POST 退出。"""
    auth.logout(request)
    return redirect(settings.LOGIN_URL)


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
