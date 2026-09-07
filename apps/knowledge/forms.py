"""文章 Admin 与受众 Inline 的最终状态校验。"""

from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from .models import Article, ArticleAudience
from .validation_context import joint_validation, pending_article, pending_audience


class JointArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = "__all__"

    def _post_clean(self):
        # 仅延后这个父实例的“旧数据库受众与策略”比较；其他模型校验照常执行。
        with joint_validation(pending_article, self.instance):
            super()._post_clean()


class AudienceInlineForm(forms.ModelForm):
    class Meta:
        model = ArticleAudience
        fields = "__all__"

    def _post_clean(self):
        with joint_validation(pending_audience, self.instance):
            super()._post_clean()


class AudienceInlineFormSet(BaseInlineFormSet):
    allow_add = False
    allow_change = False
    allow_delete = False
    mutable_fields = ("audience_type", "effect", "department", "user_group", "user", "created_by")

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        existing = {str(rule.pk): rule for rule in self.get_queryset()}
        submitted_ids = [str(form.instance.pk) for form in self.initial_forms]
        if set(submitted_ids) != set(existing) or len(submitted_ids) != len(set(submitted_ids)):
            raise ValidationError("受众规则已变化或表单不完整，请重新加载后提交。")
        final = []
        for form in self.forms:
            old = existing.get(str(form.instance.pk))
            deleting = form.data.get(form.add_prefix("DELETE")) in ("on", "true", "1")
            if deleting and not self.allow_delete:
                raise ValidationError("没有删除受众规则的权限。")
            if old is None and not self.allow_add:
                if any(form.data.get(form.add_prefix(name)) for name in self.mutable_fields):
                    raise ValidationError("没有新增受众规则的权限。")
            if old is not None and not self.allow_change:
                for name in self.mutable_fields:
                    key = form.add_prefix(name)
                    value = (
                        getattr(old, name + "_id", None)
                        if name in ("department", "user_group", "user", "created_by")
                        else getattr(old, name)
                    )
                    if key in form.data and str(form.data[key]) != str(value or ""):
                        raise ValidationError("没有修改受众规则的权限。")
            if self.can_delete and self._should_delete_form(form):
                continue
            if old is None and not form.has_changed():
                continue
            rule = form.instance if old is None or self.allow_change else old
            rule.article = self.instance
            with joint_validation(pending_audience, rule):
                rule.full_clean()
            final.append(rule)
        keys = set()
        for rule in final:
            key = self.rule_key(rule)
            if key in keys:
                raise ValidationError("最终受众规则重复，请删除或调整重复项。")
            keys.add(key)
        self._ordered_changes = self.order_changes()

    def order_changes(self):
        # FormSet 缓存中的实例已被绑定表单修改，必须重新读取数据库的原始键。
        original = {rule.pk: self.rule_key(rule) for rule in self.get_queryset().all()}
        deleted = {form.instance.pk for form in self.deleted_forms}
        occupied = {key: pk for pk, key in original.items() if pk not in deleted}
        pending = [
            form
            for form in self.initial_forms
            if form.instance.pk not in deleted and form.has_changed()
        ]
        ordered = []
        while pending:
            for form in pending:
                pk = form.instance.pk
                target = self.rule_key(form.instance)
                if target not in occupied or occupied[target] == pk:
                    occupied.pop(original[pk], None)
                    occupied[target] = pk
                    ordered.append(form)
                    pending.remove(form)
                    break
            else:
                raise ValidationError(
                    "本次修改包含受众规则目标的循环交换，当前暂不支持。"
                    "请取消交换，或联系管理员调整规则。"
                )
        return ordered

    @staticmethod
    def rule_key(rule):
        return (
            rule.audience_type,
            rule.department_id,
            rule.user_group_id,
            rule.user_id,
            rule.effect,
        )

    def save_existing_objects(self, commit=True):
        # 先执行明确授权的删除，再保存修改，允许删除旧规则后在同次请求补入同键规则。
        self.changed_objects = []
        self.deleted_objects = []
        saved = []
        for form in self.initial_forms:
            if form in self.deleted_forms:
                self.deleted_objects.append(form.instance)
                self.delete_existing(form.instance, commit=commit)
        for form in self._ordered_changes:
            self.changed_objects.append((form.instance, form.changed_data))
            saved.append(self.save_existing(form, form.instance, commit=commit))
            if not commit:
                self.saved_forms.append(form)
        return saved
