"""账号和完成动作门槛，不导入模型，允许在 Django 初始化时加载。"""

from django.core.exceptions import PermissionDenied


def valid_account(user):
    return bool(
        user
        and user.is_authenticated
        and user.pk
        and user.is_active
        and user.account_status == "active"
    )


def forbid_finish(workflow_state, user=None):
    raise PermissionDenied("F05A 未开放批准或工作流完成")
