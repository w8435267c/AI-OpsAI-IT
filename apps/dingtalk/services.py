"""钉钉 H5 离线 SSO 的会话编排服务。"""

import secrets
import time

from django.conf import settings
from django.contrib import auth
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme

from apps.dingtalk.authentication import IdentityMappingError, map_verified_identity
from apps.dingtalk.providers import DingTalkIdentityProvider, DingTalkIdentityProviderError

SSO_FLOW_SESSION_KEY = "dingtalk_sso_flow"
DEFAULT_STATE_TTL_SECONDS = 300


class SsoFlowError(Exception):
    """浏览器会话、授权码或可信身份校验失败时使用的统一安全错误。"""


def _safe_target(request, target: str | None) -> str:
    if target and url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return reverse("knowledge:home")


def begin_sso_login(request, *, target: str | None) -> str:
    """生成并在当前会话持久化一次性状态；仅保存经过校验的同站目标页。"""

    state = secrets.token_urlsafe(32)
    request.session[SSO_FLOW_SESSION_KEY] = {
        "state": state,
        "issued_at": time.time(),
        "used": False,
        "target": _safe_target(request, target),
    }
    request.session.modified = True
    return state


def complete_sso_login(
    request, *, authorization_code: str, state: str, provider: DingTalkIdentityProvider
) -> str:
    """验证一次性状态和可信身份，建立 Django 会话并返回已保存的安全目标页。"""

    flow = request.session.get(SSO_FLOW_SESSION_KEY)
    if not isinstance(flow, dict):
        raise SsoFlowError("missing login flow")

    expected_state = flow.get("state")
    issued_at = flow.get("issued_at")
    ttl = getattr(settings, "DINGTALK_SSO_STATE_TTL_SECONDS", DEFAULT_STATE_TTL_SECONDS)
    now = time.time()
    if (
        not isinstance(expected_state, str)
        or not isinstance(issued_at, (int, float))
        or flow.get("used") is not False
        or not state
        or not constant_time_compare(expected_state, state)
        or issued_at > now
        or now - issued_at > ttl
        or not authorization_code
    ):
        request.session.pop(SSO_FLOW_SESSION_KEY, None)
        raise SsoFlowError("invalid or expired login flow")

    # 必须在外部身份验证前持久化消费标记，避免同一浏览器会话重放授权码。
    flow["used"] = True
    request.session[SSO_FLOW_SESSION_KEY] = flow
    request.session.modified = True

    try:
        identity = provider.verify_authorization_code(authorization_code)
        user = map_verified_identity(identity)
    except (DingTalkIdentityProviderError, IdentityMappingError) as error:
        raise SsoFlowError("trusted identity login was rejected") from error

    target = _safe_target(request, flow.get("target"))
    auth.login(request, user)
    return target
