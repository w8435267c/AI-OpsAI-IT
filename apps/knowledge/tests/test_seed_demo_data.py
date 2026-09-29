"""Task 9B-1：最小演示数据命令的幂等、冲突与安全边界。"""

from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import (
    Department,
    UserDepartment,
    UserGroup,
    UserGroupMembership,
)
from apps.knowledge.models import (
    Article,
    ArticleAudience,
    ArticleVersion,
    AudiencePolicy,
    Category,
    KnowledgeSpace,
    ReviewRecord,
    SpaceType,
)

User = get_user_model()

DEMO_DEPARTMENT_ID = "demo-task9-support"
DEMO_DEPARTMENT_NAME = "演示 IT 支持部"
DEMO_GROUP_NAME = "演示知识受众组"
DEMO_GROUP_DESCRIPTION = "Task 9 最小演示数据：用于内容用户组受众验证。"
DEMO_SPACE_CODE = "demo-it"
DEMO_SPACE_NAME = "演示 IT 知识空间"
DEMO_SPACE_DESCRIPTION = "Task 9 最小演示空间，仅用于开发与验收。"
DEMO_CATEGORY_CODE = "demo-troubleshooting"
DEMO_CATEGORY_NAME = "演示基础排障"


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class SeedDemoDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("create_dev_users", verbosity=0)

    def _run_command(self):
        stdout = StringIO()
        call_command("seed_demo_data", stdout=stdout)
        return stdout.getvalue()

    def test_first_run_creates_only_minimum_non_article_samples(self):
        output = self._run_command()

        employee = User.objects.get(username="dev_employee")
        admin_user = User.objects.get(username="dev_knowledge_admin")
        department = Department.objects.get(dingtalk_dept_id=DEMO_DEPARTMENT_ID)
        content_group = UserGroup.objects.get(name=DEMO_GROUP_NAME)
        space = KnowledgeSpace.objects.get(code=DEMO_SPACE_CODE)
        category = Category.objects.get(space=space, code=DEMO_CATEGORY_CODE)

        self.assertEqual(department.name, DEMO_DEPARTMENT_NAME)
        self.assertTrue(department.is_active)
        self.assertTrue(
            UserDepartment.objects.filter(
                user=employee,
                department=department,
                is_primary=True,
                effective_at__isnull=True,
                expired_at__isnull=True,
            ).exists()
        )
        self.assertEqual(content_group.description, DEMO_GROUP_DESCRIPTION)
        self.assertTrue(content_group.is_active)
        self.assertTrue(
            UserGroupMembership.objects.filter(
                user=employee,
                user_group=content_group,
            ).exists()
        )
        self.assertEqual(space.name, DEMO_SPACE_NAME)
        self.assertEqual(space.description, DEMO_SPACE_DESCRIPTION)
        self.assertEqual(space.space_type, SpaceType.EMPLOYEE)
        self.assertEqual(space.owner, admin_user)
        self.assertEqual(space.default_audience_policy, AudiencePolicy.RESTRICTED)
        self.assertTrue(space.is_active)
        self.assertEqual(category.name, DEMO_CATEGORY_NAME)
        self.assertIsNone(category.parent_id)
        self.assertEqual(category.icon, "")
        self.assertEqual(category.sort_order, 0)
        self.assertTrue(category.is_active)

        self.assertEqual(Department.objects.count(), 1)
        self.assertEqual(UserDepartment.objects.count(), 1)
        self.assertEqual(UserGroup.objects.count(), 1)
        self.assertEqual(UserGroupMembership.objects.count(), 1)
        self.assertEqual(KnowledgeSpace.objects.count(), 1)
        self.assertEqual(Category.objects.count(), 1)
        self.assertIn("created: 6", output)
        self.assertIn("existing: 0", output)
        self.assertIn("conflict: 0", output)

    def test_second_run_is_idempotent_without_updates(self):
        self._run_command()
        before = {
            "departments": list(Department.objects.values()),
            "user_departments": list(UserDepartment.objects.values()),
            "groups": list(UserGroup.objects.values()),
            "memberships": list(UserGroupMembership.objects.values()),
            "spaces": list(KnowledgeSpace.objects.values()),
            "categories": list(Category.objects.values()),
        }

        output = self._run_command()
        after = {
            "departments": list(Department.objects.values()),
            "user_departments": list(UserDepartment.objects.values()),
            "groups": list(UserGroup.objects.values()),
            "memberships": list(UserGroupMembership.objects.values()),
            "spaces": list(KnowledgeSpace.objects.values()),
            "categories": list(Category.objects.values()),
        }

        self.assertEqual(after, before)
        self.assertIn("created: 0", output)
        self.assertIn("existing: 6", output)
        self.assertIn("conflict: 0", output)

    def test_existing_matching_object_is_not_updated_or_duplicated(self):
        department = Department.objects.create(
            dingtalk_dept_id=DEMO_DEPARTMENT_ID,
            name=DEMO_DEPARTMENT_NAME,
            parent=None,
            is_active=True,
        )
        original_updated_at = department.updated_at

        output = self._run_command()

        department.refresh_from_db()
        self.assertEqual(Department.objects.count(), 1)
        self.assertEqual(department.updated_at, original_updated_at)
        self.assertIn("created: 5", output)
        self.assertIn("existing: 1", output)
        self.assertIn("conflict: 0", output)

    def test_conflicting_object_fails_closed_and_leaves_no_partial_demo_set(self):
        conflicting_group = UserGroup.objects.create(
            name=DEMO_GROUP_NAME,
            description="人工维护的不同说明",
            is_active=True,
        )

        with self.assertRaises(CommandError) as ctx:
            self._run_command()

        self.assertIn(DEMO_GROUP_NAME, str(ctx.exception))
        self.assertIn("description", str(ctx.exception))
        self.assertIn("created: 0", str(ctx.exception))
        conflicting_group.refresh_from_db()
        self.assertEqual(conflicting_group.description, "人工维护的不同说明")
        self.assertFalse(Department.objects.filter(dingtalk_dept_id=DEMO_DEPARTMENT_ID).exists())
        self.assertEqual(UserDepartment.objects.count(), 0)
        self.assertEqual(UserGroupMembership.objects.count(), 0)
        self.assertEqual(KnowledgeSpace.objects.count(), 0)
        self.assertEqual(Category.objects.count(), 0)

    def test_unexpected_write_failure_rolls_back_all_new_objects(self):
        with mock.patch.object(Category, "save", side_effect=RuntimeError("injected failure")):
            with self.assertRaises(CommandError) as ctx:
                self._run_command()

        self.assertIn("整体回滚", str(ctx.exception))
        self.assertEqual(Department.objects.count(), 0)
        self.assertEqual(UserDepartment.objects.count(), 0)
        self.assertEqual(UserGroup.objects.count(), 0)
        self.assertEqual(UserGroupMembership.objects.count(), 0)
        self.assertEqual(KnowledgeSpace.objects.count(), 0)
        self.assertEqual(Category.objects.count(), 0)

    def test_unrelated_manual_data_is_untouched(self):
        admin_user = User.objects.get(username="dev_knowledge_admin")
        manual_department = Department.objects.create(
            dingtalk_dept_id="manual-corp-dept",
            name="人工部门",
            is_active=False,
        )
        manual_group = UserGroup.objects.create(
            name="人工内容组",
            description="人工说明",
            is_active=False,
        )
        manual_space = KnowledgeSpace.objects.create(
            code="manual-space",
            name="人工空间",
            description="人工说明",
            space_type=SpaceType.IT_INTERNAL,
            owner=admin_user,
            default_audience_policy=AudiencePolicy.IT_ONLY,
            is_active=False,
        )
        manual_category = Category.objects.create(
            space=manual_space,
            code="manual-category",
            name="人工分类",
            icon="manual-icon",
            sort_order=99,
            is_active=False,
        )

        self._run_command()

        manual_department.refresh_from_db()
        manual_group.refresh_from_db()
        manual_space.refresh_from_db()
        manual_category.refresh_from_db()
        self.assertEqual(manual_department.name, "人工部门")
        self.assertFalse(manual_department.is_active)
        self.assertEqual(manual_group.description, "人工说明")
        self.assertFalse(manual_group.is_active)
        self.assertEqual(manual_space.name, "人工空间")
        self.assertEqual(manual_space.default_audience_policy, AudiencePolicy.IT_ONLY)
        self.assertFalse(manual_space.is_active)
        self.assertEqual(manual_category.icon, "manual-icon")
        self.assertEqual(manual_category.sort_order, 99)
        self.assertFalse(manual_category.is_active)

    def test_article_dependent_objects_are_explicitly_skipped(self):
        output = self._run_command()

        self.assertEqual(Article.objects.count(), 0)
        self.assertEqual(ArticleAudience.objects.count(), 0)
        self.assertEqual(ArticleVersion.objects.count(), 0)
        self.assertEqual(ReviewRecord.objects.count(), 0)
        self.assertIn(
            "Article demo skipped: formal KB number service is not available",
            output,
        )


@override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
class SeedDemoDataPrerequisiteTests(TestCase):
    def test_requires_existing_fixed_development_users_without_partial_writes(self):
        with self.assertRaises(CommandError) as ctx:
            call_command("seed_demo_data")

        self.assertIn("create_dev_users", str(ctx.exception))
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Department.objects.count(), 0)
        self.assertEqual(UserGroup.objects.count(), 0)
        self.assertEqual(KnowledgeSpace.objects.count(), 0)


@override_settings(DEBUG=False, DEV_LOGIN_ENABLED=True)
class SeedDemoDataProductionGuardTests(TestCase):
    def test_refuses_when_debug_is_false(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo_data")

        self.assertEqual(Department.objects.count(), 0)
        self.assertEqual(UserGroup.objects.count(), 0)
        self.assertEqual(KnowledgeSpace.objects.count(), 0)
