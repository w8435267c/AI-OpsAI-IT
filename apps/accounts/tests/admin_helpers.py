"""Admin 保护测试共享助手（不含测试用例，pytest 不收集本模块）。"""

from django import forms as djforms
from django.forms.models import model_to_dict
from django.test import RequestFactory


def build_change_post_data(model_admin, request_user, obj, **overrides):
    """基于 admin 修改表单的真实字段构造 POST 数据（保持其他字段原值，仅改 overrides）。"""
    rf = RequestFactory()
    req = rf.get("/admin/dummy/")
    req.user = request_user
    form_cls = model_admin.get_form(req, obj=obj)
    raw = model_to_dict(obj)
    data = {}
    for name, field in form_cls.base_fields.items():
        if name in overrides:
            continue
        val = raw.get(name)
        if isinstance(field, djforms.ModelMultipleChoiceField):
            data[name] = [o.pk for o in val] if val else []
        elif isinstance(field, djforms.ModelChoiceField):
            if val is None:
                data[name] = ""
            elif hasattr(val, "pk"):
                data[name] = val.pk
            else:
                data[name] = val  # 已是主键值（UUID/字符串）
        elif isinstance(field, djforms.SplitDateTimeField):
            data[name + "_0"] = val.strftime("%Y-%m-%d") if val else ""
            data[name + "_1"] = val.strftime("%H:%M:%S") if val else ""
        else:
            data[name] = val if val is not None else ""
    data.update(overrides)
    return data
