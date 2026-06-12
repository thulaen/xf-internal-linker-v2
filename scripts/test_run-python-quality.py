"""TDD guard for scripts/run-python-quality.sh.

Tests that mypy type-checking is wired alongside ruff and bandit, and that
pylint stays retired (ruff's PLE rules cover pylint's error class).
"""
from __future__ import annotations

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SCRIPT = SCRIPTS / "run-python-quality.sh"


def _text() -> str:
    return SCRIPT.read_text()


def test_mypy_is_wired():
    """run-python-quality.sh must call mypy for type-checking."""
    text = _text()
    assert "mypy" in text, (
        "run-python-quality.sh must call mypy so Python type errors "
        "are caught at the same stage as ruff and bandit"
    )


def test_mypy_uses_config_file():
    """mypy must use the backend/mypy.ini config so Django stubs and exclusions apply."""
    text = _text()
    assert "mypy.ini" in text or "--config-file" in text, (
        "run-python-quality.sh must point mypy at backend/mypy.ini "
        "so django-stubs and per-module ignore_errors rules apply"
    )


def test_mypy_is_a_quality_step():
    """mypy must be logged through run_quality_step.py like ruff."""
    text = _text()
    assert "run_quality_step.py" in text and "mypy" in text, (
        "mypy must use the run_quality_step.py wrapper so its result is "
        "recorded in the quality evidence file alongside other static checks"
    )


def test_pylint_step_is_retired():
    """The CI in-container block must not run pylint — ruff's PLE rules replaced it."""
    text = _text()
    assert "pylint" not in text.lower(), (
        "run-python-quality.sh must not invoke pylint anywhere; "
        "ruff (with PLE selected in backend/pyproject.toml) is the only linter"
    )


def test_turbo_uses_supported_compose_pull_policy():
    """Turbo should avoid registry pulls with a Compose-supported run option."""
    text = _text()
    assert "--pull never" in text
    assert "--no-build" not in text
