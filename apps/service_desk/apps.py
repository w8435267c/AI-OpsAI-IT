from django.apps import AppConfig


class ServiceDeskConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.service_desk"
    label = "service_desk"
    verbose_name = "IT 服务入口"
