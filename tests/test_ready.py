"""GET /health/ready 的就绪与降级测试。"""

import tempfile
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings


class HealthReadyOkTests(TestCase):
    def test_ready_returns_200_when_dependencies_ok(self):
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "checks": {"database": True, "private_media": True}},
        )


class HealthReadyDatabaseDownTests(SimpleTestCase):
    def test_ready_returns_503_when_database_unavailable(self):
        # 模拟依赖检查失败，避免在 SimpleTestCase 中触碰真实数据库连接
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            with mock.patch("apps.core.views._database_ready", return_value=False):
                response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "status": "unavailable",
                "checks": {"database": False, "private_media": True},
            },
        )
        self.assertNotIn("secret-db-detail", response.content.decode())


class HealthReadyMediaNotWritableTests(TestCase):
    def test_ready_returns_503_when_media_dir_not_writable(self):
        with mock.patch(
            "apps.core.views.tempfile.mkstemp",
            side_effect=PermissionError("media-secret-detail"),
        ):
            response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "status": "unavailable",
                "checks": {"database": True, "private_media": False},
            },
        )
        self.assertNotIn("media-secret-detail", response.content.decode())


class HealthReadyMethodTests(SimpleTestCase):
    def test_ready_rejects_non_get_requests(self):
        response = self.client.post("/health/ready")

        self.assertEqual(response.status_code, 405)
