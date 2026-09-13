"""配置档完整集合、幂等、失败原子性和开发身份参数传递。"""

from io import StringIO
from unittest import mock

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts import roles
from apps.accounts.models import User, UserGroup, UserGroupMembership
from apps.accounts.tests import test_roles


def sync(profile="default"):
    call_command("sync_system_roles", profile=profile, stdout=StringIO())


def snapshot():
    models = [
        Group,
        Group.permissions.through,
        User,
        User.groups.through,
        User.user_permissions.through,
        UserGroup,
        UserGroupMembership,
        Permission,
    ]
    return {m._meta.label: list(m.objects.order_by("pk").values()) for m in models}


def matrix():
    return {
        r.name: {
            f"{p.content_type.app_label}.{p.codename}"
            for p in Group.objects.get(name=r.name).permissions.select_related("content_type")
        }
        for r in roles.SYSTEM_ROLES
    }


def expected(profile):
    return {
        name: perms
        | (
            {"wagtailadmin.access_admin"}
            if profile == "wagtail-poc" and name != "普通员工"
            else set()
        )
        for name, perms in test_roles.ExpectedPermissionMatrixTests.EXPECTED.items()
    }


class ProfileTests(TestCase):
    def test_default_exact_original_matrix(self):
        call_command("sync_system_roles", stdout=StringIO())
        self.assertEqual(matrix(), expected("default"))

    def test_fusion_exact_minimum_increment_and_no_forbidden_permissions(self):
        sync("wagtail-poc")
        self.assertEqual(matrix(), expected("wagtail-poc"))
        self.assertEqual([len(matrix()[r.name]) for r in roles.SYSTEM_ROLES], [0, 9, 7, 20])
        for perms in matrix().values():
            self.assertFalse({"accounts.change_user", "auth.change_group"} & perms)
            self.assertFalse(any(".delete_" in p for p in perms))
            self.assertEqual(
                {p for p in perms if p.startswith("wagtail")},
                {"wagtailadmin.access_admin"} if perms else set(),
            )

    def test_repeat_sync_preserves_ids_and_permissions(self):
        sync("wagtail-poc")
        before = snapshot()
        sync("wagtail-poc")
        self.assertEqual(snapshot(), before)

    def test_switch_back_restores_original_sets(self):
        sync("wagtail-poc")
        ids = dict(Group.objects.values_list("name", "pk"))
        sync()
        self.assertEqual(matrix(), expected("default"))
        self.assertEqual(dict(Group.objects.values_list("name", "pk")), ids)

    def test_managed_drift_corrected_without_touching_other_data(self):
        sync()
        unmanaged = Group.objects.create(name="f03b_external")
        extra = Permission.objects.get(content_type__app_label="auth", codename="change_group")
        unmanaged.permissions.add(extra)
        user = User.objects.create_user(
            username="f03b_preserve",
            password="synthetic-only",
            account_status="departed",
            is_active=False,
        )
        user.groups.add(unmanaged, Group.objects.get(name="知识编辑员"))
        user.user_permissions.add(extra)
        audience = UserGroup.objects.create(name="f03b_content")
        UserGroupMembership.objects.create(user=user, user_group=audience)
        Group.objects.get(name="知识编辑员").permissions.add(extra)
        before = snapshot()
        sync("wagtail-poc")
        after = snapshot()
        for key in before:
            if key != Group.permissions.through._meta.label:
                self.assertEqual(before[key], after[key])
        self.assertEqual(list(unmanaged.permissions.all()), [extra])
        self.assertEqual(matrix(), expected("wagtail-poc"))

    def test_invalid_profile_fails_before_changes(self):
        before = snapshot()
        with self.assertRaises(CommandError):
            sync("invalid")
        self.assertEqual(snapshot(), before)

    def test_missing_app_fails_even_with_permission_present(self):
        sync()
        before = snapshot()
        with mock.patch(
            "apps.accounts.management.commands.sync_system_roles.apps.is_installed",
            return_value=False,
        ):
            with self.assertRaisesMessage(CommandError, "App 未启用"):
                sync("wagtail-poc")
        self.assertEqual(snapshot(), before)

    def test_missing_permission_has_no_partial_update(self):
        sync()
        Permission.objects.filter(
            content_type__app_label="wagtailadmin", codename="access_admin"
        ).delete()
        before = snapshot()
        with self.assertRaisesMessage(CommandError, "wagtailadmin.access_admin"):
            sync("wagtail-poc")
        self.assertEqual(snapshot(), before)

    def test_missing_content_type_has_no_partial_update(self):
        ContentType.objects.filter(app_label="wagtailadmin", model="admin").delete()
        before = snapshot()
        with self.assertRaisesMessage(CommandError, "wagtailadmin.access_admin"):
            sync("wagtail-poc")
        self.assertEqual(snapshot(), before)

    def test_mid_save_failure_rolls_back_existing_and_new_groups(self):
        first = Group.objects.create(name="普通员工")
        first.permissions.add(
            Permission.objects.get(content_type__app_label="auth", codename="add_group")
        )
        before = snapshot()
        real = Group.objects.get_or_create
        count = 0

        def fail_third(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 3:
                raise RuntimeError("F03B injected save failure")
            return real(*args, **kwargs)

        with mock.patch.object(Group.objects, "get_or_create", side_effect=fail_third):
            with self.assertRaisesMessage(CommandError, "整体回滚"):
                sync("wagtail-poc")
        self.assertEqual(snapshot(), before)

    @override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
    def test_dev_users_profile_forwarding_and_identity_invariants(self):
        call_command("create_dev_users", profile="wagtail-poc", stdout=StringIO())
        self.assertEqual(matrix(), expected("wagtail-poc"))
        before = snapshot()
        call_command("create_dev_users", profile="wagtail-poc", stdout=StringIO())
        self.assertEqual(snapshot(), before)
        for identity in roles.DEV_IDENTITIES:
            user = User.objects.get(username=identity.username)
            self.assertIsNone(roles.dev_user_deviation(user, identity))
            self.assertFalse(user.has_usable_password())
            self.assertFalse(user.is_superuser)
            self.assertEqual(user.is_staff, identity.is_staff)

    @override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
    def test_dev_users_default_explicitly_restores_default_roles(self):
        call_command("create_dev_users", profile="wagtail-poc", stdout=StringIO())
        users_before = list(User.objects.order_by("pk").values())
        call_command("create_dev_users", stdout=StringIO())
        self.assertEqual(matrix(), expected("default"))
        self.assertEqual(list(User.objects.order_by("pk").values()), users_before)

    @override_settings(DEBUG=True, DEV_LOGIN_ENABLED=True)
    def test_dev_user_conflict_not_relaxed_in_fusion(self):
        User.objects.create_user(username="dev_editor", password="synthetic-conflict")
        before = snapshot()
        with self.assertRaises(CommandError):
            call_command("create_dev_users", profile="wagtail-poc", stdout=StringIO())
        self.assertEqual(snapshot(), before)
