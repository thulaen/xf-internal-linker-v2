"""Tests for repo-level Python mutmut wiring."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_repo_python_mutation_runner_exists_and_uses_docker_mutmut() -> None:
    runner = read("scripts/run-python-repo-mutation.sh")

    assert "quality_docker_compose_run python-repo-mutation backend-mutation-tools" in runner
    assert "xf-linker-backend-mutation-tools:latest" in runner
    assert '"${docker_cmd[@]}" "${docker_context_args[@]}" run --rm "$image" python' in runner
    assert "/tmp/xf-mutmut-repo-scope" in runner
    assert "mutmut run --max-children" in runner
    assert "XF_MUTMUT_CHILDREN" in runner
    assert "os.cpu_count()" in runner
    assert "kill_rate >= 90.0" in runner
    assert "docker compose exec" not in runner
    assert "repo-mutmut:tool-missing" in runner
    assert "repo-mutmut:python-missing" in runner
    assert "repo-mutmut:docker-missing" in runner
    assert "python_cmd=(py -3)" in runner
    assert "docker_cmd=(docker.exe)" in runner


def test_repo_python_mutation_scopes_scripts_and_githooks() -> None:
    runner = read("scripts/run-python-repo-mutation.sh")

    assert '^scripts/.*\\.py$' in runner
    assert '^\\.githooks/.*\\.py$' in runner
    assert "COMMIT_SCOPE_PATHS" in runner
    assert "--paths" in runner
    assert "explicit_paths" in runner
    assert "test_bazel_default.py" in runner
    assert "grep -Ev" in runner
    assert "--mode" in runner
    assert "COMMIT_SCOPE_MODE=" in runner
    assert "repo-mutmut:no-changed-targets" in runner
    assert '"${docker_cmd[@]}" "${docker_context_args[@]}" run --rm' in runner
    assert "repo-mutmut:dell-required" in runner


def test_repo_python_mutation_uses_all_changed_existing_files_not_first_path() -> None:
    runner = read("scripts/run-python-repo-mutation.sh")

    assert "changed_paths_json" in runner
    assert "paths_to_mutate = changed_paths" in runner
    assert "test_targets = test_target.split()" in runner
    assert "'tests_dir = ' + json.dumps(test_targets)" in runner
    assert "tools/quality" in runner
    assert "if [ $? -eq 0 ]" not in runner
    assert "head -n 1" not in runner
    assert "[[ -f \"$path\" ]]" in runner


def test_prepush_wires_repo_python_mutation() -> None:
    ps1 = read("scripts/run-scoped-static-quality.ps1")

    assert '"scripts/run-python-repo-mutation.sh"' in ps1
