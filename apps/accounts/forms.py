"""账号与组织表单。"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import AccountStatus, Department
from .roles import DEV_IDENTITIES


class DepartmentAdminForm(forms.ModelForm):
    """阻止后台把部门层级保存为自引用或间接循环。"""

    class Meta:
        model = Department
        fields = "__all__"

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        current = parent
        visited = set()

        while current is not None:
            if self.instance.pk and current.pk == self.instance.pk:
                raise forms.ValidationError("上级部门不能形成循环关系。")
            if current.pk in visited:
                raise forms.ValidationError("上级部门不能形成循环关系。")
            visited.add(current.pk)
            current = current.parent

        return parent


class DevLoginForm(forms.Form):
    """本地模拟登录表单：只能从固定开发身份白名单中选择，不接受任意用户名。"""

    username = forms.ChoiceField(
        label="选择本地开发身份",
        choices=tuple((identity.username, identity.display_name) for identity in DEV_IDENTITIES),
    )


class EmployeeAuthenticationForm(AuthenticationForm):
    """正式员工密码登录表单，复用 Django 校验并附加账户生命周期门禁。"""

    username = forms.CharField(
        label="用户名",
        max_length=150,
        widget=forms.TextInput(attrs={"autofocus": True}),
    )
    password = forms.CharField(label="密码", strip=False, widget=forms.PasswordInput)

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.account_status != AccountStatus.ACTIVE:
            raise forms.ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )
