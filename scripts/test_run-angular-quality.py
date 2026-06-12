"""Tests for Angular quality wrapper scope transport."""

from __future__ import annotations

from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "run-angular-quality.sh"
FRONTEND_DOCKERFILE = Path(__file__).resolve().parents[1] / "frontend" / "Dockerfile.prod"


MUTATION_SCRIPT = Path(__file__).resolve().parent / "run-angular-mutation.sh"


def test_angular_quality_is_dell_only_lint_and_tests() -> None:
    """Pre-commit Angular quality = eslint + stylelint + unit tests on Dell.
    No mutation here — Stryker lives in run-angular-mutation.sh (pre-push)."""
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'docker --context "$ANGULAR_DOCKER_CONTEXT"' in text
    assert "eslint" in text
    assert "stylelint" in text
    assert "test:ci" in text
    assert "npx stryker" not in text


def test_angular_mutation_script_owns_stryker() -> None:
    """Pre-push Angular mutation = incremental Stryker on Dell."""
    text = MUTATION_SCRIPT.read_text(encoding="utf-8")

    assert "npx stryker run" in text
    assert "--incremental" in text


def test_frontend_quality_image_installs_git_for_policy_helpers() -> None:
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")

    assert "git" in text
