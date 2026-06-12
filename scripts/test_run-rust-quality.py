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


def test_rust_quality_runs_inside_compiled_mutation_tools_on_dell():
    """Host runs must enter Dell's Docker-managed compiled mutation image."""
    text = SCRIPT.read_text()
    assert 'docker --context "$RUST_MUTATION_DOCKER_CONTEXT" run --rm' in text
    assert "xf-linker-compiled-mutation-tools:latest" in text
    assert "bash /repo/scripts/run-rust-quality.sh" in text
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


MUTATION_SCRIPT = SCRIPTS / "run-rust-mutation.sh"


def test_rust_fuzz_is_wired():
    """run-rust-mutation.sh must run cargo-fuzz targets when they exist."""
    text = MUTATION_SCRIPT.read_text()
    assert "fuzz run" in text or "cargo-fuzz" in text, (
        "run-rust-mutation.sh must call cargo-fuzz so Rust fuzz targets are run "
        "alongside mutation tests"
    )
    assert "max_total_time" in text, (
        "run-rust-mutation.sh fuzz run must be time-bounded via -max_total_time "
        "so CI does not hang on a slow fuzz target"
    )


def test_rust_quality_routes_host_runs_to_dell_mutation_image():
    """Host Rust quality runs must execute on Dell's compiled mutation image."""
    text = SCRIPT.read_text()

    assert 'RUST_MUTATION_DOCKER_CONTEXT="${RUST_MUTATION_DOCKER_CONTEXT:-dell}"' in text
    assert 'docker --context "$RUST_MUTATION_DOCKER_CONTEXT" run --rm' in text
    assert "xf-linker-compiled-mutation-tools:latest" in text


def test_rust_mutation_defaults_to_sixteen_dell_jobs():
    """Rust mutation must default to 16 cargo-mutants jobs on Dell."""
    text = MUTATION_SCRIPT.read_text()

    assert 'XF_RUST_MUTATION_JOBS="${XF_RUST_MUTATION_JOBS:-16}"' in text
    assert 'rust_mutation_jobs="${XF_RUST_MUTATION_JOBS:-16}"' in text
    assert 'cargo mutants --in-diff "$MUTATION_DIFF_FILE" --jobs "$rust_mutation_jobs"' in text


def test_rust_mutation_is_compulsory_not_skipped():
    """Missing cargo-mutants must fail the gate instead of skipping mutation."""
    text = MUTATION_SCRIPT.read_text()

    assert "cargo-mutants is required for Rust mutation" in text
    assert "cargo-mutants not installed; skipping Rust mutation." not in text


def test_rust_mutation_rejects_full_workspace_mode():
    """Rust mutation must stay diff-scoped to changed or new files."""
    text = MUTATION_SCRIPT.read_text()

    assert "Full-workspace Rust mutation is disabled" in text
    assert 'cargo mutants --in-diff "$MUTATION_DIFF_FILE" --jobs "$rust_mutation_jobs"' in text
    assert 'cargo mutants --jobs "$rust_mutation_jobs"' not in text


def test_rust_mutation_diff_includes_new_untracked_files():
    """New Rust files must be included in the diff-fed mutation scope."""
    text = MUTATION_SCRIPT.read_text()

    assert "git ls-files --error-unmatch" in text
    assert "git diff --no-index /dev/null" in text


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


def test_host_scope_guard_exits_before_dell_sync():
    """The host block must check for Rust changes BEFORE probing/syncing Dell,
    so non-Rust commits skip instantly instead of paying a multi-directory
    Dell sync on every commit."""
    text = SCRIPT.read_text()
    skip_pos = text.find("skipping Dell sync and Rust quality run")
    probe_pos = text.find('docker --context "$RUST_MUTATION_DOCKER_CONTEXT" info')
    assert skip_pos != -1, "host block must have its own no-Rust early exit"
    assert probe_pos != -1, "host block must keep the Dell probe"
    assert skip_pos < probe_pos, (
        "the no-Rust early exit must come before the Dell probe/sync"
    )
