"""Tests for the normal commit hook wrapper."""

from __future__ import annotations

from pathlib import Path


def _read_script(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_hard_gates_run_before_language_quality() -> None:
    text = _read_script("scripts/precommit-docker.sh")

    first_quality = min(
        text.index("  bash scripts/run-angular-quality.sh"),
        text.index("  bash scripts/run-python-quality.sh"),
        text.index("  bash scripts/run-cpp-quality.sh"),
        text.index("  bash scripts/run-go-quality.sh"),
    )
    hard_gates = (
        "run_hard_gate python .githooks/check-code-review-lessons.py",
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
    text = _read_script("scripts/precommit-docker.sh")

    assert "hard_gate_status=0" in text
    assert "run_hard_gate()" in text
    assert 'if [[ "$hard_gate_status" -ne 0 ]]; then' in text


def test_tool_readiness_runs_before_staged_file_selection() -> None:
    text = _read_script("scripts/precommit-docker.sh")

    assert text.index("bash scripts/run-tool-readiness.sh") < text.index("staged=")


def test_python_and_frontend_local_tests_have_five_minute_caps() -> None:
    python_text = _read_script("scripts/run-python-quality.sh")
    frontend_text = _read_script("scripts/run-angular-quality.sh")

    for text in (python_text, frontend_text):
        assert 'timeout --signal=TERM --kill-after=30 300 "$@"' in text
    assert "in_cap python /repo/scripts/run_quality_step.py" in python_text
    assert "in_cap mutmut run" in python_text
    assert "in_cap npm run test:ci" in frontend_text
    assert "in_cap npx stryker run" in frontend_text


def test_precommit_uses_named_docker_helper_for_deep_link_check() -> None:
    text = _read_script("scripts/precommit-docker.sh")

    assert ". scripts/_quality_concurrency.sh" in text
    assert "quality_install_cleanup_trap" in text
    assert "quality_docker_compose_run precommit-deep-links backend" in text
    assert "docker compose run --rm -T --no-deps \\\n  -e COMMIT_SCOPE_PATHS" not in text


def test_repo_pins_shell_scripts_to_lf_line_endings() -> None:
    attrs = _read_script(".gitattributes")

    assert ".gitattributes text eol=lf" in attrs
    assert "*.sh text eol=lf" in attrs
    assert ".githooks/* text eol=lf" in attrs
    assert "*.jsonl text eol=lf" in attrs
    assert "scripts/*.ps1 text eol=crlf" in attrs


def test_quality_concurrency_helper_does_not_spawn_background_jobs() -> None:
    text = _read_script("scripts/_quality_concurrency.sh")

    assert '"$@" &' not in text
    assert "wait \"$pid\"" not in text
    assert "GNU coreutils timeout is required" in text


def test_local_quality_checks_default_to_serial_workers() -> None:
    helper = _read_script("scripts/_quality_concurrency.sh")
    cpp_mutation = _read_script("scripts/run-cpp-mutation.sh")

    assert 'local requested="${XF_QUALITY_CORES:-1}"' in helper
    assert "local max_plugged=1" in helper
    assert "local max_battery=1" in helper
    assert "--parallel" not in cpp_mutation


def test_standalone_quality_scripts_acquire_meta_lock_before_tool_lock() -> None:
    scripts = (
        ("scripts/run-angular-quality.sh", "quality_acquire_tool_lock stryker"),
        ("scripts/run-python-quality.sh", "quality_acquire_tool_lock python-quality"),
        ("scripts/run-cpp-quality.sh", "quality_acquire_tool_lock cpp-quality"),
        ("scripts/run-go-quality.sh", "quality_acquire_tool_lock go-quality"),
    )

    for path, tool_lock in scripts:
        text = _read_script(path)
        assert "quality_acquire_meta_lock" in text
        assert text.index("quality_acquire_meta_lock") < text.index(tool_lock)


def test_cpp_and_go_local_quality_steps_have_five_minute_caps() -> None:
    cpp_text = _read_script("scripts/run-cpp-quality.sh")
    go_text = _read_script("scripts/run-go-quality.sh")

    for text in (cpp_text, go_text):
        assert "quality_timeout 300 bash -c" in text
    for step in ("cpp-tests", "cpp-coverage", "cpp-fuzz", "cpp-sanitizers", "mull"):
        assert step in cpp_text
    for step in ("go-tests", "go-mutesting", "go-bench"):
        assert step in go_text


def test_frontend_quality_uses_changed_test_includes() -> None:
    frontend_text = _read_script("scripts/run-angular-quality.sh")

    assert "QUALITY_FRONTEND_TEST_INCLUDES" in frontend_text
    assert "--include $QUALITY_FRONTEND_TEST_INCLUDES" in frontend_text
    assert "in_cap npm run test:ci -- --code-coverage=true\n" not in frontend_text
    assert "No changed frontend file needed scoped Angular lint, tests, or mutation." in frontend_text


def test_quality_debt_changed_mode_does_not_run_frontend_suite() -> None:
    quality_debt_text = _read_script("scripts/run-quality-debt-report.sh")

    changed_block = quality_debt_text.split('if [[ "${1:-}" == "--changed" ]]', 1)[1]
    changed_block = changed_block.split("fi", 1)[0]
    assert "npm run test:ci" not in changed_block
    assert "npx stryker run" not in changed_block


def test_cpp_test_wrappers_use_changed_binary_targets() -> None:
    for path in (
        "scripts/run-cpp-tests.sh",
        "scripts/run-cpp-coverage.sh",
        "scripts/run-cpp-sanitizers.sh",
    ):
        text = _read_script(path)
        assert "cpp_mutation_targets.py" in text
        assert "--target \"${targets[@]}\"" in text
        assert "ctest --output-on-failure --schedule-random -j 2" not in text


def test_cpp_mutation_does_not_fallback_to_every_binary() -> None:
    text = _read_script("scripts/run-cpp-mutation.sh")

    assert 'targets=("${all_targets[@]}")' not in text
    assert "No changed C++ mutation target" in text


def test_go_module_selector_requires_explicit_all_modules_mode() -> None:
    text = _read_script("scripts/go_modules.py")

    assert '"--all"' in text
    assert "modules = _all_modules()" not in text.split("if args.all:", 1)[0]
    assert 'os.environ.get("REPO_ROOT", "/repo")' not in text


def test_compiled_tools_image_installs_llvm_coverage_tools() -> None:
    dockerfile = _read_script("tools/mutation/Dockerfile")
    readiness = _read_script("scripts/run-tool-readiness.sh")

    assert "llvm-19" in dockerfile
    assert "llvm-cov-19 --version" in readiness
    assert "llvm-profdata-19 --version" in readiness


def test_python_quality_coverage_targets_changed_sources_only() -> None:
    text = _read_script("scripts/run-python-quality.sh")

    assert "QUALITY_PYTHON_COVERAGE_TARGETS" in text
    assert "coverage_args" in text
    assert "--cov=apps --cov=config" not in text
    assert 'XF_TURBO_TESTS:-0' in text
    assert "FULL TURBO TESTS" in text
    assert "pip-audit scoped to dependency-file changes" in text
    assert "Safety dependency check skipped because no dependency file changed." in text


def test_python_quality_excludes_generated_sidecar_protobuf_stubs() -> None:
    text = _read_script("scripts/run-python-quality.sh")

    assert "_sidecars_pb/.+_pb2(_grpc)?\\.py" in text
    assert "generated sidecar protobuf stubs are covered by the shared contract test" in text


def test_pytest_default_does_not_measure_unrelated_backend_modules() -> None:
    pytest_ini = _read_script("backend/pytest.ini")

    assert "--cov=apps" not in pytest_ini
    assert "--cov=config" not in pytest_ini
    assert "Coverage is added by scoped quality wrappers" in pytest_ini
