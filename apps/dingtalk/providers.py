"""钉钉身份提供者边界。

本模块刻意不实现真实 API 调用。未来受控接入应实现同一协议，并仅在受保护
服务端凭据、测试租户和单独授权齐备后注册；当前默认实现始终失败关闭。
"""

from dataclasses import dataclass
from typing import Protocol


class DingTalkIdentityProviderError(Exception):
    """身份提供者无法给出可信验证结果时抛出。"""


@dataclass(frozen=True)
class VerifiedDingTalkIdentity:
    """只能由可信服务端身份验证结果构造的最小身份载荷。"""

    corp_id: str
    user_id: str
    union_id: str | None = None


class DingTalkIdentityProvider(Protocol):
    """服务端授权码验证协议；不得从浏览器参数直接构造可信身份。"""

    def verify_authorization_code(self, authorization_code: str) -> VerifiedDingTalkIdentity: ...


class UnavailableDingTalkIdentityProvider:
    """默认提供者：真实钉钉验证未授权/未配置时拒绝全部登录。"""

    def verify_authorization_code(self, authorization_code: str) -> VerifiedDingTalkIdentity:
        raise DingTalkIdentityProviderError("trusted identity verification is unavailable")


def get_identity_provider() -> DingTalkIdentityProvider:
    """返回默认失败关闭的提供者。

    离线测试必须显式向服务或视图注入替身；没有基于 HTTP 参数、DEBUG 或环境变量
    启用模拟身份的路径，因此不能在正式环境绕过可信身份验证。
    """

    return UnavailableDingTalkIdentityProvider()
