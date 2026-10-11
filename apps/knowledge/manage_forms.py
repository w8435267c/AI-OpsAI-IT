"""正式知识管理区表单。"""

from __future__ import annotations

import json

from django import forms
from django.forms.fields import InvalidJSONInput

from apps.accounts.models import User

from .manage_readers import get_manage_article_create_options
from .models import ArticleType, AudiencePolicy, Category, KnowledgeSpace


class JSONObjectField(forms.JSONField):
    """只接受顶层对象，并以可读且保留中文的格式展示。"""

    default_error_messages = {
        **forms.JSONField.default_error_messages,
        "invalid": "请输入有效的 JSON。",
    }

    def prepare_value(self, value):
        if isinstance(value, InvalidJSONInput):
            return value
        if value is None or value == "":
            return ""
        return json.dumps(value, ensure_ascii=False, indent=2)

    def clean(self, value):
        if value in self.empty_values:
            return {}
        value = super().clean(value)
        if not isinstance(value, dict):
            raise forms.ValidationError("适用范围必须是 JSON 对象，例如 {}。")
        return value


class StrictPositiveIntegerField(forms.Field):
    """只接受 JSON 解码后的正整数，不接受 bool、浮点数或数字字符串。"""

    default_error_messages = {
        "required": "此字段为必填项。",
        "invalid": "请输入正整数。",
    }

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if type(value) is not int or value < 1:
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
        return value


class ArticleAutosaveIdentityForm(forms.Form):
    """autosave 请求中的草稿身份与 CAS token。"""

    draft_id = forms.UUIDField()
    expected_lock_version = StrictPositiveIntegerField()


class ArticleCreateForm(forms.Form):
    """Article 与首个 DRAFT 创建输入白名单。"""

    space = forms.ModelChoiceField(
        label="知识空间",
        queryset=KnowledgeSpace.objects.none(),
    )
    category = forms.ModelChoiceField(
        label="分类",
        queryset=Category.objects.none(),
    )
    article_type = forms.ChoiceField(
        label="文章类型",
        choices=ArticleType.choices,
    )
    title = forms.CharField(label="标题", max_length=60)
    summary = forms.CharField(
        label="摘要",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    applicable_scope = JSONObjectField(
        label="适用范围（高级设置）",
        required=False,
        initial=dict,
        widget=forms.Textarea(attrs={"rows": 7}),
        help_text="当前版本暂使用 JSON 对象保存适用范围。没有特殊限制时可填写 {}。",
    )
    body_text = forms.CharField(
        label="正文",
        widget=forms.Textarea(attrs={"rows": 16}),
    )
    change_summary = forms.CharField(
        label="版本说明",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    audience_policy = forms.ChoiceField(
        label="内容受众策略",
        required=False,
        choices=(("", "使用知识空间默认策略"), *AudiencePolicy.choices),
    )
    effective_at = forms.DateTimeField(
        label="生效时间",
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    review_due_at = forms.DateTimeField(
        label="复审截止时间",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    owner = forms.ModelChoiceField(
        label="知识负责人",
        queryset=User.objects.none(),
        required=False,
        help_text="不选择时由当前知识管理员担任负责人。",
    )

    def __init__(self, *, actor, **kwargs):
        super().__init__(**kwargs)
        options = get_manage_article_create_options(actor=actor)
        self.fields["space"].queryset = options.spaces
        self.fields["category"].queryset = options.categories
        if options.is_admin:
            self.fields["owner"].queryset = options.owners
        else:
            self.fields.pop("owner")

    def clean_audience_policy(self):
        return self.cleaned_data.get("audience_policy") or None

    def clean(self):
        cleaned_data = super().clean()
        space = cleaned_data.get("space")
        category = cleaned_data.get("category")
        if space is not None and category is not None and category.space_id != space.pk:
            self.add_error("category", "所选分类不属于该知识空间")
        return cleaned_data


class ArticleDraftForm(forms.Form):
    """working DRAFT 可编辑内容的严格白名单。"""

    title = forms.CharField(label="标题", max_length=60, strip=False)
    summary = forms.CharField(
        label="摘要",
        max_length=500,
        strip=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    applicable_scope = JSONObjectField(
        label="适用范围（高级设置）",
        required=False,
        initial=dict,
        widget=forms.Textarea(attrs={"rows": 7}),
        help_text="当前版本暂使用 JSON 对象保存适用范围。没有特殊限制时可填写 {}。",
    )
    body_text = forms.CharField(
        label="正文",
        strip=False,
        widget=forms.Textarea(attrs={"rows": 18}),
    )
    change_summary = forms.CharField(
        label="版本说明",
        max_length=500,
        strip=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def _clean_nonblank_text(self, field_name: str, label: str) -> str:
        value = self.cleaned_data[field_name]
        if not value.strip():
            raise forms.ValidationError(f"{label}不能为空。")
        return value

    def clean_title(self):
        return self._clean_nonblank_text("title", "标题")

    def clean_summary(self):
        return self._clean_nonblank_text("summary", "摘要")

    def clean_body_text(self):
        value = self.cleaned_data["body_text"]
        if not value.strip():
            raise forms.ValidationError("正文不能为空。")
        return value

    def clean_change_summary(self):
        return self._clean_nonblank_text("change_summary", "版本说明")
