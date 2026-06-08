from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch


def _load_check_rust_mandate():
    """Load the hook logic module by file path so this test runs under the
    standard ``pytest .githooks/`` invocation (no dependency on .githooks being
    on sys.path), matching the repo's other hook tests."""
    hooks_dir = Path(__file__).resolve().parent
    helpers_spec = importlib.util.spec_from_file_location(
        "_hook_helpers", hooks_dir / "_hook_helpers.py"
    )
    helpers_mod = importlib.util.module_from_spec(helpers_spec)
    sys.modules["_hook_helpers"] = helpers_mod
    helpers_spec.loader.exec_module(helpers_mod)
    spec = importlib.util.spec_from_file_location(
        "check_rust_mandate", hooks_dir / "check_rust_mandate.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_rust_mandate"] = module
    spec.loader.exec_module(module)
    return module


check_rust_mandate = _load_check_rust_mandate()


def test_wrapper_entrypoint_loads_in_fresh_interpreter_without_crashing():
    """The check-rust-mandate.py wrapper must IMPORT cleanly in a fresh
    `python check-rust-mandate.py` process where the logic module is NOT already
    imported (exactly how git invokes the hook).

    The logic module defines a @dataclass; dataclasses resolves field
    annotations via sys.modules[cls.__module__]. A module loaded with
    module_from_spec is not auto-registered, so the wrapper must register it in
    sys.modules before exec_module. The crash (AttributeError on a None lookup)
    happened at module-load time — before any git check — so it shows up as a
    traceback regardless of what is staged. Running in a subprocess is what
    reproduces the fresh-process condition that this warm test process masks.

    The subprocess runs with cwd + PYTHONPATH set to the .githooks directory so
    the sibling `_hook_helpers` import resolves exactly as it does for the real
    git hook (which runs from the hooks directory).
    """
    githooks_dir = Path(check_rust_mandate.__file__).resolve().parent
    wrapper_path = githooks_dir / "check-rust-mandate.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(githooks_dir) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", f"import runpy; runpy.run_path(r'{wrapper_path}')"],
        cwd=str(githooks_dir),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    # The only thing this guards is the module-load dataclass crash; an
    # AttributeError traceback means the wrapper failed to register the logic
    # module in sys.modules before the @dataclass resolved its annotations.
    assert "AttributeError" not in proc.stderr, proc.stderr
    assert "object has no attribute '__dict__'" not in proc.stderr, proc.stderr


def _make_workspaces(tmp_path: Path, *names: str) -> None:
    """Create the on-disk workspace dirs the gate checks for existence."""
    for name in names:
        (tmp_path / name).mkdir(parents=True, exist_ok=True)


def _passing_run_factory(calls: list[list[str]]):
    """A subprocess.run double that records every call and always succeeds.

    The coverage step now shells scripts/run-rust-coverage.sh (the ratchet),
    so a passing coverage run is simply returncode 0 with the ratchet's
    own stdout — there is no TOTAL table to parse anymore.
    """

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = Mock()
        result.returncode = 0
        result.stdout = "[run-rust-coverage] line coverage 72.00% (floor now 72.0%)\n"
        result.stderr = ""
        return result

    return fake_run


# ── skip when no Rust files are staged ────────────────────────────────────────


def test_skips_when_no_rust_files_staged(tmp_path: Path):
    with patch.object(check_rust_mandate, "staged_paths", return_value=["README.md"]):
        assert check_rust_mandate.main(tmp_path) == 0


# ── speccheck is still gated (regression guard) ───────────────────────────────


def test_fires_on_speccheck_change(tmp_path: Path):
    _make_workspaces(tmp_path, "services/speccheck")
    calls: list[list[str]] = []
    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["services/speccheck/crates/parser/src/lib.rs"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=_passing_run_factory(calls)):
            assert check_rust_mandate.main(tmp_path) == 0
    flattened = "\n".join(" ".join(call) for call in calls)
    assert "/repo/services/speccheck" in flattened


def test_blocks_when_required_rust_command_fails_on_speccheck(tmp_path: Path):
    _make_workspaces(tmp_path, "services/speccheck")
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = Mock()
        result.returncode = 1 if any("clippy" in part for part in cmd) else 0
        result.stdout = ""
        result.stderr = "warning: clippy failed"
        return result

    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["services/speccheck/crates/parser/src/lib.rs"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=fake_run):
            assert check_rust_mandate.main(tmp_path) == 2
    assert calls


# ── NEW: the gate fires on rust/**/*.rs and rust/**/Cargo.* changes ───────────


def test_fires_on_rust_kernels_rs_change(tmp_path: Path):
    _make_workspaces(tmp_path, "rust")
    calls: list[list[str]] = []
    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["rust/extensions/l2norm/src/lib.rs"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=_passing_run_factory(calls)):
            assert check_rust_mandate.main(tmp_path) == 0
    assert calls, "the gate must run commands when a rust/ source file is staged"
    flattened = "\n".join(" ".join(call) for call in calls)
    assert "/repo/rust" in flattened, "the gate must run its checks over the /repo/rust workspace"


def test_fires_on_rust_cargo_toml_change(tmp_path: Path):
    _make_workspaces(tmp_path, "rust")
    calls: list[list[str]] = []
    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["rust/Cargo.toml"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=_passing_run_factory(calls)):
            assert check_rust_mandate.main(tmp_path) == 0
    assert calls, "a rust/**/Cargo.* change must trip the gate too"


# ── NEW: both workspaces run when both have staged changes ────────────────────


def test_covers_both_workspaces_when_both_staged(tmp_path: Path):
    _make_workspaces(tmp_path, "services/speccheck", "rust")
    calls: list[list[str]] = []
    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=[
            "services/speccheck/crates/parser/src/lib.rs",
            "rust/extensions/l2norm/src/lib.rs",
        ],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=_passing_run_factory(calls)):
            assert check_rust_mandate.main(tmp_path) == 0
    flattened = "\n".join(" ".join(call) for call in calls)
    assert "/repo/services/speccheck" in flattened
    assert "/repo/rust" in flattened


# ── NEW: every cargo command runs on the DELL helper, not local compiled-tools ─


def _cargo_calls(calls: list[list[str]]) -> list[list[str]]:
    """Filter recorded subprocess calls down to the cargo gate steps.

    The gate now also shells a Dell reachability probe (`docker --context dell
    version`) and a source-sync pipeline (tar -> alpine extract) before any
    cargo runs. Those are infrastructure, not gate steps, so this helper keeps
    only the calls that actually invoke a cargo/ratchet command inside the Dell
    compiled-tools image.
    """
    cargo_steps = (
        "cargo ",
        "run-rust-coverage.sh",
    )
    out: list[list[str]] = []
    for call in calls:
        joined = " ".join(call)
        if "version" in call:  # the reachability probe
            continue
        if any(step in joined for step in cargo_steps):
            out.append(call)
    return out


def test_cargo_runs_on_dell_context_not_local_compiled_tools(tmp_path: Path):
    """Every cargo gate step must run on the Dell helper via `docker --context
    dell run`, never the removed local `docker compose exec compiled-tools`."""
    _make_workspaces(tmp_path, "rust")
    calls: list[list[str]] = []
    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["rust/extensions/l2norm/src/lib.rs"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=_passing_run_factory(calls)):
            assert check_rust_mandate.main(tmp_path) == 0
    cargo_calls = _cargo_calls(calls)
    assert cargo_calls, "the gate must run cargo steps when a rust/ source file is staged"
    for call in cargo_calls:
        joined = " ".join(call)
        assert "--context" in call and "dell" in call, (
            f"cargo step must target the Dell context, got: {joined}"
        )
        assert "xf-linker-compiled-tools:latest" in joined, (
            f"cargo step must run inside the Dell compiled-tools image, got: {joined}"
        )
    # The removed local container must never be invoked.
    flattened = "\n".join(" ".join(call) for call in calls)
    assert "compose exec -T compiled-tools" not in flattened, (
        "the local `docker compose exec compiled-tools` path is removed — MSI has no toolchain"
    )


def test_syncs_rust_source_to_dell_before_cargo(tmp_path: Path):
    """The gate must push the rust/ (and speccheck) source into the Dell volume
    before cargo runs, mirroring scripts/dell-rust.sh — otherwise Dell builds
    stale or missing source."""
    _make_workspaces(tmp_path, "rust")
    calls: list[list[str]] = []
    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["rust/extensions/l2norm/src/lib.rs"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=_passing_run_factory(calls)):
            assert check_rust_mandate.main(tmp_path) == 0
    flattened = "\n".join(" ".join(call) for call in calls)
    assert "xf_dell_compiled_repo" in flattened, (
        "the gate must sync source into the Dell xf_dell_compiled_repo volume"
    )


def test_fails_closed_when_dell_unreachable(tmp_path: Path, capsys):
    """If the Dell context is unreachable the gate must FAIL (Rule-F three-part),
    never skip and never fall back to a local toolchain MSI does not have."""
    _make_workspaces(tmp_path, "rust")

    def fake_run(cmd, **kwargs):
        result = Mock()
        # The Dell reachability probe (`docker --context dell version`) fails.
        if "version" in cmd:
            result.returncode = 1
            result.stdout = ""
            result.stderr = "Cannot connect to the Docker daemon at the dell context."
        else:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        return result

    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["rust/extensions/l2norm/src/lib.rs"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=fake_run):
            assert check_rust_mandate.main(tmp_path) == 2
    combined = capsys.readouterr().err
    assert "FAIL check-rust-mandate" in combined
    assert "WHY:" in combined
    assert "UNBLOCK:" in combined
    # It must NOT have attempted any cargo run after the probe failed.
    assert "Dell" in combined or "dell" in combined


# ── NEW: coverage uses the stable ratchet, never nightly / --fail-under-lines ─


def test_coverage_uses_stable_ratchet_not_nightly(tmp_path: Path):
    _make_workspaces(tmp_path, "rust")
    calls: list[list[str]] = []
    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["rust/extensions/l2norm/src/lib.rs"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=_passing_run_factory(calls)):
            assert check_rust_mandate.main(tmp_path) == 0
    flattened = "\n".join(" ".join(call) for call in calls)
    # The ratchet script is what measures coverage now.
    assert "run-rust-coverage.sh" in flattened, (
        "coverage must be measured by the ratchet script scripts/run-rust-coverage.sh"
    )
    # The old hard-100% / nightly path must be gone.
    assert "--fail-under-lines 100" not in flattened, (
        "the hard 100% line-coverage cliff must be replaced by the ratchet"
    )
    assert "+nightly" not in flattened, "the nightly-toolchain requirement must be dropped"


def test_coverage_below_target_still_passes_via_ratchet(tmp_path: Path):
    """A ~72% coverage workspace must be committable (the ratchet passes it)."""
    _make_workspaces(tmp_path, "rust")

    def fake_run(cmd, **kwargs):
        result = Mock()
        # The ratchet script exits 0 at 72% (floor held), even though < 95%.
        result.returncode = 0
        result.stdout = "[run-rust-coverage] /repo/rust: line coverage 72.00% (floor now 72.00%, target 95%)\n"
        result.stderr = ""
        return result

    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["rust/extensions/l2norm/src/lib.rs"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=fake_run):
            assert check_rust_mandate.main(tmp_path) == 0


def test_coverage_regression_below_floor_blocks(tmp_path: Path):
    """If the ratchet script exits non-zero (coverage dropped below floor), block."""
    _make_workspaces(tmp_path, "rust")

    def fake_run(cmd, **kwargs):
        result = Mock()
        is_coverage = any("run-rust-coverage.sh" in part for part in cmd)
        result.returncode = 1 if is_coverage else 0
        result.stdout = (
            "FAIL: /repo/rust coverage 60.00% dropped below its ratchet floor.\n"
            if is_coverage
            else ""
        )
        result.stderr = ""
        return result

    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["rust/extensions/l2norm/src/lib.rs"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=fake_run):
            assert check_rust_mandate.main(tmp_path) == 2


# ── NEW: mutation step is per-workspace (speccheck=catalog, rust=default) ─────


def test_mutants_command_is_per_workspace():
    speccheck = next(w for w in check_rust_mandate.RUST_WORKSPACES if w.prefix == "services/speccheck/")
    rust = next(w for w in check_rust_mandate.RUST_WORKSPACES if w.prefix == "rust/")
    speccheck_cmd = check_rust_mandate._mutants_command(speccheck)
    rust_cmd = check_rust_mandate._mutants_command(rust)
    # speccheck routes mutation runs to its integration test target.
    assert "-p speccheck-detectors" in speccheck_cmd
    assert "-- --test catalog" in speccheck_cmd
    # the rust/ kernels use inline unit tests, so no `--test catalog` selector.
    assert "-p l2norm" in rust_cmd
    assert "--test catalog" not in rust_cmd


# ── NEW: graceful degradation when a security tool is genuinely absent ────────


def test_degrades_gracefully_when_audit_tool_missing(tmp_path: Path, capsys):
    """A missing cargo-audit binary must WARN (Rule-F) and continue, not crash."""
    _make_workspaces(tmp_path, "rust")

    def fake_run(cmd, **kwargs):
        result = Mock()
        command = " ".join(cmd)
        if "cargo audit" in command:
            # Mimic `bash -lc "... cargo audit ..."` reporting a missing binary.
            result.returncode = 127
            result.stdout = ""
            result.stderr = "bash: line 1: cargo-audit: command not found"
        else:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        return result

    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["rust/extensions/l2norm/src/lib.rs"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=fake_run):
            # Missing security tool must NOT hard-fail the gate.
            assert check_rust_mandate.main(tmp_path) == 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    # A plain-English warning must be surfaced (Rule-F three parts: what / why / unblock).
    assert "WARNING" in combined
    assert "WHY:" in combined
    assert "UNBLOCK:" in combined


def test_real_finding_with_no_such_file_phrase_is_not_swallowed():
    """A genuine audit/deny finding whose text contains 'no such file or directory'
    must BLOCK — never be misclassified as a missing tool and warned-and-skipped.

    Regression (security bypass): the missing-tool heuristic keys ONLY on the
    shell 'command not found' and cargo 'error: no such command:' signals, never
    on a bare 'no such file' / 'no such command' substring that can legitimately
    appear inside a real RustSec advisory or cargo-deny rejection.
    """
    # Real RustSec advisory text that happens to contain the dangerous substring.
    assert (
        check_rust_mandate._looks_like_missing_tool(
            1, "RUSTSEC-2024-0001: vulnerable crate reads no such file or directory path"
        )
        is False
    )
    # Real cargo-deny license rejection (exit 101) mentioning 'no such command' in prose.
    assert (
        check_rust_mandate._looks_like_missing_tool(
            101, "error: license `GPL-3.0` not allowed; advice: no such command should run it"
        )
        is False
    )
    # Genuine missing-tool signals still degrade gracefully.
    assert (
        check_rust_mandate._looks_like_missing_tool(
            127, "bash: line 1: cargo-audit: command not found"
        )
        is True
    )
    assert (
        check_rust_mandate._looks_like_missing_tool(
            101, "error: no such command: `audit`"
        )
        is True
    )


def test_degrades_gracefully_when_cargo_subcommand_absent(tmp_path: Path, capsys):
    """cargo's own 'no such command: audit' (exit 101) must also degrade, not crash.

    When `cargo-audit` is not installed, cargo prints
    `error: no such command: \"audit\"` and exits 101 (not 127). This is the
    real-world shape and must be treated as a missing tool, not a finding.
    """
    _make_workspaces(tmp_path, "rust")

    def fake_run(cmd, **kwargs):
        result = Mock()
        command = " ".join(cmd)
        if "cargo deny" in command:
            result.returncode = 101
            result.stdout = ""
            result.stderr = "error: no such command: `deny`"
        else:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        return result

    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["rust/extensions/l2norm/src/lib.rs"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=fake_run):
            assert check_rust_mandate.main(tmp_path) == 0
    combined = capsys.readouterr().err
    assert "WARNING" in combined


def test_real_finding_in_graceful_step_still_blocks(tmp_path: Path):
    """A genuine audit/deny FINDING (tool present, exit non-zero) must block.

    Graceful degradation only swallows 'tool missing'. A real RustSec advisory
    or license violation is a non-missing failure and must still hard-fail.
    """
    _make_workspaces(tmp_path, "rust")

    def fake_run(cmd, **kwargs):
        result = Mock()
        command = " ".join(cmd)
        if "cargo audit" in command:
            # Tool IS installed; it found a real advisory.
            result.returncode = 1
            result.stdout = "error: 1 vulnerability found in dependencies"
            result.stderr = ""
        else:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        return result

    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["rust/extensions/l2norm/src/lib.rs"],
    ):
        with patch.object(check_rust_mandate.subprocess, "run", side_effect=fake_run):
            assert check_rust_mandate.main(tmp_path) == 2


def test_missing_required_workspace_blocks(tmp_path: Path):
    """If a staged workspace dir is missing on disk, block with a clear message."""
    # Stage a rust/ change but do NOT create rust/ on disk.
    with patch.object(
        check_rust_mandate,
        "staged_paths",
        return_value=["rust/extensions/l2norm/src/lib.rs"],
    ):
        assert check_rust_mandate.main(tmp_path) == 2
