"""Tests for scripts/quality-evidence-lib.sh."""
from __future__ import annotations

from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "quality-evidence-lib.sh"
READINESS_SCRIPT = Path(__file__).resolve().parent / "run-tool-readiness.sh"


def _readiness_text_or_skip() -> str:
    text = READINESS_SCRIPT.read_text()
    if not text:
        pytest.skip("run-tool-readiness.sh is empty in this worktree")
    return text


def test_turbo_no_build_reaches_evidence_helpers():
    text = SCRIPT.read_text()

    assert "quality_docker_run_opts" in text
    assert 'XF_QUALITY_NO_BUILD:-0' in text
    assert 'printf "%s\\n" "--pull" "never"' in text
    assert "quality_python_cmd()" in text
    assert '"$(quality_python_cmd)" scripts/write_quality_evidence.py "$@"' in text
    assert "command -v python3" in text


def test_evidence_import_uses_shared_lock_before_backend_lookup():
    text = SCRIPT.read_text()

    assert "quality_evidence_acquire_import_lock" in text
    assert "quality-evidence-import.lock" in text
    assert text.index("quality_evidence_acquire_import_lock") < text.index("quality_backend_pod")


def test_evidence_import_can_be_skipped_for_remote_compute_shards():
    text = SCRIPT.read_text()

    assert "QUALITY_EVIDENCE_SKIP_IMPORT" in text
    assert "Quality evidence import skipped" in text


def test_evidence_file_is_removed_after_successful_import():
    text = SCRIPT.read_text()

    assert 'rm -f "$host_path"' in text
    assert text.index('rm -f "$host_path"') > text.index('quality_evidence_import "$container_path"')


def test_tool_readiness_backend_quality_respects_no_build_option():
    text = _readiness_text_or_skip()

    assert '"${PYTHON:-python3}" scripts/smart_build.py --target "$service"' in text
    assert 'XF_QUALITY_NO_BUILD:-0' in text
    assert "Docker image is missing and no-build mode is enabled." in text
    assert "ensure_image backend-quality xf-linker-backend-quality:latest" in text
    assert "backend_quality_run_opts" in text
    assert "quality_docker_run_opts" in text
    assert '"${backend_quality_run_opts[@]}" backend-quality' in text


def test_tool_readiness_skips_frontend_mutation_when_no_frontend_files_changed():
    text = _readiness_text_or_skip()

    assert "changed_frontend_paths()" in text
    assert "frontend_changed_paths=\"$(changed_frontend_paths)\"" in text
    assert "No changed frontend files; frontend mutation readiness skipped." in text
    assert text.count("docker --context dell inspect xf_linker_frontend_mutation_tools") >= 2
    assert text.index("docker --context dell inspect xf_linker_frontend_mutation_tools") > text.index(
        'if [[ -n "$frontend_changed_paths" ]]'
    )
