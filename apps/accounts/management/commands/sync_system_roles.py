"""同步系统操作角色：创建/取得四个 Django Group 并把权限校准为代码定义的集合。"""

from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts import roles


def _resolve_permissions(role):
    """把角色的权限字符串解析为 Permission 对象，返回 (已解析列表, 缺失列表)。"""
    resolved = []
    missing = []
    for codename in role.permissions:
        app_label, _, perm_codename = codename.partition(".")
        try:
            lookup = {"content_type__app_label": app_label, "codename": perm_codename}
            if codename == roles.WAGTAIL_ACCESS_PERMISSION:
                lookup["content_type__model"] = "admin"
            permission = Permission.objects.get(**lookup)
        except Permission.DoesNotExist:
            missing.append(codename)
        else:
            resolved.append(permission)
    return resolved, missing


class Command(BaseCommand):
    help = "创建或取得四个系统操作角色，并将其权限同步为代码定义的准确集合。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile",
            choices=roles.ROLE_PROFILES,
            default="default",
            help="显式角色配置档；默认保持原权限，wagtail-poc 仅增加后台入口。",
        )

    def handle(self, *args, **options):
        profile = options["profile"]
        try:
            selected_roles = roles.get_system_roles(profile)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        missing_apps = [
            name for name in roles.PROFILE_REQUIRED_APPS[profile] if not apps.is_installed(name)
        ]
        if missing_apps:
            raise CommandError("配置档所需 App 未启用，未做任何写入：" + "、".join(missing_apps))
        # 先整体解析：任何权限缺失都直接报错停止，不做部分写入。
        planned = []
        all_missing = []
        for role in selected_roles:
            resolved, missing = _resolve_permissions(role)
            planned.append((role, resolved))
            all_missing.extend(missing)
        if all_missing:
            raise CommandError(
                "存在尚未定义的权限，已停止且未做任何写入：{}。".format(
                    "、".join(sorted(all_missing))
                )
            )

        # 写入阶段整体事务：任意一个角色同步失败，前面角色的创建与
        # 权限修改全部回滚，保证一次同步要么全成、要么全无部分写入。
        try:
            with transaction.atomic():
                for role, resolved in planned:
                    group, created = Group.objects.get_or_create(name=role.name)
                    group.permissions.set(resolved)
                    self.stdout.write(
                        "{}：{}（权限 {} 项）".format(
                            "创建" if created else "同步", group.name, len(resolved)
                        )
                    )
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"系统角色同步失败，已整体回滚且未留下部分写入：{exc}。") from exc
        self.stdout.write(f"系统角色同步完成，共 {len(planned)} 个角色。")
