"""TDD guard for scripts/run-cpp-quality.sh.

Full icecc distribution tests live in scripts/tests/test_icecc_cpp_distribution.py.
"""
from pathlib import Path

from scripts.tests.test_icecc_cpp_distribution import (  # noqa: F401
    test_cpp_quality_passes_icecc_scheduler,
)

SCRIPT = Path(__file__).resolve().parent / "run-cpp-quality.sh"


def test_cpp_quality_honors_prefilled_manifest_scope():
    text = SCRIPT.read_text()

    assert 'if [[ "${QUALITY_SCOPE_FROM_MANIFEST:-0}" == "1" ]]' in text
    assert 'cpp_files="$QUALITY_CPP_CHANGED_FILES"' in text


def test_cpp_quality_skips_infer_for_helper_fuzz_and_stub_scope():
    text = SCRIPT.read_text()

    assert "cpp_infer_scope_files" in text
    assert "C++ Infer skipped" in text


def test_cpp_quality_skips_survivor_filing_on_remote_compute_shard():
    text = SCRIPT.read_text()

    assert "QUALITY_EVIDENCE_SKIP_IMPORT" in text
    assert "Skipping Mull survivor filing" in text
