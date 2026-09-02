from django.apps import AppConfig


class DingtalkConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dingtalk"
    label = "dingtalk"
    verbose_name = "钉钉集成"
