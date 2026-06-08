"""TDD guard for scripts/run-go-quality.sh."""
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "run-go-quality.sh"
MUTATION_SCRIPT = Path(__file__).resolve().parent / "run-go-mutation.sh"


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


def test_go_quality_skips_survivor_filing_when_turbo_mutation_is_enabled():
    text = SCRIPT.read_text()

    assert "XF_TURBO_MUTATION" in text
    assert "mutation is delegated to turbo coordinator" in text


def test_go_mutation_skips_generated_sources():
    text = MUTATION_SCRIPT.read_text()

    assert "mutation_targets_for_module" in text
    assert "api/gen/*" in text
    assert "*_test.go" in text
    assert "No non-generated Go source files needed go-mutesting" in text
