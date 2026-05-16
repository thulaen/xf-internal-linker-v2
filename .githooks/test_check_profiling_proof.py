#!/usr/bin/env python3
"""Tests for the profiling proof hard check."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock


VALID_PROOF = (
    "[PROFILING PROOF: service=backend scope=backend/apps/core "
    "source=pyroscope+otel_profiles hotspots=0 "
    "baseline=\"docker compose exec -T backend python manage.py inspect_profiles\" "
    "decision=not-relevant]"
)
VALID_HOTSPOT = (
    "[HOTSPOT OPTIMIZATION: name=scheduler before=100ms after=4ms "
    "improvement=25.00x workload=pytest regression_test=test_scheduler]"
)
VALID_GAP = (
    "[PROFILING PIPELINE GAP: autoissues=#1,#2,#3,#4,#5,#6,#7,#8 "
    "categories=collector,backend,versions,permissions,sampling,retention,"
    "dashboards,trace-profile-correlation]"
)
VALID_SPEC = (
    "[PERFORMANCE SPEC: sources=otel-profiles-spec,pyroscope-otel-docs,gwp-paper "
    "source_types=technical_doc,academic_paper tdd=yes tests=profiling-tests]"
)
VALID_REWRITE = (
    "[NATIVE REWRITE REVIEW: hotspot=scheduler before=100ms after=80ms "
    "current_ceiling=80ms reason=interpreter_overhead expected_speedup=5-20x "
    "target_language=Go cost=medium integration=rpc tests=parity_tests "
    "reuse_check=shared_boundary_checked canonical=go_scheduler "
    "default_path=native_when_faster python_fallback=optimized "
    "risks=maintenance rollback=python_fallback autoissue=#42 "
    "label=performance-native-rewrite]"
)


def _load_hook():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "check_profiling_proof", here / "check-profiling-proof.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProfilingProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def _run(self, files: list[str], handoff: str) -> tuple[int, str]:
        with mock.patch.object(self.hook, "_staged_source_files", return_value=files), \
             mock.patch.object(self.hook, "_staged_handoff_diff", return_value=handoff), \
             mock.patch.object(sys, "stderr", StringIO()) as err:
            return self.hook.main(), err.getvalue()

    def test_no_source_files_passes(self):
        code, _ = self._run([], "")
        self.assertEqual(code, 0)

    def test_source_without_handoff_fails(self):
        code, err = self._run(["backend/apps/core/example.py"], "")
        self.assertEqual(code, 2)
        self.assertIn("FAIL", err)
        self.assertIn("WHY", err)
        self.assertIn("UNBLOCK", err)

    def test_handoff_without_marker_fails(self):
        code, err = self._run(["backend/apps/core/example.py"], "plain text")
        self.assertEqual(code, 2)
        self.assertIn("PROFILING PROOF", err)

    def test_marker_missing_required_field_fails(self):
        marker = VALID_PROOF.replace("service=backend ", "")
        code, err = self._run(["backend/apps/core/example.py"], marker)
        self.assertEqual(code, 2)
        self.assertIn("service", err)

    def test_marker_requires_pyroscope_and_otel_profiles(self):
        marker = VALID_PROOF.replace(
            "source=pyroscope+otel_profiles", "source=pyroscope"
        )
        code, err = self._run(["backend/apps/core/example.py"], marker)
        self.assertEqual(code, 2)
        self.assertIn("pyroscope+otel_profiles", err)

    def test_marker_rejects_more_than_five_hotspots(self):
        marker = VALID_PROOF.replace("hotspots=0", "hotspots=6")
        code, err = self._run(["backend/apps/core/example.py"], marker)
        self.assertEqual(code, 2)
        self.assertIn("0 to 5", err)

    def test_marker_rejects_unknown_decision(self):
        marker = VALID_PROOF.replace("decision=not-relevant", "decision=skip")
        code, err = self._run(["backend/apps/core/example.py"], marker)
        self.assertEqual(code, 2)
        self.assertIn("decision", err)

    def test_valid_not_relevant_marker_passes(self):
        code, _ = self._run(["backend/apps/core/example.py"], VALID_PROOF)
        self.assertEqual(code, 0)

    def test_optimized_hotspot_requires_optimization_marker(self):
        marker = VALID_PROOF.replace("hotspots=0", "hotspots=1").replace(
            "decision=not-relevant", "decision=optimized"
        )
        code, err = self._run(["backend/apps/core/example.py"], marker + "\n" + VALID_SPEC)
        self.assertEqual(code, 2)
        self.assertIn("HOTSPOT OPTIMIZATION", err)

    def test_valid_hotspot_optimization_passes(self):
        marker = VALID_PROOF.replace("hotspots=0", "hotspots=1").replace(
            "decision=not-relevant", "decision=optimized"
        )
        code, _ = self._run(
            ["backend/apps/core/example.py"],
            marker + "\n" + VALID_SPEC + "\n" + VALID_HOTSPOT,
        )
        self.assertEqual(code, 0)

    def test_hotspot_optimization_missing_metric_fails(self):
        marker = VALID_PROOF.replace("hotspots=0", "hotspots=1").replace(
            "decision=not-relevant", "decision=optimized"
        )
        bad_hotspot = VALID_HOTSPOT.replace("after=4ms ", "")
        code, err = self._run(
            ["backend/apps/core/example.py"],
            marker + "\n" + VALID_SPEC + "\n" + bad_hotspot,
        )
        self.assertEqual(code, 2)
        self.assertIn("after", err)

    def test_pipeline_gap_missing_category_fails(self):
        bad_gap = VALID_GAP.replace(",dashboards", "")
        code, err = self._run([".githooks/check-profiling-proof.py"], VALID_SPEC + "\n" + bad_gap)
        self.assertEqual(code, 2)
        self.assertIn("dashboards", err)

    def test_pipeline_gap_does_not_unblock_unrelated_source(self):
        code, err = self._run(["backend/apps/core/example.py"], VALID_SPEC + "\n" + VALID_GAP)
        self.assertEqual(code, 2)
        self.assertIn("does not clear unrelated source changes", err)

    def test_pipeline_gap_passes_for_profiling_repair_files(self):
        code, _ = self._run([".githooks/check-profiling-proof.py"], VALID_SPEC + "\n" + VALID_GAP)
        self.assertEqual(code, 0)

    def test_not_achievable_hotspot_requires_native_rewrite_review(self):
        marker = VALID_PROOF.replace("hotspots=0", "hotspots=1").replace(
            "decision=not-relevant", "decision=not-achievable"
        )
        code, err = self._run(["backend/apps/core/example.py"], marker + "\n" + VALID_SPEC)
        self.assertEqual(code, 2)
        self.assertIn("NATIVE REWRITE REVIEW", err)

    def test_native_rewrite_review_missing_evidence_fails(self):
        marker = VALID_PROOF.replace("hotspots=0", "hotspots=1").replace(
            "decision=not-relevant", "decision=not-achievable"
        )
        bad_rewrite = VALID_REWRITE.replace("rollback=python_fallback ", "")
        code, err = self._run(
            ["backend/apps/core/example.py"],
            marker + "\n" + VALID_SPEC + "\n" + bad_rewrite,
        )
        self.assertEqual(code, 2)
        self.assertIn("rollback", err)

    def test_native_rewrite_review_requires_reuse_check(self):
        marker = VALID_PROOF.replace("hotspots=0", "hotspots=1").replace(
            "decision=not-relevant", "decision=not-achievable"
        )
        bad_rewrite = VALID_REWRITE.replace("reuse_check=shared_boundary_checked ", "")
        code, err = self._run(
            ["backend/apps/core/example.py"],
            marker + "\n" + VALID_SPEC + "\n" + bad_rewrite,
        )
        self.assertEqual(code, 2)
        self.assertIn("reuse_check", err)

    def test_native_rewrite_review_passes_with_required_evidence(self):
        marker = VALID_PROOF.replace("hotspots=0", "hotspots=1").replace(
            "decision=not-relevant", "decision=not-achievable"
        )
        code, _ = self._run(
            ["backend/apps/core/example.py"],
            marker + "\n" + VALID_SPEC + "\n" + VALID_REWRITE,
        )
        self.assertEqual(code, 0)

    def test_profiling_repair_requires_source_backed_spec(self):
        code, err = self._run([".githooks/check-profiling-proof.py"], VALID_GAP)
        self.assertEqual(code, 2)
        self.assertIn("PERFORMANCE SPEC", err)

    def test_performance_spec_requires_tdd_yes(self):
        bad_spec = VALID_SPEC.replace("tdd=yes", "tdd=no")
        code, err = self._run([".githooks/check-profiling-proof.py"], bad_spec + "\n" + VALID_GAP)
        self.assertEqual(code, 2)
        self.assertIn("tdd=yes", err)

    def test_observability_config_changes_require_source_backed_spec(self):
        code, err = self._run(["otelcol-config.yaml"], VALID_PROOF)
        self.assertEqual(code, 2)
        self.assertIn("PERFORMANCE SPEC", err)

    def test_observability_config_passes_with_profile_proof_and_spec(self):
        code, _ = self._run(["docker-compose.yml"], VALID_SPEC + "\n" + VALID_PROOF)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
