"""TDD guard for scripts/run-mint-quality-shard.sh."""
from __future__ import annotations

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SCRIPT = SCRIPTS / "run-mint-quality-shard.sh"


def _text() -> str:
    return SCRIPT.read_text()


def test_mint_runner_file_exists():
    assert SCRIPT.exists(), "scripts/run-mint-quality-shard.sh must be created"


def test_runs_all_mint_language_quality_scripts():
    t = _text()
    for s in (
        "run-cpp-quality.sh",
        "run-go-quality.sh",
        "run-haskell-quality.sh",
        "run-rust-quality.sh",
    ):
        assert s in t, f"Mint runner must call {s}"


def test_runs_megalinter_via_docker():
    assert "oxsecurity/megalinter" in _text()


def test_megalinter_writes_reports_outside_read_only_repo_mount():
    t = _text()
    assert "REPORT_OUTPUT_FOLDER=/tmp/megalinter-reports" in t
    assert "-v \"$repo_root:/tmp/lint:ro\"" in t


def test_uses_filter_regex_include_for_scope():
    assert "FILTER_REGEX_INCLUDE" in _text()


def test_mint_runner_provides_python_alias_when_only_python3_exists():
    t = _text()
    assert "xf-mint-python-bin" in t
    assert "python3" in t


def test_mint_runner_sets_compose_password_for_quality_only_services():
    assert "mint-quality-not-used" in _text()


def test_mint_runner_sets_quality_only_django_secret_key():
    t = _text()
    assert "DJANGO_SECRET_KEY" in t
    assert "mint-quality-dummy-secret-key" in t


def test_mint_runner_skips_database_evidence_import():
    t = _text()
    assert "QUALITY_EVIDENCE_SKIP_IMPORT" in t


def test_mint_runner_runs_rust_and_haskell_inside_compiled_tools():
    t = _text()
    assert "xf_linker_compiled_tools" in t
    assert "run-rust-quality.sh" in t
    assert "run-haskell-quality.sh" in t


def test_mint_runner_exports_manifest_scope_to_language_wrappers():
    t = _text()
    assert "changed_files" in t
    assert "QUALITY_CPP_CHANGED_FILES" in t
    assert "QUALITY_GO_PATHS" in t


def test_mint_runner_propagates_background_failures():
    t = _text()
    assert "pids+=" in t
    assert 'exit "$status"' in t


def test_all_jobs_backgrounded():
    """Every language script must run in parallel (&) not sequentially."""
    t = _text()
    for s in (
        "run-cpp-quality.sh",
        "run-go-quality.sh",
        "run-haskell-quality.sh",
        "run-rust-quality.sh",
    ):
        idx = t.index(s)
        # The & must appear within 80 chars of the script reference (same line)
        surrounding = t[idx : idx + 80]
        assert "&" in surrounding, f"{s} must be backgrounded with &"


def test_waits_for_all_background_jobs():
    t = _text()
    assert 'for pid in "${pids[@]}"' in t
    assert 'wait "$pid"' in t
