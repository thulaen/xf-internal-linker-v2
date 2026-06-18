"""Tests for the MSI Docker-free workflow guard."""

from __future__ import annotations

import importlib.util
from pathlib import Path

HOOK_PATH = Path(__file__).with_name("check-msi-docker-free.py")
spec = importlib.util.spec_from_file_location("check_msi_docker_free", HOOK_PATH)
assert spec and spec.loader
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


def test_flags_local_compose_usage() -> None:
    findings = hook.scan_text("scripts/example.sh", "docker compose exec backend echo hi\n")

    assert findings


def test_flags_docker_desktop_guidance() -> None:
    findings = hook.scan_text("scripts/example.ps1", 'Write-Host "Start Docker Desktop"\n')

    assert findings


def test_allows_kubernetes_backend_runner() -> None:
    findings = hook.scan_text(
        "scripts/example.sh",
        "python scripts/backend_manage.py check\nkubectl -n xf-app get pods\n",
    )

    assert findings == []


def test_allows_remote_ssh_docker() -> None:
    findings = hook.scan_text(
        "scripts/example.ps1",
        'ssh dell docker ps\nssh mint docker compose ps\n',
    )

    assert findings == []


def test_allows_retired_script_text() -> None:
    findings = hook.scan_text(
        "scripts/old.ps1",
        "# old.ps1 - retired.\nWrite-Error \"Docker Desktop path is retired\"\n",
    )

    assert findings == []
