"""TDD guard for scripts/run-go-quality.sh."""
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "run-go-quality.sh"


def test_go_quality_honors_prefilled_manifest_scope():
    text = SCRIPT.read_text()

    assert 'if [[ "${QUALITY_SCOPE_FROM_MANIFEST:-0}" == "1" ]]' in text
    assert 'go_paths="$QUALITY_GO_PATHS"' in text


def test_go_quality_disables_vcs_stamping_for_helper_checkouts():
    text = SCRIPT.read_text()

    assert "GOFLAGS" in text
    assert "-buildvcs=false" in text
    assert "-e GOFLAGS" in text


def test_go_quality_skips_survivor_filing_on_remote_compute_shard():
    text = SCRIPT.read_text()

    assert "QUALITY_EVIDENCE_SKIP_IMPORT" in text
    assert "Skipping go-mutesting survivor filing" in text
