"""Tests for repo-level Python mutmut wiring."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_repo_python_mutation_runner_exists_and_uses_docker_mutmut() -> None:
    runner = read("tools/quality/internal/run-python-repo-mutation.sh")

    assert "quality_docker_compose_run python-repo-mutation backend-mutation-tools" in runner
    assert "xf-linker-backend-mutation-tools:latest" in runner
    assert 'mutation_context="${PYTHON_REPO_MUTATION_DOCKER_CONTEXT' in runner
    assert 'docker_context_args=(--context "$mutation_context")' in runner
    assert '"${docker_cmd[@]}" "${docker_context_args[@]}" run --rm "$image" python' in runner
    assert "/tmp/xf-mutmut-repo-scope" in runner
    assert "mutmut run --max-children" in runner
    assert "XF_MUTMUT_CHILDREN" in runner
    assert "XF_QUALITY_CORES" in runner
    assert "os.cpu_count()" in runner
    assert "min(16" not in runner
    assert "mutmut-results.txt" in runner
    assert "survived|no tests" in runner
    assert "docker compose exec" not in runner
    assert "repo-mutmut:tool-missing" in runner
    assert "repo-mutmut:python-missing" in runner
    assert "repo-mutmut:docker-missing" in runner
    assert "python_cmd=(py -3)" in runner
    assert "docker_cmd=(docker.exe)" in runner


def test_repo_python_mutation_scopes_scripts_and_githooks() -> None:
    runner = read("tools/quality/internal/run-python-repo-mutation.sh")

    assert '^scripts/.*\\.py$' in runner
    assert '^\\.githooks/.*\\.py$' in runner
    assert "COMMIT_SCOPE_PATHS" in runner
    assert "--paths" in runner
    assert "explicit_paths" in runner
    assert "--mode" in runner
    assert "COMMIT_SCOPE_MODE=" in runner
    assert "repo-mutmut:no-changed-targets" in runner
    assert '"${docker_cmd[@]}" "${docker_context_args[@]}" run --rm' in runner
    assert "repo-mutmut:dell-required" in runner
    assert "test_*.py|tests_*.py) continue" in runner
    assert "MUTMUT_CHANGED_JSON" in runner
    assert "MUTMUT_TESTS_JSON" in runner
    assert "MUTMUT_SCOPE_HASH" in runner
    assert 'runner = "python -m pytest -q "' in runner
    assert "MUTMUT_REPO_SCRIPT" in runner
    assert "tools/quality" in runner
    assert "repo-mutmut:retrying-failed-or-untested" in runner
    assert "mutmut-repo-retry.txt" in runner
    assert "survived|no tests" in runner
    assert 'sub(/:$/, "", name)' in runner


def test_repo_python_mutation_uses_all_changed_existing_files_not_first_path() -> None:
    runner = read("tools/quality/internal/run-python-repo-mutation.sh")

    assert "changed_paths_json" in runner
    assert "MUTMUT_CHANGED_JSON" in runner
    assert "head -n 1" not in runner
    assert "[[ -f \"$path\" ]]" in runner


def test_repo_python_mutation_parses_results_after_mutmut_nonzero() -> None:
    runner = read("tools/quality/internal/run-python-repo-mutation.sh")

    assert "set +e\nmutmut run --max-children" in runner
    assert "mutmut_status=$?" in runner
    assert "repo-mutmut:run-status=$mutmut_status" in runner
    assert 'grep -Eiq \':[[:space:]]+(survived|no tests)$\'' in runner


def test_repo_python_mutation_can_use_local_docker_inside_bazel_snapshot() -> None:
    runner = read("tools/quality/internal/run-python-repo-mutation.sh")

    assert 'mutation_context="${PYTHON_REPO_MUTATION_DOCKER_CONTEXT' in runner
    assert 'if [[ "$mutation_context" != "__local__" && "$mutation_context" != "local" ]]' in runner
    assert 'docker_context_args=(--context "$mutation_context")' in runner


def test_repo_python_mutation_copies_routing_config_for_script_tests() -> None:
    runner = read("tools/quality/internal/run-python-repo-mutation.sh")

    assert "config/mutation-routing.json" in runner
    assert '"config/"' in runner
    assert 'cp -R config "$tmp_dir/config"' in runner


def test_repo_python_mutation_copies_bazelrc_for_bazel_default_tests() -> None:
    runner = read("tools/quality/internal/run-python-repo-mutation.sh")

    assert ".bazelrc" in runner
    assert '".bazelrc"' in runner
    assert 'cp .bazelrc "$tmp_dir/.bazelrc"' in runner


def test_backend_python_mutation_uses_remote_docker_helper_not_raw_ssh() -> None:
    runner = read("tools/quality/internal/run-python-mutation.sh")

    assert "xf_remote_context_reachable \"$PYTHON_MUTATION_DOCKER_CONTEXT\"" in runner
    assert "ssh \"$PYTHON_MUTATION_DOCKER_CONTEXT\" docker info" not in runner
    assert "XF_BAZEL_PRIVATE_MUTATION" in runner
    assert "Bazel is the required quality path" in runner


def test_public_prepush_wires_bazel_mutation() -> None:
    ps1 = read("scripts/prepush-docker.sh")

    assert "scripts/bazel_default.py run //tools/quality:mutation" in ps1
    assert "run-python-repo-mutation.sh" not in ps1


def test_bazel_mutation_wrapper_calls_private_runner_bodies() -> None:
    wrapper = read("tools/quality/mutation.sh")
    repo_runner = read("tools/quality/internal/run-python-repo-mutation.sh")
    rust_runner = read("tools/quality/internal/run-rust-mutation.sh")
    angular_runner = read("tools/quality/internal/run-angular-mutation.sh")

    assert "export XF_BAZEL_INTERNAL=1" not in wrapper
    assert "XF_BAZEL_PRIVATE_MUTATION=1" in wrapper
    for text in (repo_runner, rust_runner, angular_runner):
        assert "XF_BAZEL_PRIVATE_MUTATION" in text
        assert "Bazel is the required quality path" in text
    assert "-e XF_BAZEL_INTERNAL=1" not in rust_runner
