"""生产部署基线的离线配置合同测试。"""

from __future__ import annotations

import importlib
import os
import unittest
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENV = {
    "DJANGO_SECRET_KEY": "test-only-secret",
    "DJANGO_ALLOWED_HOSTS": "kb-pilot.example.internal",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://kb-pilot.example.internal",
    "POSTGRES_DB": "opsai_pilot",
    "POSTGRES_USER": "opsai_pilot",
    "POSTGRES_PASSWORD": "test-only-password",
    "POSTGRES_HOST": "db",
    "POSTGRES_PORT": "5432",
}


class ProductionSettingsTests(unittest.TestCase):
    def _reload_production(self, environment: dict[str, str]):
        with mock.patch.dict(os.environ, environment, clear=True):
            production = importlib.import_module("config.settings.production")
            return importlib.reload(production)

    def test_production_requires_secret_key(self):
        environment = REQUIRED_ENV | {"DJANGO_SECRET_KEY": ""}
        with self.assertRaises(ImproperlyConfigured):
            self._reload_production(environment)

    def test_production_enforces_proxy_and_cookie_security(self):
        production = self._reload_production(REQUIRED_ENV | {"DJANGO_DEV_LOGIN_ENABLED": "true"})

        self.assertFalse(production.DEBUG)
        self.assertFalse(production.DEV_LOGIN_ENABLED)
        self.assertEqual(production.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))
        self.assertTrue(production.SECURE_SSL_REDIRECT)
        self.assertTrue(production.SESSION_COOKIE_SECURE)
        self.assertTrue(production.CSRF_COOKIE_SECURE)
        self.assertEqual(production.SECURE_HSTS_SECONDS, 0)

    def test_production_rejects_non_https_csrf_origin(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_production(
                REQUIRED_ENV | {"DJANGO_CSRF_TRUSTED_ORIGINS": "http://example"}
            )


class ProductionDeploymentFileTests(unittest.TestCase):
    def test_gunicorn_is_a_bounded_runtime_dependency(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('"gunicorn>=27,<28"', pyproject)

    def test_production_dockerfile_uses_gunicorn_not_runserver(self):
        dockerfile = (ROOT / "deploy" / "Dockerfile.production").read_text(encoding="utf-8")

        self.assertIn('"gunicorn"', dockerfile)
        self.assertIn('"config.wsgi:application"', dockerfile)
        self.assertNotIn('CMD ["python", "manage.py", "runserver"', dockerfile)
        self.assertIn("--no-index", dockerfile)
        self.assertIn("setuptools==80.9.0 gunicorn==27.0.0", dockerfile)
        self.assertIn("USER appuser", dockerfile)

    def test_compose_keeps_database_and_gunicorn_off_host_ports(self):
        compose = (ROOT / "deploy" / "compose.pilot.yaml").read_text(encoding="utf-8")

        self.assertIn("internal: true", compose)
        self.assertNotIn('"5432:5432"', compose)
        self.assertNotIn('"8000:8000"', compose)
        self.assertIn('"127.0.0.1:${PILOT_HTTP_PORT:-8080}:80"', compose)
        self.assertIn('"127.0.0.1:${PILOT_HTTPS_PORT:-8443}:443"', compose)
        self.assertIn("frontend:", compose)
        self.assertIn("pilot_postgres_data", compose)
        self.assertIn("pilot_private_media", compose)

    def test_caddy_serves_static_and_blocks_private_media(self):
        caddyfile = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")

        self.assertIn("handle_path /static/*", caddyfile)
        self.assertIn("respond @private_media", caddyfile)
        self.assertIn(
            "redir https://{$PILOT_HTTPS_DOMAIN}:{$PILOT_HTTPS_PORT}{uri} permanent", caddyfile
        )
        self.assertNotIn("/app/private_media", caddyfile)
