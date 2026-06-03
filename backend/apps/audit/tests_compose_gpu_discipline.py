"""
Hard CI gate that fails if any Docker service declares GPU device access.

Background: this slice removes project Docker access to the laptop GPU while
leaving the Windows NVIDIA driver installed. The larger backend and frontend
GPU-code deletion remains a separate, test-heavy slice. At this stage, the
compose file must not ask Docker for NVIDIA devices at all.

Source-of-truth spec: `docs/specs/fr-gpu-idle-release.md` §Hard Fence
Requirements HF-1 — no Docker service declares GPU in compose.

Spec source-excerpt: Docker Compose Deploy Specification (devices) —
"devices defines a list of device reservations the platform should provide
for the service. […] When the platform is unable to provide a list of
devices matching the request, the service deployment must fail."

The test reads only `docker-compose.yml` and does not require Docker, the
live stack, or any database. It runs as a plain `SimpleTestCase` in <100 ms.
"""

from __future__ import annotations

from typing import Any

import yaml
from django.test import SimpleTestCase

from apps.audit.tests_glitchtip_compose_integrity import COMPOSE_PATH


def _devices_for(service: dict[str, Any]) -> list[dict[str, Any]]:
    deploy = service.get("deploy") or {}
    resources = deploy.get("resources") or {}
    reservations = resources.get("reservations") or {}
    devices = reservations.get("devices") or []
    return [device for device in devices if isinstance(device, dict)]


def _has_nvidia_device(service: dict[str, Any]) -> bool:
    for device in _devices_for(service):
        if device.get("driver") == "nvidia":
            return True
        capabilities = device.get("capabilities") or []
        if "gpu" in capabilities:
            return True
    return False


class ComposeGpuDisciplineTests(SimpleTestCase):
    """Per fr-gpu-idle-release.md §HF-1: no service gets Docker GPU access."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with COMPOSE_PATH.open("r", encoding="utf-8") as fh:
            cls.services = yaml.safe_load(fh)["services"]

    def test_given_compose_parsed_when_backend_devices_checked_then_no_nvidia_block(self):
        """HF-1 / HF-2: backend service must not declare a GPU device."""
        service = self.services.get("backend")
        self.assertIsNotNone(service, msg="`backend` service missing from compose.")
        self.assertFalse(
            _has_nvidia_device(service),
            msg=(
                "`backend` declares `deploy.resources.reservations.devices` with the "
                "nvidia driver, but the backend service has no GPU code path. "
                "Remove the devices block per docs/specs/fr-gpu-idle-release.md §HF-1."
            ),
        )

    def test_given_compose_parsed_when_celery_worker_default_devices_checked_then_no_nvidia_block(self):
        """HF-1 / HF-3: celery-worker-default service must not declare a GPU device."""
        service = self.services.get("celery-worker-default")
        self.assertIsNotNone(service, msg="`celery-worker-default` missing from compose.")
        self.assertFalse(
            _has_nvidia_device(service),
            msg=(
                "`celery-worker-default` declares an nvidia device, but no task "
                "routed to the `default` queue uses GPU code. Remove the devices "
                "block per docs/specs/fr-gpu-idle-release.md §HF-1."
            ),
        )

    def test_given_compose_parsed_when_celery_worker_pipeline_devices_checked_then_no_nvidia_block(self):
        """HF-1 / HF-4: celery-worker-pipeline must not declare a GPU device."""
        service = self.services.get("celery-worker-pipeline")
        self.assertIsNotNone(service, msg="`celery-worker-pipeline` missing from compose.")
        self.assertFalse(
            _has_nvidia_device(service),
            msg=(
                "`celery-worker-pipeline` declares an nvidia device. This staged "
                "cleanup removes all Docker GPU device access before the larger "
                "backend GPU-code decommission."
            ),
        )

    def test_given_compose_parsed_when_every_service_checked_then_no_service_has_gpu(self):
        """HF-1: across every service, no service carries nvidia."""
        offenders = sorted(
            name
            for name, service in self.services.items()
            if _has_nvidia_device(service)
        )
        self.assertEqual(
            offenders,
            [],
            msg=(
                f"Services declaring Docker GPU device access: {offenders}. Per "
                f"docs/specs/fr-gpu-idle-release.md §HF-1, this staged cleanup "
                f"allows no `deploy.resources.reservations.devices` entry with "
                f"the nvidia driver or GPU capability."
            ),
        )
