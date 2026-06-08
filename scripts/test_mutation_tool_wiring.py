"""Tests for mutation tool wiring across local and remote runners."""

from __future__ import annotations

import importlib.util
import re
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


def test_rust_mutation_config_lists_both_workspaces() -> None:
    """config/mutation-routing.json rust block must cover /repo/rust too."""
    import json

    config = json.loads(_read("config/mutation-routing.json"))
    rust = config["languages"]["rust"]
    # A `workspaces` list (plural) is the new shape that lets cargo-mutants run
    # across every Rust workspace. Both the speccheck service and the new
    # /repo/rust kernels workspace must appear.
    workspaces = rust.get("workspaces")
    assert isinstance(workspaces, list), (
        "rust block must declare a `workspaces` list so cargo-mutants covers "
        "more than one Rust workspace"
    )
    assert "/repo/services/speccheck" in workspaces
    assert "/repo/rust" in workspaces
    # The kill-rate gate must stay at 0.90 (unchanged).
    assert config["kill_rate_gates"]["rust"] == 0.90


def test_turbo_rust_runner_loops_over_workspaces() -> None:
    """turbo_mutation._run_rust must iterate the configured workspace list."""
    text = _read("scripts/turbo_mutation.py")
    # The runner must read the plural `workspaces` key and loop over it so each
    # Rust workspace gets its own cargo-mutants run + report file.
    assert '"workspaces"' in text, (
        "turbo_mutation._run_rust must read the `workspaces` list from config"
    )


def test_turbo_rust_runner_runs_cargo_mutants_per_workspace(monkeypatch) -> None:
    """_run_rust must invoke cargo-mutants once per configured workspace."""
    turbo = _load_turbo_module()

    cfg = {
        "languages": {
            "rust": {
                "tool": "cargo-mutants",
                "workspaces": ["/repo/services/speccheck", "/repo/rust"],
                "report_host": ".tmp/rust-outcomes.json",
            }
        }
    }
    machine = {
        "name": "windows",
        "transport": "docker_local",
        "weight": 1.0,
        "max_weight": 1.0,
        "share": 1.0,
    }
    seen_cmds: list[str] = []

    def fake_run_on_machine(_machine, _container, cmd, **_kwargs):
        seen_cmds.append(cmd)
        return 0, "{}"

    monkeypatch.setattr(turbo, "_run_on_machine", fake_run_on_machine)
    monkeypatch.setattr(turbo, "_file_survivors", lambda *a, **k: "")

    turbo._run_rust(cfg, [machine], {"windows": 4}, dry_run=True)

    speccheck_runs = [c for c in seen_cmds if "/repo/services/speccheck" in c]
    rust_runs = [c for c in seen_cmds if "cd /repo/rust" in c]
    assert speccheck_runs, "cargo-mutants must run in the speccheck workspace"
    assert rust_runs, "cargo-mutants must run in the /repo/rust workspace"
    assert all("cargo mutants" in c for c in seen_cmds if "cargo mutants" in c)


def test_dell_shard_syncs_rust_workspace() -> None:
    """run-dell-quality-shard.sh must ship rust/ to the Dell volume."""
    text = _read("scripts/run-dell-quality-shard.sh")
    # The tar that seeds the Dell volume must include the rust/ tree, and the
    # remote cleanup must remove it before re-extracting, otherwise the inner
    # run-rust-quality.sh finds no /repo/rust workspace on Dell.
    assert "tar" in text
    assert re.search(r"-cf - .*\brust\b", text), (
        "run-dell-quality-shard.sh tar argument list must include rust/ so the "
        "/repo/rust workspace exists on the Dell compute shard"
    )
    assert "/repo/rust" in text, (
        "run-dell-quality-shard.sh remote cleanup (rm -rf) must remove "
        "/repo/rust before re-extracting the synced tree"
    )


def test_turbo_mutation_has_windows_and_dell_remote_e2e_paths() -> None:
    text = _read("scripts/turbo_mutation.py")
    config = _read("config/mutation-routing.json")

    # Mint is removed from compute: the Docker-context fallback remote is Dell.
    assert '"remote_context": "dell"' in config
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
