"""Tests for the SSH-backed Dell Docker helper."""

from __future__ import annotations

from types import SimpleNamespace

from scripts import dell_docker


def test_builds_ssh_command_without_local_docker() -> None:
    assert dell_docker.build_ssh_docker_command(["ps"]) == ["ssh", "dell", "docker", "ps"]


def test_host_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv(dell_docker.DELL_HOST_ENV, "dell-wifi")

    assert dell_docker.build_ssh_docker_command(["info"], host="dell-wifi") == [
        "ssh", "dell-wifi", "docker", "info"
    ]


def test_run_relays_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr("scripts.remote_docker.subprocess.run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0))

    assert dell_docker.run_dell_docker(["ps"]) == 0
