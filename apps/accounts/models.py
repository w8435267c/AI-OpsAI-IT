from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """项目自定义用户模型，正式业务字段将在accounts模型阶段补充。"""

    class Meta:
        db_table = "accounts_user"
        verbose_name = "用户"
        verbose_name_plural = "用户"
