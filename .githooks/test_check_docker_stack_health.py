from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import check_docker_stack_health as hook


def _container(name: str, status: str = "running", health: str | None = None) -> str:
    state: dict[str, object] = {"Status": status}
    if health is not None:
        state["Health"] = {"Status": health}
    return json.dumps({"Name": f"/{name}", "State": state})


def test_config_supports_windows_mint_and_future_pc() -> None:
    config = hook.load_config()
    names = [target["name"] for target in config["targets"]]

    assert "windows-control-plane" in names
    assert "mint-quality-plane" in names
    assert "third-pc-template" in names
    assert any(target.get("enabled") is False for target in config["targets"])


def test_probe_builds_context_and_ssh_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[tuple[str, ...]] = []

    def fake_run(command, **_kwargs):
        commands.append(tuple(command))
        return SimpleNamespace(returncode=0, stdout=_container(command[-1]), stderr="")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    windows = {
        "name": "windows",
        "kind": "docker-context",
        "context": "desktop-linux",
        "containers": [{"name": "xf_linker_backend"}],
    }
    mint = {
        "name": "mint",
        "kind": "ssh",
        "host": "mint",
        "containers": [{"name": "xf_linker_compiled_tools"}],
    }

    assert hook.check_target(windows) == []
    assert hook.check_target(mint) == []
    assert commands[0][:4] == ("docker", "--context", "desktop-linux", "inspect")
    assert commands[1][:3] == ("ssh", "mint", "docker")


def test_unhealthy_container_blocks_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(_command, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=_container("xf_linker_backend", health="unhealthy"),
            stderr="",
        )

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    target = {
        "name": "windows",
        "kind": "docker-context",
        "context": "desktop-linux",
        "containers": [{"name": "xf_linker_backend", "health": "healthy"}],
    }

    failures = hook.check_target(target)

    assert failures
    assert "xf_linker_backend" in failures[0]
    assert "unhealthy" in failures[0]


def test_main_reports_why_and_unblock_for_down_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = tmp_path / "docker-stack-health.json"
    config.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "name": "windows",
                        "kind": "docker-context",
                        "context": "desktop-linux",
                        "containers": [{"name": "xf_linker_backend"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run(_command, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="daemon down")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    result = hook.main(["--config", str(config)])

    captured = capsys.readouterr()
    assert result == 2
    assert "WHY:" in captured.err
    assert "UNBLOCK:" in captured.err
    assert "windows" in captured.err


def test_malformed_docker_output_blocks_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="warning: noisy banner\n", stderr="")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    target = {
        "name": "windows",
        "kind": "docker-context",
        "context": "desktop-linux",
        "containers": [{"name": "xf_linker_backend"}],
    }

    failures = hook.check_target(target)

    assert failures
    assert "unreadable Docker inspect output" in failures[0]


def test_malformed_future_target_config_blocks_without_traceback() -> None:
    target = {
        "name": "third-pc",
        "kind": "ssh",
        "containers": [{"name": "xf_linker_future_worker"}],
    }

    failures = hook.check_target(target)

    assert failures == ["third-pc: missing required config field 'host'"]
