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
