"""Tests for Angular quality wrapper scope transport."""

from __future__ import annotations

from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "run-angular-quality.sh"


def test_angular_wrapper_passes_large_scope_by_file() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "QUALITY_FRONTEND_LINT_TARGETS_FILE" in text
    assert 'QUALITY_FRONTEND_LINT_TARGETS="$frontend_lint_targets"' not in text
    assert "read_target_file" in text


def test_angular_wrapper_delegates_mutation_in_turbo_mode() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'XF_TURBO_MUTATION="${XF_TURBO_MUTATION:-0}"' in text
    assert "Angular mutation delegated to turbo coordinator" in text
