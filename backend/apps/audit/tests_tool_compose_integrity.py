"""Checks that Docker-managed quality tool containers boot by default."""

from __future__ import annotations

import json

import yaml
from django.test import SimpleTestCase

from apps.audit.tests_glitchtip_compose_integrity import COMPOSE_PATH


TOOL_SERVICES = ("compiled-tools", "frontend-mutation-tools")
PROTECTED_DATA_STORES_PATH = COMPOSE_PATH.parent / "config" / "protected-data-stores.json"


class DockerToolComposeIntegrityTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with COMPOSE_PATH.open("r", encoding="utf-8") as fh:
            cls.services = yaml.safe_load(fh)["services"]
        with PROTECTED_DATA_STORES_PATH.open("r", encoding="utf-8") as fh:
            cls.protected_data = json.load(fh)

    def test_tool_services_are_default_stack_services(self):
        for name in TOOL_SERVICES:
            service = self.services.get(name)
            self.assertIsNotNone(service, msg=f"`{name}` is missing from docker-compose.yml.")
            self.assertEqual(
                service.get("profiles") or [],
                [],
                msg=f"`{name}` must start on a normal `docker compose up`.",
            )

    def test_tool_services_restart_and_keep_running(self):
        for name in TOOL_SERVICES:
            service = self.services[name]
            self.assertEqual(service.get("restart"), "unless-stopped")
            self.assertIn("tail -f /dev/null", service.get("command") or "")
            self.assertIn("healthcheck", service)

    def test_compiled_tools_uses_shared_compiled_artifact_volume(self):
        volumes = self.services["compiled-tools"].get("volumes") or []
        self.assertIn(
            "compiled_artifacts:/opt/xf/compiled",
            volumes,
            msg="`compiled-tools` must use the shared compiled-artifact Docker volume.",
        )

    def test_tool_services_use_shared_cache_volumes(self):
        compiled_volumes = self.services["compiled-tools"].get("volumes") or []
        frontend_volumes = self.services["frontend-mutation-tools"].get("volumes") or []
        self.assertIn("compiled_tool_cache:/root/.cache", compiled_volumes)
        self.assertIn("go_tool_mod_cache:/go/pkg/mod", compiled_volumes)
        self.assertIn("frontend_tool_cache:/root/.npm", frontend_volumes)

    def test_tool_cache_prune_policy_protects_embedding_space(self):
        policy = self.protected_data["tool_cache_policy"]

        self.assertEqual(policy["normal_retention_days"], 3)
        self.assertEqual(policy["pressure_retention_days"], 2)
        self.assertEqual(policy["cleanup_watermark_gb"], 64)
        self.assertEqual(policy["protected_reserve_gb"], 48)
        self.assertEqual(
            set(policy["deduped_cache_volumes"]),
            {"compiled_tool_cache", "frontend_tool_cache", "go_tool_mod_cache"},
        )

    def test_pipeline_worker_uses_single_process_pool_for_gpu_code(self):
        command = self.services["celery-worker-pipeline"].get("command") or ""
        self.assertIn("--pool=solo", command)
        self.assertIn("--concurrency=1", command)
        self.assertIn("-Q pipeline,embeddings", command)
