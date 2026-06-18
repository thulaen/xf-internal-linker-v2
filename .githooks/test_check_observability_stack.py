#!/usr/bin/env python3
"""Tests for ``.githooks/check-observability-stack.py``.

These tests stub ``subprocess.run`` so no live Kubernetes calls are needed.
They cover the documented happy-path and failure cases from
``docs/specs/fr-observability-always-on-and-no-deferral.md``.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


_HOOK_PATH = Path(__file__).resolve().parent / "check-observability-stack.py"


def _load_hook_module():
    """Load check-observability-stack.py as ``hook_module``.

    The hyphen in the filename means a plain ``import`` would fail; we
    import via spec so tests can patch internals.
    """
    spec = importlib.util.spec_from_file_location(
        "check_observability_stack_under_test", _HOOK_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("could not load check-observability-stack.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook_module()


def _make_run_result(stdout: str, returncode: int = 0) -> types.SimpleNamespace:
    return types.SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def _pod_list(service: str, phase: str = "Running", ready: bool = True) -> str:
    return json.dumps(
        {
            "items": [
                {
                    "metadata": {"name": f"{service}-abc"},
                    "status": {
                        "phase": phase,
                        "containerStatuses": [{"name": service, "ready": ready}],
                    },
                }
            ]
        }
    )


class _FakeHTTPResponse:
    """Minimal context-manager stand-in for ``urllib.request.urlopen``."""

    def __init__(self, status: int = 200, body: str = '{"status":"UP"}') -> None:
        self.status = status
        self._body = body

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self, _size: int = -1) -> bytes:
        return self._body.encode("utf-8")


class _NoRemoteMixin:
    """Blank out REMOTE_SERVICES so local-focused tests make no network call."""

    def setUp(self) -> None:  # noqa: D401
        patcher = patch.object(hook, "REMOTE_SERVICES", ())
        patcher.start()
        self.addCleanup(patcher.stop)


class HappyPathTests(_NoRemoteMixin, unittest.TestCase):
    def test_all_services_running_and_healthy_returns_zero(self) -> None:
        def fake_run(cmd, *args, **kwargs):
            service = cmd[-3].replace("app=", "")
            return _make_run_result(_pod_list(service) + "\n")

        with patch.object(hook.subprocess, "run", side_effect=fake_run):
            self.assertEqual(hook.main(), 0)

    def test_running_ready_pod_is_accepted(self) -> None:
        def fake_run(cmd, *args, **kwargs):
            service = cmd[-3].replace("app=", "")
            return _make_run_result(_pod_list(service) + "\n")

        with patch.object(hook.subprocess, "run", side_effect=fake_run):
            self.assertEqual(hook.main(), 0)

    def test_each_service_is_checked_through_kubernetes(self) -> None:
        seen = []

        def fake_run(cmd, *args, **kwargs):
            seen.append(cmd)
            service = cmd[-3].replace("app=", "")
            return _make_run_result(_pod_list(service) + "\n")

        with patch.object(hook.shutil, "which", return_value="kubectl.exe"), patch.object(
            hook.subprocess, "run", side_effect=fake_run
        ):
            self.assertEqual(hook.main(), 0)
        self.assertTrue(all(cmd[:3] == ["kubectl", "-n", hook.K8S_NAMESPACE] for cmd in seen))

    def test_missing_windows_kubectl_uses_mint_ssh(self) -> None:
        seen = []

        def fake_run(cmd, *args, **kwargs):
            seen.append(cmd)
            service = cmd[-3].replace("app=", "")
            return _make_run_result(_pod_list(service) + "\n")

        with patch.object(hook.shutil, "which", return_value=None), patch.object(
            hook.subprocess, "run", side_effect=fake_run
        ):
            self.assertEqual(hook.main(), 0)
        self.assertTrue(all(cmd[:3] == ["ssh", "mint-wifi", "kubectl"] for cmd in seen))


class FailureTests(_NoRemoteMixin, unittest.TestCase):
    def test_one_service_absent_blocks_with_message(self) -> None:
        # grafana is a local service.
        absent = "grafana"

        def fake_run(cmd, *args, **kwargs):
            service = cmd[-3].replace("app=", "")
            if service == absent:
                return _make_run_result('{"items": []}')
            return _make_run_result(_pod_list(service) + "\n")

        captured: list[str] = []
        with patch.object(hook.subprocess, "run", side_effect=fake_run), patch.object(
            hook.sys, "stderr", new=_collect(captured)
        ):
            rc = hook.main()
        self.assertEqual(rc, 2)
        joined = "".join(captured)
        self.assertIn(absent, joined)
        self.assertIn("no Kubernetes pod found", joined)
        self.assertIn("kubectl -n xf-obs get pods", joined)

    def test_pending_phase_blocks(self) -> None:
        broken = "tempo"

        def fake_run(cmd, *args, **kwargs):
            service = cmd[-3].replace("app=", "")
            if service == broken:
                return _make_run_result(_pod_list(service, "Pending") + "\n")
            return _make_run_result(_pod_list(service) + "\n")

        captured: list[str] = []
        with patch.object(hook.subprocess, "run", side_effect=fake_run), patch.object(
            hook.sys, "stderr", new=_collect(captured)
        ):
            rc = hook.main()
        self.assertEqual(rc, 2)
        joined = "".join(captured)
        self.assertIn(broken, joined)
        self.assertIn("Pending", joined)

    def test_not_ready_container_blocks(self) -> None:
        sick = "loki"

        def fake_run(cmd, *args, **kwargs):
            service = cmd[-3].replace("app=", "")
            if service == sick:
                return _make_run_result(_pod_list(service, "Running", ready=False) + "\n")
            return _make_run_result(_pod_list(service) + "\n")

        captured: list[str] = []
        with patch.object(hook.subprocess, "run", side_effect=fake_run), patch.object(
            hook.sys, "stderr", new=_collect(captured)
        ):
            rc = hook.main()
        self.assertEqual(rc, 2)
        joined = "".join(captured)
        self.assertIn(sick, joined)
        self.assertIn("not Ready", joined)

    def test_multiple_services_down_lists_each(self) -> None:
        down = {"loki", "tempo", "grafana"}

        def fake_run(cmd, *args, **kwargs):
            service = cmd[-3].replace("app=", "")
            if service in down:
                return _make_run_result('{"items": []}')
            return _make_run_result(_pod_list(service) + "\n")

        captured: list[str] = []
        with patch.object(hook.subprocess, "run", side_effect=fake_run), patch.object(
            hook.sys, "stderr", new=_collect(captured)
        ):
            rc = hook.main()
        self.assertEqual(rc, 2)
        joined = "".join(captured)
        for service in down:
            self.assertIn(service, joined)


class RemoteServiceTests(unittest.TestCase):
    """Remote services are verified over HTTP via their health endpoint."""

    _REMOTE = (
        {
            "label": "tika",
            "host": "dell",
            "health_url": "http://192.168.0.163:9998/tika",
            "health_ok_contains": "Apache Tika",
        },
    )

    @staticmethod
    def _all_local_running(cmd, *args, **kwargs):
        service = cmd[-3].replace("app=", "")
        return _make_run_result(_pod_list(service) + "\n")

    def test_remote_service_up_returns_zero(self) -> None:
        with patch.object(hook, "REMOTE_SERVICES", self._REMOTE), patch.object(
            hook.subprocess, "run", side_effect=self._all_local_running
        ), patch.object(
            hook.urllib.request,
            "urlopen",
            return_value=_FakeHTTPResponse(200, "Apache Tika"),
        ):
            self.assertEqual(hook.main(), 0)

    def test_remote_service_command_up_returns_zero(self) -> None:
        remote = (
            {
                "label": "tika",
                "host": "dell",
                "health_command": [
                    "docker",
                    "--context",
                    "dell",
                    "exec",
                    "xf_dell_tika",
                    "curl",
                    "-fsS",
                    "http://localhost:9998/tika",
                ],
                "health_ok_contains": "Apache Tika",
            },
        )

        def fake_run(cmd, *args, **kwargs):
            if cmd[:3] == ["ssh", "dell", "docker"]:
                return _make_run_result("Apache Tika\n")
            return self._all_local_running(cmd, *args, **kwargs)

        with patch.object(hook, "REMOTE_SERVICES", remote), patch.object(
            hook.subprocess, "run", side_effect=fake_run
        ):
            self.assertEqual(hook.main(), 0)

    def test_remote_service_command_failure_blocks(self) -> None:
        remote = (
            {
                "label": "tika",
                "host": "dell",
                "health_command": ["docker", "--context", "dell", "exec", "bad"],
                "health_ok_contains": "Apache Tika",
            },
        )

        def fake_run(cmd, *args, **kwargs):
            if cmd[:3] == ["ssh", "dell", "docker"]:
                return _make_run_result("", returncode=1)
            return self._all_local_running(cmd, *args, **kwargs)

        captured: list[str] = []
        with patch.object(hook, "REMOTE_SERVICES", remote), patch.object(
            hook.subprocess, "run", side_effect=fake_run
        ), patch.object(hook.sys, "stderr", new=_collect(captured)):
            rc = hook.main()
        self.assertEqual(rc, 2)
        self.assertIn("health_command failed", "".join(captured))

    def test_remote_service_unreachable_blocks(self) -> None:
        def boom(*args, **kwargs):
            raise hook.urllib.error.URLError("connection refused")

        captured: list[str] = []
        with patch.object(hook, "REMOTE_SERVICES", self._REMOTE), patch.object(
            hook.subprocess, "run", side_effect=self._all_local_running
        ), patch.object(
            hook.urllib.request, "urlopen", side_effect=boom
        ), patch.object(hook.sys, "stderr", new=_collect(captured)):
            rc = hook.main()
        self.assertEqual(rc, 2)
        joined = "".join(captured)
        self.assertIn("tika", joined)
        self.assertIn("dell", joined.lower())

    def test_remote_service_not_healthy_blocks(self) -> None:
        captured: list[str] = []
        with patch.object(hook, "REMOTE_SERVICES", self._REMOTE), patch.object(
            hook.subprocess, "run", side_effect=self._all_local_running
        ), patch.object(
            hook.urllib.request,
            "urlopen",
            return_value=_FakeHTTPResponse(200, "error page"),
        ), patch.object(hook.sys, "stderr", new=_collect(captured)):
            rc = hook.main()
        self.assertEqual(rc, 2)
        self.assertIn("tika", "".join(captured))


class _StderrCollector:
    """Minimal stand-in for ``sys.stderr`` that captures writes."""

    def __init__(self, bucket: list[str]) -> None:
        self._bucket = bucket

    def write(self, message: str) -> int:
        self._bucket.append(message)
        return len(message)

    def flush(self) -> None:  # pragma: no cover - trivial
        return None


def _collect(bucket: list[str]) -> _StderrCollector:
    return _StderrCollector(bucket)


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=2))
