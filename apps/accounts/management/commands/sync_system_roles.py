"""同步系统操作角色：创建/取得四个 Django Group 并把权限校准为代码定义的集合。"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import roles


def _resolve_permissions(role):
    """把角色的权限字符串解析为 Permission 对象，返回 (已解析列表, 缺失列表)。"""
    resolved = []
    missing = []
    for codename in role.permissions:
        app_label, _, perm_codename = codename.partition(".")
        try:
            permission = Permission.objects.get(
                content_type__app_label=app_label, codename=perm_codename
            )
        except Permission.DoesNotExist:
            missing.append(codename)
        else:
            resolved.append(permission)
    return resolved, missing


class Command(BaseCommand):
    help = "创建或取得四个系统操作角色，并将其权限同步为代码定义的准确集合。"

    def handle(self, *args, **options):
        # 先整体解析：任何权限缺失都直接报错停止，不做部分写入。
        planned = []
        all_missing = []
        for role in roles.SYSTEM_ROLES:
            resolved, missing = _resolve_permissions(role)
            planned.append((role, resolved))
            all_missing.extend(missing)
        if all_missing:
            raise CommandError(
                "存在尚未定义的权限，已停止且未做任何写入：{}。".format(
                    "、".join(sorted(all_missing))
                )
            )

        for role, resolved in planned:
            group, created = Group.objects.get_or_create(name=role.name)
            group.permissions.set(resolved)
            self.stdout.write(
                "{}：{}（权限 {} 项）".format(
                    "创建" if created else "同步", group.name, len(resolved)
                )
            )
        self.stdout.write(f"系统角色同步完成，共 {len(planned)} 个角色。")
