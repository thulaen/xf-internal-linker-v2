"""Compose checks for instant frontend development mode."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.audit.tests_glitchtip_compose_integrity import COMPOSE_PATH, REPO_ROOT
import yaml


class FrontendDevComposeTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with COMPOSE_PATH.open("r", encoding="utf-8") as fh:
            cls.compose = yaml.safe_load(fh)
        cls.services = cls.compose["services"]

    def test_frontend_dev_service_serves_angular_with_polling(self):
        service = self.services.get("frontend-dev")
        self.assertIsNotNone(service, msg="docker-compose.yml needs a frontend-dev service.")
        self.assertEqual(service.get("build", {}).get("dockerfile"), "Dockerfile.dev")
        self.assertEqual(service.get("environment", {}).get("CHROME_BIN"), "/usr/bin/chromium")
        self.assertEqual(service.get("mem_limit"), "4g")
        self.assertEqual(service.get("profiles"), ["dev"])
        self.assertIn("4200:4200", service.get("ports", []))
        command = " ".join(service.get("command", []))
        self.assertIn("npm run start", command)
        self.assertNotIn("-- --host", command)
        self.assertNotIn("-- --port", command)
        self.assertNotIn("-- --poll", command)
        self.assertIn("./frontend:/app", service.get("volumes", []))

    def test_nginx_dev_service_uses_dev_proxy_config(self):
        service = self.services.get("nginx-dev")
        self.assertIsNotNone(service, msg="docker-compose.yml needs an nginx-dev service.")
        self.assertEqual(service.get("profiles"), ["dev"])
        self.assertIn("8080:80", service.get("ports", []))
        self.assertIn("./nginx/nginx.dev.conf:/etc/nginx/nginx.conf:ro", service.get("volumes", []))
        self.assertIn("frontend-dev", service.get("depends_on", {}))

    def test_nginx_dev_config_proxies_pages_to_frontend_dev(self):
        config = (REPO_ROOT / "nginx" / "nginx.dev.conf").read_text(encoding="utf-8")
        self.assertIn("proxy_pass http://frontend-dev:4200", config)
        self.assertIn("proxy_pass http://backend:8000", config)
        self.assertIn("Cache-Control \"no-store", config)
        self.assertIn("proxy_set_header Host $host;", config)
        self.assertNotIn("proxy_set_header Host frontend-dev:4200;", config)
