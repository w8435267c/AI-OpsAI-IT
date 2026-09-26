"""账号与组织表单。"""

from django import forms

from .models import Department
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
