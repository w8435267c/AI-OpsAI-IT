"""可信钉钉身份到既有 Django 员工账号的安全映射。"""

from django.contrib.auth import get_user_model

from apps.accounts.models import AccountStatus
from apps.dingtalk.providers import VerifiedDingTalkIdentity


class IdentityMappingError(Exception):
    """可信身份无法安全映射到一个可用的现有员工账号。"""


def map_verified_identity(identity: VerifiedDingTalkIdentity):
    """仅以 ``corp_id + user_id`` 精确映射一个正常、启用的既有员工。

    不创建账号，不根据姓名、手机或 union_id 猜测，也不变更系统角色或受众关系。
    """

    if not identity.corp_id or not identity.user_id:
        raise IdentityMappingError("verified identity is incomplete")

    user_model = get_user_model()
    matches = user_model.objects.filter(
        dingtalk_corp_id=identity.corp_id,
        dingtalk_user_id=identity.user_id,
    )
    if matches.count() != 1:
        raise IdentityMappingError("identity mapping is missing or ambiguous")

    user = matches.get()
    if not user.is_active or user.account_status != AccountStatus.ACTIVE:
        raise IdentityMappingError("mapped account is not active")
    return user
