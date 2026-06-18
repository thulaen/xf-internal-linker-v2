"""Tests for the normal commit hook wrapper."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_script(path: str) -> str:
    # Resolve from the repo root so the tests pass from any working
    # directory — including the Dell test container, whose cwd is
    # /repo/backend rather than the repo root.
    return (ROOT / path).read_text(encoding="utf-8")


def test_hard_gates_run_before_language_quality() -> None:
    text = _read_script("scripts/precommit-docker.sh")

    first_quality = min(
        text.index(
            "run_soft_gate bazel-frontend-quality "
            "python scripts/bazel_default.py run //tools/quality:frontend"
        ),
        text.index(
            "run_hard_gate bazel-python-quality "
            "python scripts/bazel_default.py run //tools/quality:python"
        ),
    )
    hard_gates = (
        "run_hard_gate check-observability-stack python .githooks/check-observability-stack.py",
        "run_hard_gate check-msi-docker-free python .githooks/check-msi-docker-free.py",
        "run_hard_gate check-no-destructive-docker-commands python .githooks/check-no-destructive-docker-commands.py",
        "run_hard_gate check-rust-mandate python .githooks/check-rust-mandate.py",
        "run_hard_gate check-debug-code python .githooks/check-debug-code.py",
        "run_hard_gate check-junk-files python .githooks/check-junk-files.py",
        "run_hard_gate check-no-cross-language-import python .githooks/check-no-cross-language-import.py",
        "run_hard_gate check-language-ownership python .githooks/check-language-ownership.py",
    )
    for gate in hard_gates:
        assert gate in text
        assert text.index(gate) < first_quality


def test_hard_gates_collect_failures_before_exiting() -> None:
    text = _read_script("scripts/precommit-docker.sh")

    assert "hard_block_failures=0" in text
    assert "run_hard_gate()" in text
    assert 'hard_block_failures=$((hard_block_failures + 1))' in text
    assert '_finish_precommit "$code"' in text


def test_tool_readiness_runs_before_staged_file_selection() -> None:
    text = _read_script("scripts/precommit-docker.sh")

    assert text.index("bash scripts/run-tool-readiness.sh") < text.index("staged=")


def test_precommit_resolves_python_before_hooks() -> None:
    text = _read_script("scripts/precommit-docker.sh")

    assert "_resolve_python_bin()" in text
    assert 'PYTHON_BIN="${PYTHON_BIN:-$(_resolve_python_bin)}"' in text
    assert text.index('PYTHON_BIN="${PYTHON_BIN:-$(_resolve_python_bin)}"') < text.index(
        "run_hard_gate tool-readiness"
    )


def test_python_local_tests_have_five_minute_caps() -> None:
    python_text = _read_script("tools/quality/internal/run-python-quality.sh")

    assert 'timeout --signal=TERM --kill-after=30 300 "$@"' in python_text
    assert "in_cap python /repo/scripts/run_quality_step.py" in python_text


def test_precommit_runs_deep_link_check_without_local_docker() -> None:
    text = _read_script("scripts/precommit-docker.sh")

    assert ". scripts/_quality_concurrency.sh" in text
    assert "quality_install_cleanup_trap" in text
    assert "COMMIT_SCOPE_PATHS=\"$staged\" python scripts/verify_deep_links.py" in text
    assert "quality_docker_compose_run precommit-deep-links backend" not in text
    assert "docker compose run --rm -T --no-deps \\\n  -e COMMIT_SCOPE_PATHS" not in text


def test_repo_pins_shell_scripts_to_lf_line_endings() -> None:
    attrs = _read_script(".gitattributes")

    assert "* text=auto eol=lf" in attrs
    assert "*.ps1 text eol=crlf" in attrs


def test_quality_concurrency_helper_does_not_spawn_background_jobs() -> None:
    text = _read_script("scripts/_quality_concurrency.sh")

    assert '"$@" &' not in text
    assert "wait \"$pid\"" not in text
    assert "GNU coreutils timeout is required" in text


def test_local_quality_checks_default_to_serial_workers() -> None:
    helper = _read_script("scripts/_quality_concurrency.sh")

    assert 'local requested="${XF_QUALITY_CORES:-1}"' in helper
    assert "local max_plugged=1" in helper
    assert "local max_battery=1" in helper


def test_standalone_quality_scripts_acquire_meta_lock_before_tool_lock() -> None:
    scripts = (
        ("tools/quality/internal/run-python-quality.sh", "quality_acquire_tool_lock python-quality"),
    )

    for path, tool_lock in scripts:
        text = _read_script(path)
        assert "quality_acquire_meta_lock" in text
        assert text.index("quality_acquire_meta_lock") < text.index(tool_lock)


def test_python_quality_coverage_targets_changed_sources_only() -> None:
    text = _read_script("tools/quality/internal/run-python-quality.sh")

    assert "QUALITY_PYTHON_COVERAGE_TARGETS" in text
    assert "coverage_args" in text
    assert "--cov=apps --cov=config" not in text
    assert 'XF_TURBO_TESTS:-0' in text
    assert "[TURBO TESTS: distributing pytest shards via turbo_tests.py]" in text
    assert '--tool-name pip-audit --command "pip-audit"' in text
    assert "Safety dependency check passed." in text


def test_python_quality_excludes_generated_sidecar_protobuf_stubs() -> None:
    text = _read_script("tools/quality/internal/run-python-quality.sh")

    assert "_sidecars_pb/.+_pb2(_grpc)?\\.py" in text
    assert "generated sidecar protobuf stubs are covered by the shared contract test" in text


def test_pytest_default_does_not_measure_unrelated_backend_modules() -> None:
    pytest_ini = _read_script("backend/pytest.ini")

    assert "--cov=apps" not in pytest_ini
    assert "--cov=config" not in pytest_ini
    assert "Coverage is added by scoped quality wrappers" in pytest_ini
