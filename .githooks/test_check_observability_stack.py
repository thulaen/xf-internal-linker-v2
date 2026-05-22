#!/usr/bin/env python3
"""Tests for ``.githooks/check-observability-stack.py``.

These tests stub ``subprocess.run`` so no live Docker calls are needed.
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


def _running_record(service: str, health: str = "healthy") -> str:
    return json.dumps({"Service": service, "State": "running", "Health": health})


class HappyPathTests(unittest.TestCase):
    def test_all_services_running_and_healthy_returns_zero(self) -> None:
        def fake_run(cmd, *args, **kwargs):
            service = cmd[-1]
            return _make_run_result(_running_record(service, "healthy") + "\n")

        with patch.object(hook.subprocess, "run", side_effect=fake_run):
            self.assertEqual(hook.main(), 0)

    def test_starting_health_is_accepted(self) -> None:
        def fake_run(cmd, *args, **kwargs):
            service = cmd[-1]
            return _make_run_result(_running_record(service, "starting") + "\n")

        with patch.object(hook.subprocess, "run", side_effect=fake_run):
            self.assertEqual(hook.main(), 0)

    def test_empty_health_is_accepted(self) -> None:
        # otel-collector has no declared healthcheck — Health is "".
        def fake_run(cmd, *args, **kwargs):
            service = cmd[-1]
            return _make_run_result(_running_record(service, "") + "\n")

        with patch.object(hook.subprocess, "run", side_effect=fake_run):
            self.assertEqual(hook.main(), 0)


class FailureTests(unittest.TestCase):
    def test_one_service_absent_blocks_with_message(self) -> None:
        absent = "sonarqube"

        def fake_run(cmd, *args, **kwargs):
            service = cmd[-1]
            if service == absent:
                return _make_run_result("")
            return _make_run_result(_running_record(service, "healthy") + "\n")

        captured: list[str] = []
        with patch.object(hook.subprocess, "run", side_effect=fake_run), patch.object(
            hook.sys, "stderr", new=_collect(captured)
        ):
            rc = hook.main()
        self.assertEqual(rc, 2)
        joined = "".join(captured)
        self.assertIn(absent, joined)
        self.assertIn("absent", joined)
        self.assertIn("docker compose up -d", joined)

    def test_restarting_state_blocks(self) -> None:
        broken = "vmagent"

        def fake_run(cmd, *args, **kwargs):
            service = cmd[-1]
            if service == broken:
                return _make_run_result(
                    json.dumps({"Service": broken, "State": "restarting", "Health": ""})
                    + "\n"
                )
            return _make_run_result(_running_record(service, "healthy") + "\n")

        captured: list[str] = []
        with patch.object(hook.subprocess, "run", side_effect=fake_run), patch.object(
            hook.sys, "stderr", new=_collect(captured)
        ):
            rc = hook.main()
        self.assertEqual(rc, 2)
        joined = "".join(captured)
        self.assertIn(broken, joined)
        self.assertIn("restarting", joined)

    def test_unhealthy_health_blocks(self) -> None:
        sick = "loki"

        def fake_run(cmd, *args, **kwargs):
            service = cmd[-1]
            if service == sick:
                return _make_run_result(
                    json.dumps(
                        {"Service": sick, "State": "running", "Health": "unhealthy"}
                    )
                    + "\n"
                )
            return _make_run_result(_running_record(service, "healthy") + "\n")

        captured: list[str] = []
        with patch.object(hook.subprocess, "run", side_effect=fake_run), patch.object(
            hook.sys, "stderr", new=_collect(captured)
        ):
            rc = hook.main()
        self.assertEqual(rc, 2)
        joined = "".join(captured)
        self.assertIn(sick, joined)
        self.assertIn("unhealthy", joined)

    def test_multiple_services_down_lists_each(self) -> None:
        down = {"loki", "tempo", "grafana"}

        def fake_run(cmd, *args, **kwargs):
            service = cmd[-1]
            if service in down:
                return _make_run_result("")
            return _make_run_result(_running_record(service, "healthy") + "\n")

        captured: list[str] = []
        with patch.object(hook.subprocess, "run", side_effect=fake_run), patch.object(
            hook.sys, "stderr", new=_collect(captured)
        ):
            rc = hook.main()
        self.assertEqual(rc, 2)
        joined = "".join(captured)
        for service in down:
            self.assertIn(service, joined)


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
