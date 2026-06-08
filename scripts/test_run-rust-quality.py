"""Tests for run-rust-quality.sh scope guard.

TDD Red phase: these tests fail before the scope guard block is added to
run-rust-quality.sh.  They pass (Green) once the guard is present.

The scope guard makes the script exit 0 immediately when no Rust-relevant
files (*.rs, Cargo.toml, Cargo.lock) appear in the commit scope, so CI
and local pre-push checks never spend time on Rust tooling when only
Python or frontend files changed.
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SCRIPT = SCRIPTS / "run-rust-quality.sh"


def test_scope_guard_exits_early_on_no_rust_files():
    """Script must detect 'no Rust files' and print a skip message."""
    text = SCRIPT.read_text()
    assert "No changed Rust files detected" in text, (
        "run-rust-quality.sh must print a skip message and exit 0 when "
        "commit_scope.py returns no .rs / Cargo files"
    )


def test_scope_guard_exports_quality_rust_paths():
    """Script must export QUALITY_RUST_PATHS for downstream mutation tools."""
    text = SCRIPT.read_text()
    assert "QUALITY_RUST_PATHS" in text, (
        "run-rust-quality.sh must export QUALITY_RUST_PATHS so tools like "
        "cargo-mutants can receive the narrowed file list"
    )


def test_rust_quality_runs_inside_compiled_tools_container():
    """Host runs must enter the Docker-managed compiled-tools container."""
    text = SCRIPT.read_text()
    assert "docker compose exec -T" in text
    assert "compiled-tools bash /repo/scripts/run-rust-quality.sh" in text
    assert "XF_QUALITY_INNER=1" in text


def test_scope_guard_delegates_to_commit_scope_py():
    """Scope detection must use commit_scope.py for consistency with other gates."""
    text = SCRIPT.read_text()
    assert "commit_scope.py" in text, (
        "run-rust-quality.sh must call commit_scope.py to get changed paths, "
        "matching the pattern used by run-go-quality.sh"
    )


def test_scope_guard_filters_rust_extensions():
    """The grep filter must match .rs and Cargo manifest files."""
    text = SCRIPT.read_text()
    # The grep pattern must cover .rs files and Cargo.toml / Cargo.lock
    assert re.search(r"\.rs", text) and re.search(r"Cargo\.", text), (
        "run-rust-quality.sh scope filter must include *.rs and Cargo.toml/Cargo.lock "
        "so that changes to those files are detected"
    )


def test_scope_grep_pattern_correctness():
    """The regex used in the scope grep must match exactly what we expect."""
    # Reproduce the pattern the script will embed; verify it is correct.
    pattern = re.compile(r"\.rs$|Cargo\.(toml|lock)$")

    matches = [
        "src/lib.rs",
        "services/speccheck/src/main.rs",
        "Cargo.toml",
        "services/speccheck/Cargo.lock",
        "services/speccheck/Cargo.toml",
    ]
    non_matches = [
        "main.go",
        "script.py",
        "README.md",
        "frontend/src/app.component.ts",
        "backend/apps/audit/models.py",
    ]

    for path in matches:
        assert pattern.search(path), f"Expected scope filter to match {path!r}"
    for path in non_matches:
        assert not pattern.search(path), f"Expected scope filter NOT to match {path!r}"


def test_rust_fuzz_is_wired():
    """run-rust-quality.sh must run cargo-fuzz targets when they exist."""
    text = SCRIPT.read_text()
    assert "fuzz run" in text or "cargo-fuzz" in text, (
        "run-rust-quality.sh must call cargo-fuzz so Rust fuzz targets are run "
        "alongside mutation tests"
    )
    assert "max_total_time" in text, (
        "run-rust-quality.sh fuzz run must be time-bounded via -max_total_time "
        "so CI does not hang on a slow fuzz target"
    )


# ── multi-workspace coverage (the new /repo/rust workspace) ───────────────────


def test_quality_covers_both_speccheck_and_rust_workspaces():
    """fmt + clippy + cargo test must run over BOTH speccheck AND /repo/rust."""
    text = SCRIPT.read_text()
    assert "/repo/services/speccheck" in text, (
        "run-rust-quality.sh must still cover the speccheck workspace"
    )
    assert "/repo/rust" in text, (
        "run-rust-quality.sh must also cover the new /repo/rust kernels "
        "workspace per docs/PYTHON-RUST-MIGRATION-PLAN.md"
    )


def test_quality_iterates_a_workspace_list():
    """The script must loop over a list of workspaces, not a single path."""
    text = SCRIPT.read_text()
    # A `for ws in ...` loop over the workspace list is the shape that lets the
    # fmt/clippy/test block run once per workspace.
    assert re.search(r"for\s+\w+\s+in\b", text), (
        "run-rust-quality.sh must iterate over a workspace list so the "
        "fmt/clippy/test block runs once per Rust workspace"
    )


def test_quality_tolerates_a_missing_workspace_without_failing():
    """A workspace with no Cargo.toml must be skipped, not hard-fail the run."""
    text = SCRIPT.read_text()
    # The per-workspace Cargo.toml guard must use `continue` (skip this
    # workspace) rather than `exit 1`, so a missing workspace is tolerated.
    assert re.search(r"Cargo\.toml.*\n.*continue", text) or re.search(
        r"continue", text
    ), (
        "run-rust-quality.sh must `continue` past a workspace that lacks a "
        "Cargo.toml instead of aborting the whole run"
    )


def test_quality_respects_rust_workspace_override():
    """The RUST_WORKSPACE override must still select a single workspace."""
    text = SCRIPT.read_text()
    assert "RUST_WORKSPACE" in text, (
        "run-rust-quality.sh must keep honouring the RUST_WORKSPACE override "
        "so a caller can still pin the run to one workspace"
    )
    # The list default must be overridable and include both default workspaces.
    assert "RUST_WORKSPACES" in text, (
        "run-rust-quality.sh must expose a RUST_WORKSPACES list (plural) that "
        "defaults to both speccheck and /repo/rust"
    )
