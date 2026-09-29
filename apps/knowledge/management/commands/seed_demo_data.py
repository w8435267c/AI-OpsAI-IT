"""创建 Task 9 所需的最小、幂等且不含文章的演示数据。"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import (
    Department,
    UserDepartment,
    UserGroup,
    UserGroupMembership,
)
from apps.accounts.roles import DEV_IDENTITIES, dev_user_deviation
from apps.knowledge.models import AudiencePolicy, Category, KnowledgeSpace, SpaceType

DEMO_DEPARTMENT_ID = "demo-task9-support"
DEMO_DEPARTMENT_NAME = "演示 IT 支持部"
DEMO_GROUP_NAME = "演示知识受众组"
DEMO_GROUP_DESCRIPTION = "Task 9 最小演示数据：用于内容用户组受众验证。"
DEMO_SPACE_CODE = "demo-it"
DEMO_SPACE_NAME = "演示 IT 知识空间"
DEMO_SPACE_DESCRIPTION = "Task 9 最小演示空间，仅用于开发与验收。"
DEMO_CATEGORY_CODE = "demo-troubleshooting"
DEMO_CATEGORY_NAME = "演示基础排障"


class Command(BaseCommand):
    help = "创建不依赖正式 KB 编号服务的最小演示数据；运行前须先执行 create_dev_users。"

    def handle(self, *args, **options):
        if not (settings.DEBUG and settings.DEV_LOGIN_ENABLED):
            raise CommandError(
                "拒绝执行：seed_demo_data 仅允许在 DEBUG=True 且开发登录开关启用时运行。"
            )

        stats = {"created": 0, "existing": 0}
        try:
            with transaction.atomic():
                users = self._load_dev_users()
                employee = users["dev_employee"]
                admin_user = users["dev_knowledge_admin"]

                department = self._ensure(
                    Department,
                    lookup={"dingtalk_dept_id": DEMO_DEPARTMENT_ID},
                    expected={
                        "name": DEMO_DEPARTMENT_NAME,
                        "parent": None,
                        "is_active": True,
                        "last_sync_at": None,
                    },
                    label=f"Department[{DEMO_DEPARTMENT_ID}]",
                    stats=stats,
                )
                content_group = self._ensure(
                    UserGroup,
                    lookup={"name": DEMO_GROUP_NAME},
                    expected={
                        "description": DEMO_GROUP_DESCRIPTION,
                        "is_active": True,
                    },
                    label=f"UserGroup[{DEMO_GROUP_NAME}]",
                    stats=stats,
                )
                space = self._ensure(
                    KnowledgeSpace,
                    lookup={"code": DEMO_SPACE_CODE},
                    expected={
                        "name": DEMO_SPACE_NAME,
                        "description": DEMO_SPACE_DESCRIPTION,
                        "space_type": SpaceType.EMPLOYEE,
                        "owner": admin_user,
                        "default_audience_policy": AudiencePolicy.RESTRICTED,
                        "is_active": True,
                    },
                    label=f"KnowledgeSpace[{DEMO_SPACE_CODE}]",
                    stats=stats,
                )
                self._ensure(
                    Category,
                    lookup={"space": space, "code": DEMO_CATEGORY_CODE},
                    expected={
                        "parent": None,
                        "name": DEMO_CATEGORY_NAME,
                        "icon": "",
                        "sort_order": 0,
                        "is_active": True,
                    },
                    label=f"Category[{DEMO_SPACE_CODE}/{DEMO_CATEGORY_CODE}]",
                    stats=stats,
                )
                self._ensure(
                    UserDepartment,
                    lookup={"user": employee, "department": department},
                    expected={
                        "is_primary": True,
                        "effective_at": None,
                        "expired_at": None,
                    },
                    label="UserDepartment[dev_employee/demo-task9-support]",
                    stats=stats,
                )
                self._ensure(
                    UserGroupMembership,
                    lookup={"user": employee, "user_group": content_group},
                    expected={},
                    label="UserGroupMembership[dev_employee/演示知识受众组]",
                    stats=stats,
                )
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(
                "seed_demo_data 执行失败，已整体回滚且未留下部分演示数据；"
                f"created: 0; existing: {stats['existing']}; conflict: 1。"
            ) from exc

        self.stdout.write("Article demo skipped: formal KB number service is not available")
        self.stdout.write(
            "seed_demo_data 完成："
            f"created: {stats['created']}; existing: {stats['existing']}; conflict: 0"
        )

    @staticmethod
    def _load_dev_users():
        user_model = get_user_model()
        users = {}
        missing = []
        conflicts = []

        for identity in DEV_IDENTITIES:
            user = user_model.objects.filter(username=identity.username).first()
            if user is None:
                missing.append(identity.username)
                continue
            reason = dev_user_deviation(user, identity)
            if reason:
                conflicts.append(f"{identity.username}（{reason}）")
                continue
            users[identity.username] = user

        if missing or conflicts:
            details = []
            if missing:
                details.append("缺少固定开发身份：" + "、".join(missing))
            if conflicts:
                details.append("开发身份不符合预期：" + "、".join(conflicts))
            raise CommandError(
                "；".join(details) + "。请先安全执行 create_dev_users；本次未做任何写入。"
            )
        return users

    @staticmethod
    def _ensure(model, *, lookup, expected, label, stats):
        existing = model.objects.filter(**lookup).first()
        if existing is not None:
            mismatched = [
                field_name
                for field_name, expected_value in expected.items()
                if getattr(existing, field_name) != expected_value
            ]
            if mismatched:
                raise CommandError(
                    f"演示数据冲突：{label} 已存在但字段不一致："
                    f"{', '.join(mismatched)}；已整体回滚；"
                    f"created: 0; existing: {stats['existing']}; conflict: 1。"
                )
            stats["existing"] += 1
            return existing

        instance = model(**lookup, **expected)
        instance.full_clean()
        instance.save(force_insert=True)
        stats["created"] += 1
        return instance
