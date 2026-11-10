"""钉钉已验证身份到既有员工账号的离线映射测试。"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import AccountStatus
from apps.dingtalk.authentication import IdentityMappingError, map_verified_identity
from apps.dingtalk.providers import VerifiedDingTalkIdentity

User = get_user_model()


class DingTalkIdentityMappingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dingtalk-employee",
            dingtalk_corp_id="corp-001",
            dingtalk_user_id="user-001",
        )

    def identity(self, *, corp_id="corp-001", user_id="user-001"):
        return VerifiedDingTalkIdentity(corp_id=corp_id, user_id=user_id)

    def test_exact_verified_corp_and_user_maps_existing_active_employee(self):
        self.assertEqual(map_verified_identity(self.identity()), self.user)

    def test_corp_mismatch_is_rejected(self):
        with self.assertRaises(IdentityMappingError):
            map_verified_identity(self.identity(corp_id="corp-other"))

    def test_unknown_user_is_rejected_without_auto_creation(self):
        before = User.objects.count()
        with self.assertRaises(IdentityMappingError):
            map_verified_identity(self.identity(user_id="missing"))
        self.assertEqual(User.objects.count(), before)

    def test_disabled_departed_and_inactive_accounts_are_rejected(self):
        for changes in (
            {"account_status": AccountStatus.DISABLED},
            {"account_status": AccountStatus.DEPARTED},
            {"is_active": False},
        ):
            with self.subTest(changes=changes):
                User.objects.filter(pk=self.user.pk).update(**changes)
                with self.assertRaises(IdentityMappingError):
                    map_verified_identity(self.identity())
                User.objects.filter(pk=self.user.pk).update(
                    account_status=AccountStatus.ACTIVE,
                    is_active=True,
                )

    def test_missing_verified_identity_fields_are_rejected(self):
        for identity in (
            VerifiedDingTalkIdentity(corp_id="", user_id="user-001"),
            VerifiedDingTalkIdentity(corp_id="corp-001", user_id=""),
        ):
            with self.subTest(identity=identity):
                with self.assertRaises(IdentityMappingError):
                    map_verified_identity(identity)
