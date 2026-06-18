"""Tests for the Kubernetes rehearsal readiness check."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / ".githooks" / "check-k8s-cluster-ready.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_k8s_cluster_ready", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _nodes(*names: str) -> str:
    items = [
        {
            "metadata": {"name": name},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }
        for name in names
    ]
    return json.dumps({"items": items})


def test_dry_run_never_calls_kubectl_and_reports_ready(capsys) -> None:
    mod = _load_module()

    result = mod.main(["--dry-run"])

    out = capsys.readouterr().out
    assert result == 0
    assert "Would check nodes" in out
    assert "[K8S CLUSTER READY: yes]" in out


def test_live_check_passes_with_two_ready_nodes_and_services() -> None:
    mod = _load_module()

    def runner(args: list[str]) -> str:
        if args[:2] == ["get", "nodes"]:
            return _nodes(*mod.EXPECTED_NODES)
        return "service/foo\n"

    result = mod.check_cluster(runner)

    assert result.ready is True
    assert all(message.startswith("PASS:") for message in result.messages)


def test_live_check_fails_when_expected_node_is_missing() -> None:
    mod = _load_module()

    def runner(args: list[str]) -> str:
        if args[:2] == ["get", "nodes"]:
            return _nodes(mod.EXPECTED_NODES[0])
        return "service/foo\n"

    result = mod.check_cluster(runner)

    assert result.ready is False
    assert "FAIL: missing node dell-ubuntu-01-optiplex-micro-7010" in result.messages


def test_live_check_fails_when_service_lookup_fails() -> None:
    mod = _load_module()

    def runner(args: list[str]) -> str:
        if args[:2] == ["get", "nodes"]:
            return _nodes(*mod.EXPECTED_NODES)
        raise subprocess.CalledProcessError(1, args)

    result = mod.check_cluster(runner)

    assert result.ready is False
    assert any("service xf-app/backend" in message for message in result.messages)


def test_live_check_reports_node_timeout_as_not_ready() -> None:
    mod = _load_module()

    def runner(args: list[str]) -> str:
        raise subprocess.TimeoutExpired(args, timeout=20)

    result = mod.check_cluster(runner)

    assert result.ready is False
    assert result.messages == (
        "FAIL: kubectl could not read cluster nodes: Command '['get', 'nodes', '-o', "
        "'json']' timed out after 20 seconds",
    )
