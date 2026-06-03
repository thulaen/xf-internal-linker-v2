"""Tests for scripts/quality-evidence-lib.sh."""
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "quality-evidence-lib.sh"


def test_turbo_no_build_reaches_evidence_docker_runs():
    text = SCRIPT.read_text()

    assert "quality_docker_run_opts" in text
    assert 'XF_QUALITY_NO_BUILD:-0' in text
    assert 'printf "%s\\n" "--pull" "never"' in text
    assert "docker compose run" in text
    assert '"${docker_run_opts[@]}"' in text


def test_evidence_import_uses_shared_lock_before_docker_compose():
    text = SCRIPT.read_text()

    assert "quality_evidence_acquire_import_lock" in text
    assert "quality-evidence-import.lock" in text
    assert text.index("quality_evidence_acquire_import_lock") < text.index("docker compose run")


def test_evidence_import_can_be_skipped_for_remote_compute_shards():
    text = SCRIPT.read_text()

    assert "QUALITY_EVIDENCE_SKIP_IMPORT" in text
    assert "Quality evidence import skipped" in text


def test_evidence_file_is_removed_after_successful_import():
    text = SCRIPT.read_text()

    assert 'rm -f "$host_path"' in text
    assert text.index('rm -f "$host_path"') > text.index('quality_evidence_import "$container_path"')
