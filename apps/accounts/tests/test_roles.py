"""系统操作角色定义与 sync_system_roles 命令测试。"""

from unittest import mock

from django.contrib.auth.models import Group as SystemGroup
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.models import UserGroup
from apps.accounts.roles import (
    ROLE_EDITOR,
    ROLE_EMPLOYEE,
    ROLE_KNOWLEDGE_ADMIN,
    ROLE_REVIEWER,
    SYSTEM_ROLES,
    SystemRole,
)


def _permission_codenames(permissions) -> set[str]:
    return {f"{perm.content_type.app_label}.{perm.codename}" for perm in permissions}


class SystemRoleDefinitionTests(TestCase):
    """角色定义本身：名称、代码与最小权限原则。"""

    def test_exactly_four_roles_with_prd_names(self):
        self.assertEqual(
            [role.name for role in SYSTEM_ROLES],
            ["普通员工", "知识编辑员", "知识审核员", "知识库管理员"],
        )

    def test_role_codes_stable_and_unique(self):
        codes = [role.code for role in SYSTEM_ROLES]
        self.assertEqual(codes, [ROLE_EMPLOYEE, ROLE_EDITOR, ROLE_REVIEWER, ROLE_KNOWLEDGE_ADMIN])
        self.assertEqual(len(codes), len(set(codes)))

    def test_no_delete_permissions_in_any_role(self):
        for role in SYSTEM_ROLES:
            for perm in role.permissions:
                self.assertNotIn(".delete_", perm, f"角色 {role.name} 不应包含删除权限：{perm}")

    def test_employee_has_no_model_permissions(self):
        role = next(r for r in SYSTEM_ROLES if r.code == ROLE_EMPLOYEE)
        self.assertEqual(role.permissions, ())

    def test_permission_strings_well_formed(self):
        for role in SYSTEM_ROLES:
            for perm in role.permissions:
                app_label, _, codename = perm.partition(".")
                self.assertTrue(app_label, f"权限缺少 app_label：{perm}")
                self.assertTrue(codename, f"权限缺少 codename：{perm}")


class SyncSystemRolesCommandTests(TestCase):
    """sync_system_roles 命令：创建、幂等、漂移纠正与失败保护。"""

    def test_creates_four_system_groups(self):
        call_command("sync_system_roles")
        names = set(SystemGroup.objects.values_list("name", flat=True))
        self.assertEqual(names, {role.name for role in SYSTEM_ROLES})

    def test_group_permissions_match_definition_exactly(self):
        call_command("sync_system_roles")
        for role in SYSTEM_ROLES:
            group = SystemGroup.objects.get(name=role.name)
            self.assertEqual(_permission_codenames(group.permissions.all()), set(role.permissions))

    def test_employee_group_has_no_permissions(self):
        call_command("sync_system_roles")
        group = SystemGroup.objects.get(name="普通员工")
        self.assertEqual(group.permissions.count(), 0)

    def test_no_group_granted_delete_permissions(self):
        call_command("sync_system_roles")
        for group in SystemGroup.objects.all():
            for perm in group.permissions.all():
                self.assertNotIn("delete", perm.codename)

    def test_repeated_execution_is_idempotent(self):
        call_command("sync_system_roles")
        before = {
            group.name: _permission_codenames(group.permissions.all())
            for group in SystemGroup.objects.all()
        }
        call_command("sync_system_roles")
        after = {
            group.name: _permission_codenames(group.permissions.all())
            for group in SystemGroup.objects.all()
        }
        self.assertEqual(before, after)
        self.assertEqual(SystemGroup.objects.count(), 4)

    def test_drift_is_corrected(self):
        call_command("sync_system_roles")
        group = SystemGroup.objects.get(name="知识编辑员")
        bogus = Permission.objects.get(content_type__app_label="auth", codename="add_group")
        group.permissions.add(bogus)
        removed = group.permissions.get(codename="add_article")
        group.permissions.remove(removed)

        call_command("sync_system_roles")

        group.refresh_from_db()
        expected = next(role for role in SYSTEM_ROLES if role.code == ROLE_EDITOR)
        self.assertEqual(_permission_codenames(group.permissions.all()), set(expected.permissions))

    def test_unrelated_group_untouched(self):
        other = SystemGroup.objects.create(name="人工维护的测试组")
        perms = list(Permission.objects.filter(content_type__app_label="auth")[:2])
        other.permissions.add(*perms)

        call_command("sync_system_roles")

        other.refresh_from_db()
        self.assertTrue(SystemGroup.objects.filter(name="人工维护的测试组").exists())
        self.assertEqual(
            _permission_codenames(other.permissions.all()),
            _permission_codenames(perms),
        )

    def test_content_user_group_not_used_as_system_role(self):
        UserGroup.objects.create(name="内容用户组示例")
        call_command("sync_system_roles")
        self.assertEqual(UserGroup.objects.count(), 1)
        self.assertFalse(SystemGroup.objects.filter(name="内容用户组示例").exists())

    def test_missing_permission_fails_without_writing(self):
        broken = (
            SystemRole(
                code="broken",
                name="异常角色",
                permissions=("knowledge.add_article", "knowledge.no_such_perm"),
            ),
        )
        with mock.patch("apps.accounts.roles.SYSTEM_ROLES", broken):
            with self.assertRaises(CommandError) as ctx:
                call_command("sync_system_roles")
        self.assertIn("no_such_perm", str(ctx.exception))
        self.assertEqual(SystemGroup.objects.count(), 0)
