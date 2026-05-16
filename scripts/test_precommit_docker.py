"""Tests for the normal commit hook wrapper."""

from __future__ import annotations

from pathlib import Path


def test_hard_gates_run_before_language_quality() -> None:
    text = Path("scripts/precommit-docker.sh").read_text(encoding="utf-8")

    first_quality = min(
        text.index("bash scripts/run-angular-quality.sh"),
        text.index("bash scripts/run-python-quality.sh"),
        text.index("bash scripts/run-cpp-quality.sh"),
        text.index("bash scripts/run-go-quality.sh"),
    )
    hard_gates = (
        "run_hard_gate python .githooks/check-code-review-lessons.py",
        "run_hard_gate python .githooks/check-registry-read.py",
        "run_hard_gate python .githooks/check-paper-trail-read.py",
        "run_hard_gate python .githooks/check-deferral-filed.py",
        "run_hard_gate python .githooks/check-profiling-proof.py",
        "run_hard_gate python .githooks/check-perf-proof.py",
        "run_hard_gate python .githooks/check-tdd-cycle.py",
        "run_hard_gate python .githooks/check-spec-citation.py",
        "run_hard_gate python .githooks/check-scoped-lessons.py",
        "run_hard_gate python .githooks/check-debug-code.py",
        "run_hard_gate python .githooks/check-junk-files.py",
    )
    for gate in hard_gates:
        assert gate in text
        assert text.index(gate) < first_quality

    assert text.index(".githooks/check-profiling-proof.py") < text.index(
        ".githooks/check-perf-proof.py"
    )


def test_hard_gates_collect_failures_before_exiting() -> None:
    text = Path("scripts/precommit-docker.sh").read_text(encoding="utf-8")

    assert "hard_gate_status=0" in text
    assert "run_hard_gate()" in text
    assert 'if [[ "$hard_gate_status" -ne 0 ]]; then' in text
