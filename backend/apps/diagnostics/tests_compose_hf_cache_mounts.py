"""Checks that Celery services share the Hugging Face cache volume."""

from __future__ import annotations

import yaml
from django.test import SimpleTestCase

from apps.audit.tests_glitchtip_compose_integrity import COMPOSE_PATH


CELERY_SERVICES = ("celery-worker-default", "celery-worker-pipeline", "celery-beat")
HF_CACHE_MOUNT = "hf_cache:/tmp/.cache"


class HuggingFaceCacheComposeTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with COMPOSE_PATH.open("r", encoding="utf-8") as fh:
            cls.compose = yaml.safe_load(fh)

    def test_hf_cache_volume_is_declared_once(self):
        volumes = self.compose.get("volumes") or {}

        self.assertIn(
            "hf_cache",
            volumes,
            msg="docker-compose.yml must declare the shared `hf_cache` Docker volume.",
        )
        self.assertEqual(
            volumes["hf_cache"],
            {"driver": "local"},
            msg="`hf_cache` must be a local named Docker volume.",
        )

    def test_three_celery_services_mount_hf_cache_at_tmp_cache(self):
        services = self.compose.get("services") or {}

        for name in CELERY_SERVICES:
            service = services.get(name)
            self.assertIsNotNone(service, msg=f"`{name}` is missing from docker-compose.yml.")
            self.assertIn(
                HF_CACHE_MOUNT,
                service.get("volumes") or [],
                msg=f"`{name}` must mount `hf_cache` at `/tmp/.cache`.",
            )

    def test_backend_service_does_not_mount_hf_cache_in_this_slice(self):
        backend = self.compose["services"]["backend"]

        self.assertNotIn(
            HF_CACHE_MOUNT,
            backend.get("volumes") or [],
            msg="The backend service stays out of the first hf_cache slice.",
        )

    def test_celery_services_repair_cache_ownership_before_start(self):
        for name in CELERY_SERVICES:
            service = self.compose["services"][name]
            command = service.get("command") or ""

            self.assertEqual(service.get("user"), "0:0", msg=f"`{name}` must start as root to fix volume ownership.")
            self.assertIn("mkdir -p /tmp/.cache/huggingface", command)
            self.assertIn("chown -R appuser:appuser /tmp/.cache", command)
            self.assertIn("su -m appuser -c", command)
