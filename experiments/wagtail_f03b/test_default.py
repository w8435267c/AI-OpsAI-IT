"""没有 Wagtail App 且阻止其导入的默认兼容性。"""

import sys

from django.apps import apps
from django.core.management.base import CommandError
from django.test import TestCase

from experiments.wagtail_f03b.test_profiles import expected, matrix, snapshot, sync


class DefaultCompatibilityTests(TestCase):
    def test_default_works_without_wagtail_imports(self):
        self.assertFalse(apps.is_installed("wagtail"))
        sync()
        self.assertEqual(matrix(), expected("default"))
        self.assertFalse(any(n == "wagtail" or n.startswith("wagtail.") for n in sys.modules))

    def test_fusion_missing_apps_fails_without_changes(self):
        sync()
        before = snapshot()
        with self.assertRaisesMessage(CommandError, "App 未启用"):
            sync("wagtail-poc")
        self.assertEqual(snapshot(), before)
