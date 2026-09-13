"""账号状态门槛：同时覆盖密码认证和每次请求的会话用户恢复。"""

from django.contrib.auth.backends import ModelBackend

from apps.accounts.models import AccountStatus


class AccountStateBackend(ModelBackend):
    def user_can_authenticate(self, user):
        return super().user_can_authenticate(user) and user.account_status == AccountStatus.ACTIVE
