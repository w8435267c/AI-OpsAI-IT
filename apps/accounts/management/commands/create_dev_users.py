"""创建本地模拟登录使用的四个固定开发身份（仅限开发环境）。"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.accounts import roles


def _find_business_association(user) -> str | None:
    """检查开发用户是否已与任何业务数据关联；有关联即不得视为命令自身产物。"""
    from apps.accounts.models import UserDepartment, UserGroupMembership
    from apps.knowledge.models import Article, ArticleVersion, ReviewRecord

    if UserDepartment.objects.filter(user=user).exists():
        return "存在部门关系"
    if UserGroupMembership.objects.filter(user=user).exists():
        return "存在内容用户组成员关系"
    if Article.objects.filter(Q(owner=user) | Q(created_by=user) | Q(updated_by=user)).exists():
        return "存在知识文章业务关联"
    if ArticleVersion.objects.filter(Q(created_by=user) | Q(submitted_by=user)).exists():
        return "存在文章版本业务关联"
    if ReviewRecord.objects.filter(reviewer=user).exists():
        return "存在审核记录业务关联"
    return None


class Command(BaseCommand):
    help = "创建本地模拟登录的四个固定开发用户（仅 DEBUG=True 且开发登录开关启用时可用）。"

    def handle(self, *args, **options):
        if not (settings.DEBUG and settings.DEV_LOGIN_ENABLED):
            raise CommandError(
                "拒绝执行：create_dev_users 仅允许在 DEBUG=True 且开发登录开关启用时运行，"
                "生产环境已强制关闭模拟登录。"
            )

        user_model = get_user_model()

        # 第一步：纯读取整体预检，零写入。只有完全符合预期的开发用户
        # 才会被视为命令自身产物；任何偏差（真实身份特征、异常组、
        # 直接权限、禁用/离职状态、业务数据关联等）都必须整体拒绝
        # 并人工处理，绝不静默修复（不重新激活、不清理组或权限、
        # 不覆盖身份字段），避免"角色已写入后才发现用户名碰撞"。
        conflicts = []
        for identity in roles.DEV_IDENTITIES:
            existing = user_model.objects.filter(username=identity.username).first()
            if existing is None:
                continue
            reason = roles.dev_user_deviation(existing, identity) or _find_business_association(
                existing
            )
            if reason:
                conflicts.append(f"{identity.username}（{reason}）")
        if conflicts:
            raise CommandError(
                "以下固定开发用户名与预期不符或已有关联数据，拒绝覆盖，"
                "请人工确认后再执行；本次未做任何写入：{}。".format("、".join(conflicts))
            )

        # 第二步：角色同步与四个开发用户处于同一外层事务；任意一步失败，
        # Group 与 User 的全部修改整体回滚。已存在的完全符合预期的开发
        # 用户只做幂等确认，不做任何写入（不重置 last_login 等运行痕迹）。
        try:
            with transaction.atomic():
                call_command("sync_system_roles", verbosity=0)
                for identity in roles.DEV_IDENTITIES:
                    group = Group.objects.get(
                        name=roles.SYSTEM_ROLE_BY_CODE[identity.role_code].name
                    )
                    user, created = user_model.objects.get_or_create(username=identity.username)
                    if created:
                        user.display_name = identity.display_name
                        user.is_staff = identity.is_staff
                        user.is_superuser = False
                        user.is_active = True
                        user.set_unusable_password()
                        user.save()
                        user.groups.set([group])
                        action = "创建"
                    else:
                        # 预检已确认完全符合预期：保持幂等，不做任何修改。
                        action = "确认"
                    self.stdout.write(
                        "{}：{}（staff={}，superuser=否，角色={}）".format(
                            action,
                            user.username,
                            "是" if user.is_staff else "否",
                            group.name,
                        )
                    )
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"开发用户创建失败，已整体回滚且未留下部分写入：{exc}。") from exc
        self.stdout.write(f"开发用户创建完成，共 {len(roles.DEV_IDENTITIES)} 个固定身份。")
