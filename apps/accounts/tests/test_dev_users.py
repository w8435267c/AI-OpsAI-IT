"""create_dev_users 命令测试：固定开发身份的创建、幂等与安全拒绝。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group as SystemGroup
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import UserGroup
from apps.accounts.roles import DEV_IDENTITIES, SYSTEM_ROLE_BY_CODE
from apps.knowledge.models import Article

User = get_user_model()


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class CreateDevUsersTests(TestCase):
    """开关开启时的正常创建路径。"""

    def test_creates_four_fixed_users(self):
        call_command("create_dev_users")
        usernames = set(User.objects.values_list("username", flat=True))
        self.assertEqual(usernames, {identity.username for identity in DEV_IDENTITIES})

    def test_each_user_in_exactly_one_correct_group(self):
        call_command("create_dev_users")
        for identity in DEV_IDENTITIES:
            user = User.objects.get(username=identity.username)
            group = SystemGroup.objects.get(name=SYSTEM_ROLE_BY_CODE[identity.role_code].name)
            self.assertEqual(list(user.groups.all()), [group])

    def test_passwords_unusable(self):
        call_command("create_dev_users")
        for identity in DEV_IDENTITIES:
            user = User.objects.get(username=identity.username)
            self.assertFalse(user.has_usable_password())
            self.assertFalse(user.check_password(""))

    def test_no_superuser_created(self):
        call_command("create_dev_users")
        self.assertEqual(User.objects.filter(is_superuser=True).count(), 0)

    def test_staff_only_knowledge_admin(self):
        call_command("create_dev_users")
        for identity in DEV_IDENTITIES:
            user = User.objects.get(username=identity.username)
            self.assertEqual(user.is_staff, identity.is_staff)
        self.assertTrue(User.objects.get(username="dev_knowledge_admin").is_staff)

    def test_display_names_match_identities(self):
        call_command("create_dev_users")
        for identity in DEV_IDENTITIES:
            user = User.objects.get(username=identity.username)
            self.assertEqual(user.display_name, identity.display_name)

    def test_no_real_identity_fields_set(self):
        call_command("create_dev_users")
        for identity in DEV_IDENTITIES:
            user = User.objects.get(username=identity.username)
            self.assertEqual(user.email, "")
            self.assertIsNone(user.employee_no)
            self.assertIsNone(user.dingtalk_corp_id)
            self.assertIsNone(user.dingtalk_user_id)
            self.assertIsNone(user.dingtalk_union_id)

    def test_repeated_execution_is_idempotent(self):
        call_command("create_dev_users")
        first_ids = set(User.objects.values_list("id", flat=True))
        call_command("create_dev_users")
        self.assertEqual(User.objects.count(), 4)
        self.assertEqual(set(User.objects.values_list("id", flat=True)), first_ids)

    def test_existing_bare_dev_user_adopted_not_duplicated(self):
        # 模拟上一次命令运行的产物：无密码、无任何真实身份特征的开发用户。
        # 注意：直接 create() 的用户 password 为空字符串，按 Django 语义
        # 属于"可用密码"，会被保守地拒绝覆盖（见 test_conflict_usable_password_refused）。
        previous = User.objects.create(username="dev_employee")
        previous.set_unusable_password()
        previous.save()
        call_command("create_dev_users")
        self.assertEqual(User.objects.filter(username="dev_employee").count(), 1)
        user = User.objects.get(username="dev_employee")
        self.assertEqual(user.display_name, "本地模拟-普通员工")
        self.assertFalse(user.has_usable_password())

    def test_bare_blank_password_user_refused(self):
        User.objects.create(username="dev_employee")
        with self.assertRaises(CommandError) as ctx:
            call_command("create_dev_users")
        self.assertIn("dev_employee", str(ctx.exception))
        self.assertEqual(User.objects.count(), 1)

    def test_no_knowledge_demo_data_created(self):
        call_command("create_dev_users")
        self.assertEqual(Article.objects.count(), 0)

    def test_content_user_group_untouched(self):
        call_command("create_dev_users")
        self.assertEqual(UserGroup.objects.count(), 0)

    def test_conflict_usable_password_refused_without_writes(self):
        User.objects.create_user(username="dev_editor", password="secret-pass")
        with self.assertRaises(CommandError) as ctx:
            call_command("create_dev_users")
        self.assertIn("dev_editor", str(ctx.exception))
        self.assertEqual(User.objects.count(), 1)

    def test_conflict_real_identity_refused(self):
        User.objects.create(username="dev_reviewer", employee_no="E-100")
        with self.assertRaises(CommandError):
            call_command("create_dev_users")
        user = User.objects.get(username="dev_reviewer")
        self.assertEqual(user.employee_no, "E-100")

    def test_conflict_superuser_refused(self):
        User.objects.create_superuser(username="dev_employee", password="admin-pass")
        with self.assertRaises(CommandError):
            call_command("create_dev_users")
        self.assertTrue(User.objects.get(username="dev_employee").is_superuser)


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=False)
class CreateDevUsersSwitchOffTests(TestCase):
    """开关关闭时必须拒绝执行。"""

    def test_refused_when_switch_disabled(self):
        with self.assertRaises(CommandError):
            call_command("create_dev_users")
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(SystemGroup.objects.count(), 0)


@override_settings(DEBUG=False, DEV_LOGIN_ENABLED=True)
class CreateDevUsersDebugFalseTests(TestCase):
    """DEBUG=False 时即使开关开启也必须拒绝执行。"""

    def test_refused_when_debug_false(self):
        with self.assertRaises(CommandError):
            call_command("create_dev_users")
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(SystemGroup.objects.count(), 0)
