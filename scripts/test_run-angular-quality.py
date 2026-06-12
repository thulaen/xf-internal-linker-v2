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


def test_oxlint_runs_before_eslint() -> None:
    """oxlint is the fast pre-filter (fails the gate in milliseconds);
    eslint still runs after it for the heavy type-aware rules."""
    text = SCRIPT.read_text(encoding="utf-8")

    assert "+ oxlint" in text
    assert "+ eslint" in text
    assert text.index("+ oxlint") < text.index("+ eslint")
    # oxlint must not replace eslint.
    assert "npx eslint" in text


def test_changed_component_pulls_sibling_spec() -> None:
    """Any changed non-spec src/app/**/*.ts (component, service, plain util —
    anything) maps to its sibling .spec.ts when one exists. Both the quality
    gate and the mutation gate share this scoping."""
    for script in (SCRIPT, MUTATION_SCRIPT):
        text = script.read_text(encoding="utf-8")
        assert 'spec="${rel%.ts}.spec.ts"' in text, script.name
        assert "src/app/*.ts)" in text, script.name


def test_frontend_image_bakes_oxlint() -> None:
    """The mutation-tools image bakes a pinned oxlint into the toolchain."""
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")

    assert "npm install -g oxlint@" in text
