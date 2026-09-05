"""创建本地模拟登录使用的四个固定开发身份（仅限开发环境）。"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import roles


class Command(BaseCommand):
    help = "创建本地模拟登录的四个固定开发用户（仅 DEBUG=True 且开发登录开关启用时可用）。"

    def handle(self, *args, **options):
        if not (settings.DEBUG and settings.DEV_LOGIN_ENABLED):
            raise CommandError(
                "拒绝执行：create_dev_users 仅允许在 DEBUG=True 且开发登录开关启用时运行，"
                "生产环境已强制关闭模拟登录。"
            )

        # 先同步系统角色，保证开发用户加入的 Group 存在且权限准确。
        call_command("sync_system_roles", verbosity=0)

        # 先整体预检：固定用户名若已被真实用户占用，拒绝覆盖且不做任何写入。
        user_model = get_user_model()
        conflicts = []
        for identity in roles.DEV_IDENTITIES:
            existing = user_model.objects.filter(username=identity.username).first()
            if existing is not None and roles.has_real_identity(existing):
                conflicts.append(identity.username)
        if conflicts:
            raise CommandError(
                "以下固定开发用户名已被具有真实身份特征的用户占用"
                "（可用密码、工号、邮箱、钉钉标识或超级管理员状态），拒绝覆盖：{}。".format(
                    "、".join(sorted(conflicts))
                )
            )

        for identity in roles.DEV_IDENTITIES:
            group = Group.objects.get(name=roles.SYSTEM_ROLE_BY_CODE[identity.role_code].name)
            user, created = user_model.objects.get_or_create(username=identity.username)
            user.display_name = identity.display_name
            user.is_staff = identity.is_staff
            user.is_superuser = False
            user.is_active = True
            if created:
                user.set_unusable_password()
            user.save()
            user.groups.set([group])
            self.stdout.write(
                "{}：{}（staff={}，superuser=否，角色={}）".format(
                    "创建" if created else "更新",
                    user.username,
                    "是" if user.is_staff else "否",
                    group.name,
                )
            )
        self.stdout.write(f"开发用户创建完成，共 {len(roles.DEV_IDENTITIES)} 个固定身份。")
