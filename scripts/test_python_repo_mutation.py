"""Tests for repo-level Python mutmut wiring."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_repo_python_mutation_runner_exists_and_uses_docker_mutmut() -> None:
    runner = read("scripts/run-python-repo-mutation.sh")

    assert "quality_docker_compose_run python-repo-mutation backend" in runner
    assert "/tmp/xf-mutmut-repo-scope" in runner
    assert "mutmut run --max-children" in runner
    assert "actual == 100.0" in runner
    assert "docker compose exec" not in runner


def test_repo_python_mutation_scopes_scripts_and_githooks() -> None:
    runner = read("scripts/run-python-repo-mutation.sh")

    assert '^scripts/.*\\.py$' in runner
    assert '^\\.githooks/.*\\.py$' in runner
    assert "COMMIT_SCOPE_PATHS" in runner
    assert "--mode" in runner
    assert "COMMIT_SCOPE_MODE=" in runner
    assert "repo-mutmut:no-changed-targets" in runner
    assert "XF_TURBO_MUTATION" in runner
    assert "repo-mutmut:delegated-to-turbo" in runner


def test_precommit_wires_repo_python_mutation_before_language_quality() -> None:
    precommit = read("scripts/precommit-docker.sh")

    gate = "run_hard_gate run-python-repo-mutation bash scripts/run-python-repo-mutation.sh"
    assert gate in precommit
    assert precommit.index(gate) < precommit.index(
        "run_hard_gate run-python-quality bash scripts/run-python-quality.sh"
    )
