"""账号与组织表单。"""

from django import forms

from .roles import DEV_IDENTITIES


class DevLoginForm(forms.Form):
    """本地模拟登录表单：只能从固定开发身份白名单中选择，不接受任意用户名。"""

    username = forms.ChoiceField(
        label="选择本地开发身份",
        choices=tuple((identity.username, identity.display_name) for identity in DEV_IDENTITIES),
    )
