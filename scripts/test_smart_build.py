import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


class FakeRunner:
    def __init__(self, unavailable=None, current_context="desktop-linux"):
        self.commands = []
        self.unavailable = set(unavailable or [])
        self.current_context = current_context

    def __call__(self, command):
        self.commands.append(command)
        if command == ["docker", "context", "show"]:
            return 0, f"{self.current_context}\n", ""
        if command[:3] == ["docker", "buildx", "inspect"] and command[3] in self.unavailable:
            return 1, "", f"builder {command[3]} missing"
        return 0, "ok", ""


def test_non_gpu_build_uses_mint_builder_and_never_cloud():
    """Given ordinary build, When helper runs, Then Mint builder is selected."""
    from scripts.smart_build import run

    runner = FakeRunner()

    exit_code = run(["--target", "backend", "--", "--progress=plain"], runner=runner)

    assert exit_code == 0
    assert ["docker", "buildx", "inspect", "mint"] in runner.commands
    assert ["docker", "--context", "mint", "compose", "build", "--progress=plain", "backend"] in runner.commands
    assert not any(command[:3] == ["docker", "context", "use"] for command in runner.commands)
    assert all("cloud" not in command for command in runner.commands)


def test_gpu_flag_uses_desktop_linux_and_checks_gpu_first():
    """Given GPU build, When helper runs, Then local GPU builder is selected."""
    from scripts.smart_build import run

    runner = FakeRunner()

    exit_code = run(["--gpu", "--target", "findbugs-gpu"], runner=runner)

    assert exit_code == 0
    assert ["docker", "buildx", "inspect", "desktop-linux"] in runner.commands
    assert ["docker", "--context", "desktop-linux", "run", "--rm", "--gpus=all", "nvidia/cuda:12.4.1-base-ubuntu22.04", "nvidia-smi"] in runner.commands
    assert ["docker", "--context", "desktop-linux", "compose", "build", "findbugs-gpu"] in runner.commands
    assert not any(command[:3] == ["docker", "context", "use"] for command in runner.commands)


def test_gpu_target_from_config_uses_windows_local():
    """Given configured GPU target, When helper runs, Then local builder is selected."""
    from scripts.smart_build import run

    runner = FakeRunner()

    exit_code = run(["--target", "llama-gpu"], runner=runner)

    assert exit_code == 0
    assert ["docker", "--context", "desktop-linux", "compose", "build", "llama-gpu"] in runner.commands


def test_mint_unavailable_fails_closed_without_windows_or_cloud_fallback(capsys):
    """Given Mint is unavailable, When ordinary build runs, Then helper fails closed."""
    from scripts.smart_build import run

    runner = FakeRunner(unavailable={"mint"})

    exit_code = run(["--target", "backend"], runner=runner)

    assert exit_code == 2
    assert ["docker", "context", "use", "desktop-linux"] not in runner.commands
    assert all("cloud" not in command for command in runner.commands)
    assert "Mint builder is not available" in capsys.readouterr().err


def test_select_only_switches_builder_without_running_build():
    """Given select-only mode, When helper runs, Then no image build starts."""
    from scripts.smart_build import run

    runner = FakeRunner()

    exit_code = run(["--select-only", "--target", "backend"], runner=runner)

    assert exit_code == 0
    assert not any(command[:3] == ["docker", "context", "use"] for command in runner.commands)
    assert not any("compose" in command and "build" in command for command in runner.commands)


def test_routing_config_disables_paid_cloud_builder_by_default():
    """Given routing config, When read, Then paid cloud builders are disabled."""
    config = json.loads((ROOT / "config/docker-build-routing.json").read_text(encoding="utf-8"))

    assert config["builders"]["general"] == "mint"
    assert config["builders"]["gpu_local"] == "desktop-linux"
    assert config["fallback_policy"] == "fail_closed"
    assert "cloud" in config["disabled_builders"]


@pytest.mark.parametrize("filename", ["AGENTS.md", "CLAUDE.md", "CODEX.md", "GEMINI.md"])
def test_agent_docs_do_not_reference_old_auto_select_builder(filename):
    """Given agent docs, When read, Then old timed auto-switcher is gone."""
    text = (ROOT / filename).read_text(encoding="utf-8")

    assert "auto-select-builder.ps1" not in text
    assert "scripts/build-smart.ps1" in text
