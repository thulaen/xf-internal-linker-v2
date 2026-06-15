"""Contract tests for the property-based-testing (PBT) pre-commit gate.

These assert the wiring, not the property tests themselves: PBT is Dell-only,
scoped to changed files, capped by a shared 5-minute budget, and hard-blocks at
pre-commit after the unit-test gates (so it reuses their warm Dell volumes).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run-pbt.sh"
PRECOMMIT = ROOT / "scripts" / "precommit-docker.sh"


def test_pbt_runner_is_dell_only() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert ". scripts/_dell_only_guard.sh" in text
    assert "xf_require_remote_context run-pbt" in text


def test_pbt_has_a_five_minute_total_budget() -> None:
    """One shared wall-clock ceiling across both lanes (5 min = 300s)."""
    text = RUNNER.read_text(encoding="utf-8")
    assert 'PBT_TIMEOUT="${PBT_TIMEOUT:-300}"' in text
    assert "_remaining()" in text
    # Both lanes run under the remaining budget, not a fresh per-lane timeout.
    assert text.count('timeout "$PBT_REMAINING"') == 2


def test_pbt_is_scoped_not_whole_codebase() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "commit_scope.py paths" in text
    assert "tests_pbt_" in text          # Python property-test convention
    assert "rust/extensions/" in text    # Rust crate scoping


def test_pbt_empty_scope_reaches_skip_branch() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert text.count("sort -u || true") == 2
    assert "[run-pbt] No changed property-test scope -- skipping." in text


def test_pbt_runs_fast_profile_and_parallel() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "HYPOTHESIS_PROFILE" in text
    assert "PROPTEST_CASES" in text
    assert "-n auto" in text             # adaptive xdist parallelism


def test_pbt_reuses_warm_unit_test_volumes() -> None:
    """Reuses the gates' synced trees (overlay only changed files), not a full
    re-upload — keeps the added pre-commit cost small."""
    text = RUNNER.read_text(encoding="utf-8")
    assert "xf_test_repo" in text
    assert "xf_rust_mutation_repo" in text


def test_pbt_is_hard_gate_after_unit_tests() -> None:
    """PBT hard-blocks the commit and runs AFTER the Python/Rust unit-test gates
    so their Dell volumes are already warm."""
    text = PRECOMMIT.read_text(encoding="utf-8")
    assert "run_hard_gate run-pbt bash scripts/run-pbt.sh" in text
    assert text.index("run-rust-quality") < text.index("run_hard_gate run-pbt")


def test_hypothesis_profiles_and_marker_registered() -> None:
    conftest = (ROOT / "backend" / "conftest.py").read_text(encoding="utf-8")
    assert 'register_profile("fast"' in conftest
    assert 'register_profile("ci"' in conftest
    ini = (ROOT / "backend" / "pytest.ini").read_text(encoding="utf-8")
    assert "property:" in ini
