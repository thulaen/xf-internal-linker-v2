"""Tests for Angular quality wrapper scope transport."""

from __future__ import annotations

import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "run-angular-quality.sh"
ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DOCKERFILE = ROOT / "frontend" / "Dockerfile.prod"


def _read_or_skip(path: Path) -> str:
    """Some Dell quality runners sync only `frontend/src/app`; files outside it
    (angular.json, src/test-setup.ts) are absent there. Skip rather than fail
    when the file was not synced into the runner."""
    if not path.exists():
        import pytest

        pytest.skip(f"{path} not synced to this runner")
    return path.read_text(encoding="utf-8")


def test_angular_unit_tests_run_on_vitest_not_karma() -> None:
    """The unit-test path uses Angular's Vitest builder, not the Karma builder."""
    ng = json.loads(_read_or_skip(ROOT / "frontend" / "angular.json"))
    test_target = ng["projects"]["xf-internal-linker-frontend"]["architect"]["test"]
    assert test_target["builder"] == "@angular/build:unit-test"
    assert test_target["options"]["runner"] == "vitest"
    # The quality script no longer threads Karma's parallel-executor env.
    assert "KARMA_PARALLEL_EXECUTORS" not in SCRIPT.read_text(encoding="utf-8")


def test_vitest_setup_supplies_zone_fakeasync_and_jsdom_polyfills() -> None:
    """test-setup.ts must load zone.js/testing, install the Vitest ProxyZone
    patch that makes fakeAsync work, and polyfill the browser APIs jsdom lacks."""
    setup = _read_or_skip(ROOT / "frontend" / "src" / "test-setup.ts")
    assert "zone.js/testing" in setup
    assert "ProxyZoneSpec" in setup  # fakeAsync needs a ProxyZone under Vitest
    assert "IntersectionObserver" in setup
    assert "getContext" in setup  # canvas mock for ECharts


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
    """Pre-push Angular mutation = Stryker on Dell, scoped to the changed
    source files via --mutate, with the command runner driving the Vitest
    unit-test path (STRYKER_TEST_INCLUDES) per mutant."""
    text = MUTATION_SCRIPT.read_text(encoding="utf-8")

    assert "npx stryker run" in text
    assert "--mutate" in text
    assert "STRYKER_TEST_INCLUDES" in text


def test_stryker_uses_command_runner_not_karma() -> None:
    """Stryker drives Vitest via its built-in command runner (npm run test:ci),
    not the retired Karma runner."""
    cfg = json.loads(_read_or_skip(ROOT / "frontend" / "stryker.config.json"))
    assert cfg["testRunner"] == "command"
    assert "karma" not in cfg
    assert "test:ci" in cfg["commandRunner"]["command"]


def test_frontend_quality_image_installs_git_for_policy_helpers() -> None:
    text = _read_or_skip(FRONTEND_DOCKERFILE)

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
    text = _read_or_skip(FRONTEND_DOCKERFILE)

    assert "npm install -g oxlint@" in text
