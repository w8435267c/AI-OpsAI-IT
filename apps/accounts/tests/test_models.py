"""accounts 数据模型的约束、关系与删除策略测试。"""

from django.contrib.auth.models import Group as SystemGroup
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from ..models import (
    AccountStatus,
    Department,
    User,
    UserDepartment,
    UserGroup,
    UserGroupMembership,
)


def create_user(username: str, **kwargs) -> User:
    return User.objects.create_user(username=username, **kwargs)


class UserExternalIdentityTests(TestCase):
    """钉钉身份映射与员工编号的唯一约束（数据库层）。"""

    def test_dingtalk_identity_unique_when_both_present(self):
        create_user("u1", dingtalk_corp_id="corp", dingtalk_user_id="uid-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            # 绕过模型层校验，直接验证数据库唯一约束
            User.objects.create(username="u2", dingtalk_corp_id="corp", dingtalk_user_id="uid-1")

    def test_dingtalk_identity_allows_same_user_id_in_different_corp(self):
        create_user("u1", dingtalk_corp_id="corp-a", dingtalk_user_id="uid-1")
        other = User.objects.create(
            username="u2", dingtalk_corp_id="corp-b", dingtalk_user_id="uid-1"
        )
        self.assertEqual(other.username, "u2")

    def test_dingtalk_identity_null_allows_multiple_users(self):
        create_user("u1")
        create_user("u2")
        self.assertEqual(User.objects.count(), 2)

    def test_employee_no_unique_when_set(self):
        create_user("u1", employee_no="E-001")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(username="u2", employee_no="E-001")

    def test_employee_no_null_allows_multiple_users(self):
        create_user("u1")
        create_user("u2")
        self.assertEqual(User.objects.count(), 2)


class DepartmentTests(TestCase):
    """部门唯一标识、父子关系与删除策略。"""

    def test_dingtalk_dept_id_unique(self):
        Department.objects.create(name="IT 部", dingtalk_dept_id="dept-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Department.objects.create(name="重复部门", dingtalk_dept_id="dept-1")

    def test_dingtalk_dept_id_null_allows_multiple_departments(self):
        Department.objects.create(name="手工部门一")
        Department.objects.create(name="手工部门二")
        self.assertEqual(Department.objects.count(), 2)

    def test_parent_child_relationship(self):
        parent = Department.objects.create(name="IT 部")
        child = Department.objects.create(name="网络组", parent=parent)
        self.assertEqual(child.parent, parent)
        self.assertIn(child, parent.children.all())

    def test_deleting_parent_with_children_is_protected(self):
        parent = Department.objects.create(name="IT 部")
        Department.objects.create(name="网络组", parent=parent)
        with self.assertRaises(ProtectedError):
            parent.delete()


class UserDepartmentTests(TestCase):
    """多部门关系与主部门唯一性。"""

    def setUp(self):
        self.user = create_user("u1")
        self.dept_a = Department.objects.create(name="部门A")
        self.dept_b = Department.objects.create(name="部门B")

    def test_user_can_belong_to_multiple_departments(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_a)
        UserDepartment.objects.create(user=self.user, department=self.dept_b)
        self.assertEqual(self.user.department_memberships.count(), 2)

    def test_duplicate_user_department_raises_integrity_error(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_a)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserDepartment.objects.create(user=self.user, department=self.dept_a)

    def test_only_one_primary_department_per_user(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_a, is_primary=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserDepartment.objects.create(user=self.user, department=self.dept_b, is_primary=True)

    def test_multiple_non_primary_memberships_allowed(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_a)
        UserDepartment.objects.create(user=self.user, department=self.dept_b)
        self.assertEqual(self.user.department_memberships.count(), 2)

    def test_deleting_user_with_membership_is_protected(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_a)
        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_deleting_department_with_membership_is_protected(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_a)
        with self.assertRaises(ProtectedError):
            self.dept_a.delete()


class UserGroupTests(TestCase):
    """内容用户组与 Django 系统角色的概念分离。"""

    def test_user_group_is_not_a_system_group(self):
        group = UserGroup.objects.create(name="新员工")
        self.assertNotIsInstance(group, SystemGroup)
        self.assertEqual(SystemGroup.objects.count(), 0)

    def test_user_group_name_unique(self):
        UserGroup.objects.create(name="新员工")
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserGroup.objects.create(name="新员工")

    def test_default_is_active(self):
        group = UserGroup.objects.create(name="新员工")
        self.assertTrue(group.is_active)


class UserGroupMembershipTests(TestCase):
    """用户组成员关系的唯一性、反向关系与删除策略。"""

    def setUp(self):
        self.user = create_user("u1")
        self.group = UserGroup.objects.create(name="新员工")

    def test_duplicate_membership_raises_integrity_error(self):
        UserGroupMembership.objects.create(user=self.user, user_group=self.group)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserGroupMembership.objects.create(user=self.user, user_group=self.group)

    def test_related_names(self):
        membership = UserGroupMembership.objects.create(user=self.user, user_group=self.group)
        self.assertIn(membership, self.user.user_group_memberships.all())
        self.assertIn(membership, self.group.memberships.all())

    def test_deleting_user_with_membership_is_protected(self):
        UserGroupMembership.objects.create(user=self.user, user_group=self.group)
        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_deleting_group_with_membership_is_protected(self):
        UserGroupMembership.objects.create(user=self.user, user_group=self.group)
        with self.assertRaises(ProtectedError):
            self.group.delete()


class ModelDefaultsAndStrTests(TestCase):
    """模型字符串表示与基础字段默认值。"""

    def test_user_str_prefers_display_name(self):
        named = create_user("u1", display_name="张三")
        unnamed = create_user("u2")
        self.assertEqual(str(named), "张三")
        self.assertEqual(str(unnamed), "u2")

    def test_user_account_status_default_active(self):
        user = create_user("u1")
        self.assertEqual(user.account_status, AccountStatus.ACTIVE)

    def test_department_str(self):
        dept = Department.objects.create(name="IT 部")
        self.assertEqual(str(dept), "IT 部")
        self.assertTrue(dept.is_active)
        self.assertIsNone(dept.parent)

    def test_user_department_defaults(self):
        user = create_user("u1")
        dept = Department.objects.create(name="部门A")
        relation = UserDepartment.objects.create(user=user, department=dept)
        self.assertFalse(relation.is_primary)
        self.assertIsNone(relation.effective_at)
        self.assertIsNone(relation.expired_at)
        self.assertIn("u1", str(relation))

    def test_user_group_str_and_description_default(self):
        group = UserGroup.objects.create(name="新员工")
        self.assertEqual(str(group), "新员工")
        self.assertEqual(group.description, "")

    def test_user_group_membership_str(self):
        user = create_user("u1")
        group = UserGroup.objects.create(name="新员工")
        membership = UserGroupMembership.objects.create(user=user, user_group=group)
        self.assertIn("u1", str(membership))
        self.assertIn("新员工", str(membership))
