"""Tests for mutation tool wiring across local and remote runners."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _load_turbo_module():
    spec = importlib.util.spec_from_file_location(
        "turbo_mutation_for_tests",
        ROOT / "scripts" / "turbo_mutation.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_repo_owned_mutmut_command_uses_removed_paths_to_mutate_flag() -> None:
    offenders: list[str] = []
    removed_flag = "--paths" + "-to-mutate"
    paths = [
        *ROOT.joinpath("scripts").glob("*"),
        *ROOT.joinpath(".github", "workflows").glob("*"),
    ]
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if removed_flag in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_turbo_python_mutation_uses_temp_pyproject_config() -> None:
    text = _read("scripts/turbo_mutation.py")

    assert "[tool.mutmut]" in text
    assert "paths_to_mutate" in text
    assert "mutmut run --max-children" in text


def test_windows_python_mutation_uses_temp_pyproject_config() -> None:
    text = _read("scripts/run-windows-mutation.ps1")

    assert "[tool.mutmut]" in text
    assert "paths_to_mutate" in text
    assert "also_copy" in text
    assert "mutmut run --max-children" in text


def test_ci_python_mutation_uses_temp_pyproject_config() -> None:
    text = _read(".github/workflows/ci.yml")

    assert "[tool.mutmut]" in text
    assert "paths_to_mutate" in text
    assert "--max-children=2" in text or "--max-children 2" in text


def test_scoped_mutation_workflow_uses_temp_pyproject_config() -> None:
    text = _read(".github/workflows/scoped-mutation.yml")

    assert "[tool.mutmut]" in text
    assert "paths_to_mutate" in text
    assert "mutmut run --max-children" in text


def test_other_mutation_wrappers_expose_expected_tool_contracts() -> None:
    checks = {
        "scripts/run-cpp-mutation.sh": (
            "mull-runner-19",
            "Mull IR frontend pass plugin not found",
            "backend/extensions/reports/mull",
        ),
        "scripts/run-go-mutation.sh": (
            "go-mutesting not installed in this image.",
            "go-mutesting ./...",
            "report.json",
        ),
        "scripts/run-angular-quality.sh": (
            "npx stryker run",
            "/tmp/stryker.changed.config.json",
            "file_mutation_survivors",
        ),
        "scripts/run-lua-quality.sh": (
            "lua-mutmut binary is required",
            "lua-mutmut \"${lua_mutation_args[@]}\"",
            "luamut compatibility command is required",
        ),
        "scripts/run-rust-quality.sh": (
            "cargo mutants",
            "cargo-mutants not installed; skipping Rust mutation.",
            "--in-diff",
        ),
        "scripts/run-haskell-quality.sh": (
            "mucheck --timeout 60",
            "mucheck not installed; skipping Haskell mutation.",
            "WARN: mucheck exited non-zero",
        ),
    }

    for path, expected_parts in checks.items():
        text = _read(path)
        for expected in expected_parts:
            assert expected in text, f"{path} missing {expected!r}"


def test_turbo_mutation_has_windows_to_mint_and_mint_to_windows_e2e_paths() -> None:
    text = _read("scripts/turbo_mutation.py")
    config = _read("config/mutation-routing.json")

    # Legacy block retained for backward compatibility (kept green on purpose).
    assert '"remote_context": "mint"' in config
    # New weighted machines array is the primary routing source.
    assert '"machines"' in config
    assert 'docker", "--context", ctx' in text
    assert 'docker", "compose", "exec"' in text
    # The hardcoded two-thread (local+remote) loop is replaced by the weighted
    # machine fan-out — assert the new dispatch path exists instead.
    assert "_partition_weighted(" in text
    assert "_dispatch_to_machines(" in text
    assert "_select_machines(" in text
    assert "_file_survivors(" in text


def test_turbo_ssh_transport_builds_dell_compose_run_command(monkeypatch) -> None:
    turbo = _load_turbo_module()
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(turbo, "_sync_source_to_dell_for_turbo", lambda m: None)
    monkeypatch.setattr(turbo.subprocess, "run",
                        lambda cmd, **k: (calls.append(cmd), Result())[1])

    turbo._run_in_container("ssh", "compiled-tools", "echo hi", ssh_host="dell")
    argv = calls[-1]
    joined = " ".join(argv)
    assert argv[0] == "ssh"
    assert "set DOCKER_CONFIG=" in joined
    assert "docker compose run --rm --no-deps -T" in joined


def test_turbo_container_runner_builds_windows_and_mint_commands(monkeypatch) -> None:
    turbo = _load_turbo_module()
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return Result()

    monkeypatch.setattr(turbo.subprocess, "run", fake_run)

    assert turbo._run_in_container("local", "compiled-tools", "echo local") == (0, "ok")
    assert turbo._run_in_container(
        "mint", "compiled-tools", "echo remote") == (0, "ok")

    assert calls[0][:5] == ["docker", "compose", "exec", "-T", "compiled-tools"]
    assert calls[1][:7] == [
        "docker",
        "--context",
        "mint",
        "compose",
        "exec",
        "-T",
        "compiled-tools",
    ]
