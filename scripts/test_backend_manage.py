"""Tests for the Docker-free backend management command runner."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from scripts import backend_manage


def test_default_command_uses_kubernetes_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(backend_manage.TRANSPORT_ENV, raising=False)
    monkeypatch.setattr(backend_manage.shutil, "which", lambda _name: "kubectl.exe")

    command = backend_manage.build_manage_command(["check"])

    assert command == [
        "kubectl",
        "-n",
        "xf-app",
        "exec",
        "deploy/backend",
        "--",
        "env",
        "XF_AUDIT_DIR=/tmp/xf-linker-audit",
        "python",
        "manage.py",
        "check",
    ]


def test_compose_is_only_selected_by_explicit_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(backend_manage.TRANSPORT_ENV, "compose")

    command = backend_manage.build_manage_command(["check"])

    assert command[:6] == ["docker", "compose", "exec", "-T", "backend", "python"]


def test_kubernetes_command_supports_temporary_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(backend_manage.TRANSPORT_ENV, raising=False)
    monkeypatch.setattr(backend_manage.shutil, "which", lambda _name: "kubectl.exe")

    command = backend_manage.build_manage_command(["check"], extra_env=["A=B"])

    assert command[5:10] == [
        "--",
        "env",
        "XF_AUDIT_DIR=/tmp/xf-linker-audit",
        "A=B",
        "python",
    ]


def test_kubernetes_command_respects_explicit_audit_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(backend_manage.TRANSPORT_ENV, raising=False)
    monkeypatch.setattr(backend_manage.shutil, "which", lambda _name: "kubectl.exe")

    command = backend_manage.build_manage_command(
        ["check"],
        extra_env=["XF_AUDIT_DIR=/repo/audit"],
    )

    assert "XF_AUDIT_DIR=/tmp/xf-linker-audit" not in command
    assert command[5:9] == ["--", "env", "XF_AUDIT_DIR=/repo/audit", "python"]


def test_kubernetes_command_falls_back_to_mint_ssh_when_kubectl_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(backend_manage.TRANSPORT_ENV, raising=False)
    monkeypatch.delenv(backend_manage.K8S_SSH_HOST_ENV, raising=False)
    monkeypatch.setattr(backend_manage.shutil, "which", lambda _name: None)

    command = backend_manage.build_manage_command(["check"])

    assert command[:2] == ["ssh", "mint-wifi"]
    assert "kubectl -n xf-app exec deploy/backend" in command[2]
    assert command[2].endswith("python manage.py check")


def test_ssh_fallback_quotes_manage_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(backend_manage.TRANSPORT_ENV, raising=False)
    monkeypatch.setattr(backend_manage.shutil, "which", lambda _name: None)

    command = backend_manage.build_manage_command(["file_hook_finding", "--message", "words with spaces"])

    assert command[:2] == ["ssh", "mint-wifi"]
    assert "--message 'words with spaces'" in command[2]


def test_cli_splits_env_entries() -> None:
    env, args = backend_manage.split_cli_args(["--env", "A=B", "--", "check", "--deploy"])

    assert env == ["A=B"]
    assert args == ["check", "--deploy"]


def test_kubernetes_missing_fails_with_plain_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("kubectl")

    monkeypatch.setattr(backend_manage.subprocess, "run", fake_run)

    assert backend_manage.run_manage(["check"], timeout=1) == 127
    assert "Kubernetes backend is unreachable" in capsys.readouterr().err


def test_timeout_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("kubectl", 1)

    monkeypatch.setattr(backend_manage.subprocess, "run", fake_run)

    assert backend_manage.run_manage(["check"], timeout=1) == 124


def test_success_relays_output(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        backend_manage.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="ok\n", stderr=""),
    )

    assert backend_manage.run_manage(["check"]) == 0
    assert capsys.readouterr().out == "ok\n"
