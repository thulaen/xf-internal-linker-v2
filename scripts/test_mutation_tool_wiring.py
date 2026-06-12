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


def test_turbo_python_mutation_has_no_whole_apps_default() -> None:
    text = _read("scripts/turbo_mutation.py")

    assert 'os.environ.get("XF_MUTMUT_PATHS", "apps/")' not in text
    assert "_changed_python_mutation_paths" in text
    assert "No changed Python mutation targets" in text


def test_backend_mutation_image_pins_multicore_mutmut() -> None:
    text = _read("backend/Dockerfile")

    assert "mutmut==3.5.0" in text
    assert "mutmut==2.5.1" not in text


def test_compiled_mutation_image_requires_cargo_mutants() -> None:
    dockerfile = _read("tools/mutation/Dockerfile")
    compose = _read("docker-compose.yml")

    assert "cargo mutants --version" in dockerfile
    assert "command -v cargo-mutants" in compose


def test_python_mutation_runner_is_dell_only() -> None:
    """Pre-push Python mutation runs on Dell only — no local container, no
    turbo delegate, with the >=90% kill gate and content-hash pair caching."""
    text = _read("scripts/run-python-mutation.sh")

    assert 'PYTHON_MUTATION_DOCKER_CONTEXT="${PYTHON_MUTATION_DOCKER_CONTEXT:-dell}"' in text
    assert 'docker --context "$PYTHON_MUTATION_DOCKER_CONTEXT"' in text
    assert "xf_python_mutation_repo" in text
    assert "xf-linker-backend-mutation-tools" in text
    assert ">= 90.0" in text
    assert "filter-pairs --tool mutmut" in text
    assert "record-pairs --tool mutmut" in text
    assert "[tool.mutmut]" in text
    assert "paths_to_mutate" in text
    assert "mutmut run --max-children" in text
    assert "XF_TURBO_MUTATION" not in text
    assert "backend-quality" not in text
    # The Windows-local mutation runner is gone for good.
    assert not (ROOT / "scripts" / "run-windows-mutation.ps1").exists()


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
    # Only the two surviving mutation wrappers: Angular (TypeScript/Stryker)
    # and Rust (cargo-mutants). C++, Go, and Haskell removed per ADR 0007.
    checks = {
        "scripts/run-angular-mutation.sh": (
            "npx stryker run",
        ),
        "scripts/run-rust-mutation.sh": (
            "cargo mutants",
            "cargo-mutants is required for Rust mutation",
            "--in-diff",
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


def test_turbo_rust_runner_defaults_dell_to_sixteen_jobs(monkeypatch) -> None:
    """Dell Rust mutation should default to 16 cargo-mutants jobs."""
    turbo = _load_turbo_module()

    cfg = {
        "languages": {
            "rust": {
                "tool": "cargo-mutants",
                "workspaces": ["/repo/rust"],
                "report_host": ".tmp/rust-outcomes.json",
            }
        }
    }
    machine = {
        "name": "dell",
        "transport": "docker_context",
        "context": "dell",
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

    turbo._run_rust(cfg, [machine], {"dell": 20}, dry_run=True)

    assert any("cargo mutants --in-diff" in c and "--jobs 16" in c for c in seen_cmds)


def test_turbo_rust_runner_uses_diff_scope(monkeypatch) -> None:
    """Turbo Rust mutation must use --in-diff, not whole-workspace mutation."""
    turbo = _load_turbo_module()

    cfg = {
        "languages": {
            "rust": {
                "tool": "cargo-mutants",
                "workspaces": ["/repo/rust"],
                "report_host": ".tmp/rust-outcomes.json",
            }
        }
    }
    machine = {
        "name": "dell",
        "transport": "docker_context",
        "context": "dell",
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

    turbo._run_rust(cfg, [machine], {"dell": 20}, dry_run=True)

    assert any("cargo mutants --in-diff" in c for c in seen_cmds)
    assert not any("cargo mutants --jobs" in c for c in seen_cmds)


def test_rust_quality_syncs_rust_workspace_to_dell() -> None:
    """run-rust-quality.sh must ship rust/ to the Dell volume before running."""
    text = _read("scripts/run-rust-quality.sh")
    # The host-side re-exec tars the source roots into the Dell volume, and the
    # remote cleanup must remove the old tree before re-extracting, otherwise the
    # inner run-rust-quality.sh finds no /repo/rust workspace on Dell.
    assert "tar -cf -" in text
    assert re.search(r"sync_roots=\([^)]*\brust\b", text), (
        "run-rust-quality.sh sync_roots must include rust/ so the "
        "/repo/rust workspace exists on the Dell compute shard"
    )
    assert "/repo/rust" in text, (
        "run-rust-quality.sh remote cleanup (rm -rf) must remove "
        "/repo/rust before re-extracting the synced tree"
    )


def test_turbo_mutation_has_dell_remote_e2e_paths() -> None:
    text = _read("scripts/turbo_mutation.py")
    config = _read("config/mutation-routing.json")

    # Dell is the only compute machine; the legacy split block still names it.
    assert '"remote_context": "dell"' in config
    # New weighted machines array is the primary routing source.
    assert '"machines"' in config
    assert 'docker", "--context", context' in text
    assert 'docker", "compose", "exec"' in text
    # The hardcoded two-thread (local+remote) loop is replaced by the weighted
    # machine fan-out — assert the new dispatch path exists instead.
    assert "_partition_weighted(" in text
    assert "_dispatch_to_machines(" in text
    assert "_select_machines(" in text
    assert "_file_survivors(" in text


def test_turbo_ssh_transport_fails_closed_without_subprocess(monkeypatch) -> None:
    turbo = _load_turbo_module()

    def boom(*args, **kwargs):
        raise AssertionError("ssh transport must never spawn a subprocess")

    monkeypatch.setattr(turbo.subprocess, "run", boom)
    rc, out = turbo._run_in_container("ssh", "compiled-tools", "echo hi")
    assert rc == 1
    assert "is not allowed" in out
    assert "Dell docker context" in out


def test_turbo_container_runner_builds_dell_context_command_only(monkeypatch) -> None:
    turbo = _load_turbo_module()
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(turbo.subprocess, "run",
                        lambda cmd, **k: (calls.append(cmd), Result())[1])

    assert turbo._run_in_container(
        "docker_context", "compiled-tools", "echo hi", context="dell") == (0, "ok")
    assert calls[0][:7] == [
        "docker",
        "--context",
        "dell",
        "run",
        "--rm",
        "-v",
        "xf_python_mutation_repo:/repo",
    ]

    for transport in ("local", "docker_local", "mint"):
        rc, out = turbo._run_in_container(transport, "compiled-tools", "echo hi")
        assert rc == 1 and "is not allowed" in out
    assert len(calls) == 1  # only the docker_context call shelled out
