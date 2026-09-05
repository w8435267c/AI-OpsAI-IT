"""create_dev_users 命令测试：固定开发身份的创建、幂等与安全拒绝。"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group as SystemGroup
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import UserGroup
from apps.accounts.roles import DEV_IDENTITIES, SYSTEM_ROLE_BY_CODE
from apps.knowledge.models import Article, Category, KnowledgeSpace

User = get_user_model()


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class CreateDevUsersTests(TestCase):
    """开关开启时的正常创建路径。"""

    def _make_bare_dev(self, username, display_name):
        """构造仅有开发身份特征、无密码的存量用户，便于叠加各种偏差。"""
        user = User.objects.create(username=username)
        user.set_unusable_password()
        user.display_name = display_name
        user.save()
        return user

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

    def test_existing_matching_dev_user_confirmed_without_writes(self):
        # 完全符合预期的存量开发用户：只做幂等确认，不做任何写入，
        # 尤其不得重置 last_login 等正常运行痕迹。
        call_command("create_dev_users")
        user = User.objects.get(username="dev_employee")
        user.last_login = timezone.now()
        user.save()
        call_command("create_dev_users")
        user.refresh_from_db()
        self.assertEqual(User.objects.count(), 4)
        self.assertIsNotNone(user.last_login)
        self.assertEqual(user.display_name, "本地模拟-普通员工")

    def test_existing_deviant_bare_user_refused(self):
        # 空 display_name、无组的存量用户是"疑似漂移"，必须整体拒绝并人工处理，
        # 不得静默校准（禁止自动修复：不补 display_name、不补组）。
        User.objects.create(username="dev_employee")
        with self.assertRaises(CommandError) as ctx:
            call_command("create_dev_users")
        self.assertIn("dev_employee", str(ctx.exception))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(SystemGroup.objects.count(), 0)

    def test_existing_wrong_group_refused(self):
        user = self._make_bare_dev("dev_editor", "本地模拟-知识编辑员")
        user.groups.add(SystemGroup.objects.create(name="知识审核员"))
        with self.assertRaises(CommandError):
            call_command("create_dev_users")
        self.assertEqual(SystemGroup.objects.count(), 1)

    def test_existing_extra_group_refused(self):
        user = self._make_bare_dev("dev_editor", "本地模拟-知识编辑员")
        user.groups.add(
            SystemGroup.objects.create(name="知识编辑员"),
            SystemGroup.objects.create(name="多余组"),
        )
        with self.assertRaises(CommandError):
            call_command("create_dev_users")

    def test_existing_direct_permission_refused(self):
        user = self._make_bare_dev("dev_reviewer", "本地模拟-知识审核员")
        perm = Permission.objects.get(content_type__app_label="knowledge", codename="view_article")
        user.user_permissions.add(perm)
        with self.assertRaises(CommandError):
            call_command("create_dev_users")
        self.assertTrue(user.user_permissions.filter(pk=perm.pk).exists())

    def test_existing_inactive_refused(self):
        user = self._make_bare_dev("dev_employee", "本地模拟-普通员工")
        user.is_active = False
        user.save()
        with self.assertRaises(CommandError):
            call_command("create_dev_users")
        self.assertEqual(User.objects.count(), 1)

    def test_existing_departed_refused(self):
        user = self._make_bare_dev("dev_employee", "本地模拟-普通员工")
        user.account_status = "departed"
        user.save()
        with self.assertRaises(CommandError):
            call_command("create_dev_users")

    def test_existing_staff_drift_refused(self):
        user = self._make_bare_dev("dev_employee", "本地模拟-普通员工")
        user.is_staff = True
        user.save()
        with self.assertRaises(CommandError):
            call_command("create_dev_users")

    def test_existing_business_association_refused(self):
        # 开发用户名下已存在业务数据（部门/内容用户组/文章/版本/审核记录），
        # 说明该用户已被当作正式用户使用，必须拒绝并人工处理。
        user = self._make_bare_dev("dev_employee", "本地模拟-普通员工")
        space = KnowledgeSpace.objects.create(
            name="临时空间",
            code="TEMP-SPACE",
            space_type=KnowledgeSpace._meta.get_field("space_type").choices[0][0],
            owner=user,
        )
        category = Category.objects.create(name="临时分类", code="TEMP-CAT", space=space)
        Article.objects.create(
            kb_no="KB-900001",
            title="临时文章",
            space=space,
            category=category,
            article_type=Article._meta.get_field("article_type").choices[0][0],
            audience_policy=Article._meta.get_field("audience_policy").choices[0][0],
            owner=user,
            created_by=user,
            updated_by=user,
            review_due_at=timezone.now() + timedelta(days=30),
        )
        with self.assertRaises(CommandError) as ctx:
            call_command("create_dev_users")
        self.assertIn("dev_employee", str(ctx.exception))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(SystemGroup.objects.count(), 0)

    def test_user_creation_failure_rolls_back_groups_and_users(self):
        # 在第三个身份写入时注入故障：外层事务必须整体回滚，
        # 不允许出现"Group 已创建、用户只建了一半"的部分写入。
        real_get = SystemGroup.objects.get
        calls = {"n": 0}

        def failing_get(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 3:  # 第三个身份（dev_reviewer）写入时注入故障
                raise RuntimeError("注入故障：开发用户创建失败")
            return real_get(*args, **kwargs)

        with mock.patch.object(SystemGroup.objects, "get", failing_get):
            with self.assertRaises(CommandError):
                call_command("create_dev_users")
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(SystemGroup.objects.count(), 0)

    def test_bare_blank_password_user_refused(self):
        User.objects.create(username="dev_employee")
        with self.assertRaises(CommandError) as ctx:
            call_command("create_dev_users")
        self.assertIn("dev_employee", str(ctx.exception))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(SystemGroup.objects.count(), 0)

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
        self.assertEqual(SystemGroup.objects.count(), 0)

    def test_conflict_real_identity_refused(self):
        User.objects.create(username="dev_reviewer", employee_no="E-100")
        with self.assertRaises(CommandError):
            call_command("create_dev_users")
        user = User.objects.get(username="dev_reviewer")
        self.assertEqual(user.employee_no, "E-100")
        self.assertEqual(SystemGroup.objects.count(), 0)

    def test_conflict_superuser_refused(self):
        User.objects.create_superuser(username="dev_employee", password="admin-pass")
        with self.assertRaises(CommandError):
            call_command("create_dev_users")
        self.assertTrue(User.objects.get(username="dev_employee").is_superuser)
        self.assertEqual(SystemGroup.objects.count(), 0)


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
