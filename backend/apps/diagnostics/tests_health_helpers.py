"""Tests for the pure-function helpers extracted from ``apps.diagnostics.health``.

Covers helpers introduced when shrinking 4 oversized functions
(``_benchmark_native_modules``, ``check_native_scoring``, ``detect_conflicts``,
``_native_module_runtime_status``).

All tests run in ``SimpleTestCase`` (no DB, no Docker) via mocks.  ORM-touching
helpers (the conflict detectors and ``_persist_conflicts``) get integration
coverage from existing diagnostics tests and are exercised here only via mocks.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.diagnostics.health import (
    _aggregate_benchmark_results,
    _benchmark_error_result,
    _benchmark_feedrerank,
    _benchmark_pagerank,
    _benchmark_result,
    _benchmark_scoring,
    _benchmark_simsearch,
    _benchmark_texttok,
    _classify_module_state,
    _classify_native_modules,
    _conflict_analytics_missing,
    _conflict_dev_runtime,
    _conflict_native_unhealthy,
    _conflict_orphaned_suggestions,
    _conflict_planned_services,
    _merge_benchmark_into_statuses,
    _native_scoring_benchmark_result,
    _native_scoring_metadata,
    _native_scoring_module_failure_result,
    _native_scoring_result,
    _persist_conflicts,
)


# ---------------------------------------------------------------------------
# _classify_module_state
# ---------------------------------------------------------------------------


class ClassifyModuleStateTests(SimpleTestCase):
    """Verify the if/elif/else module-state classification table."""

    def test_healthy_when_importable_and_callable(self):
        state, runtime, fallback, reason = _classify_module_state(
            importable=True,
            callable_present=True,
            critical=True,
            error="",
            expected_attr="run",
        )
        self.assertEqual(state, "healthy")
        self.assertEqual(runtime, "cpp")
        self.assertFalse(fallback)
        self.assertEqual(reason, "")

    def test_failed_when_critical_and_missing_callable(self):
        state, runtime, fallback, reason = _classify_module_state(
            importable=True,
            callable_present=False,
            critical=True,
            error="",
            expected_attr="run",
        )
        self.assertEqual(state, "failed")
        self.assertEqual(runtime, "python")
        self.assertTrue(fallback)
        self.assertIn("run", reason)

    def test_degraded_when_noncritical_and_missing(self):
        state, runtime, fallback, reason = _classify_module_state(
            importable=False,
            callable_present=False,
            critical=False,
            error="ImportError: not built",
            expected_attr="run",
        )
        self.assertEqual(state, "degraded")
        self.assertEqual(runtime, "python")
        self.assertTrue(fallback)
        self.assertEqual(reason, "ImportError: not built")

    def test_uses_explicit_error_over_synthetic_fallback(self):
        _, _, _, reason = _classify_module_state(
            importable=False,
            callable_present=False,
            critical=True,
            error="boom",
            expected_attr="run",
        )
        self.assertEqual(reason, "boom")


# ---------------------------------------------------------------------------
# _merge_benchmark_into_statuses
# ---------------------------------------------------------------------------


class MergeBenchmarkIntoStatusesTests(SimpleTestCase):
    """The merge copies benchmark fields onto each status; missing benchmarks default."""

    def test_copies_benchmark_fields_when_present(self):
        statuses = [{"module": "scoring"}]
        benchmarks = {
            "scoring": {
                "benchmark_status": "benchmarked_faster",
                "python_ms": 1.2,
                "cpp_ms": 0.4,
                "speedup_vs_python": 3.0,
                "proof_available": True,
                "error": "",
            }
        }
        _merge_benchmark_into_statuses(statuses, benchmarks)
        self.assertEqual(statuses[0]["benchmark_status"], "benchmarked_faster")
        self.assertEqual(statuses[0]["speedup_vs_python"], 3.0)
        self.assertTrue(statuses[0]["proof_available"])

    def test_defaults_when_benchmark_missing(self):
        statuses = [{"module": "scoring"}]
        _merge_benchmark_into_statuses(statuses, {})
        self.assertEqual(statuses[0]["benchmark_status"], "not_benchmarked")
        self.assertIsNone(statuses[0]["python_ms"])
        self.assertFalse(statuses[0]["proof_available"])
        self.assertEqual(statuses[0]["benchmark_error"], "")


# ---------------------------------------------------------------------------
# _classify_native_modules
# ---------------------------------------------------------------------------


def _status(
    *,
    module: str = "scoring",
    state: str = "healthy",
    critical: bool = True,
    compiled: bool = True,
    importable: bool = True,
) -> dict[str, object]:
    return {
        "module": module,
        "state": state,
        "critical": critical,
        "compiled": compiled,
        "importable": importable,
    }


class ClassifyNativeModulesTests(SimpleTestCase):
    """Partition into critical_failures / degraded / healthy + count compiled/importable."""

    def test_all_healthy(self):
        statuses = [_status(module="a"), _status(module="b")]
        result = _classify_native_modules(statuses)
        self.assertEqual(result["critical_failures"], [])
        self.assertEqual(result["degraded_modules"], [])
        self.assertEqual(len(result["healthy_modules"]), 2)
        self.assertEqual(result["compiled_count"], 2)
        self.assertEqual(result["importable_count"], 2)
        self.assertFalse(result["fallback_active"])

    def test_one_critical_failure(self):
        statuses = [
            _status(module="a", state="failed", critical=True, importable=False),
            _status(module="b"),
        ]
        result = _classify_native_modules(statuses)
        self.assertEqual(len(result["critical_failures"]), 1)
        self.assertTrue(result["fallback_active"])

    def test_one_degraded(self):
        statuses = [
            _status(module="a"),
            _status(module="b", state="degraded", critical=False),
        ]
        result = _classify_native_modules(statuses)
        self.assertEqual(len(result["degraded_modules"]), 1)
        self.assertEqual(result["critical_failures"], [])
        self.assertTrue(result["fallback_active"])

    def test_mixed_states(self):
        statuses = [
            _status(module="a", state="failed", critical=True, compiled=False),
            _status(module="b", state="degraded", critical=False),
            _status(module="c"),
        ]
        result = _classify_native_modules(statuses)
        self.assertEqual(len(result["critical_failures"]), 1)
        self.assertEqual(len(result["degraded_modules"]), 1)
        self.assertEqual(len(result["healthy_modules"]), 1)
        self.assertEqual(result["compiled_count"], 2)


# ---------------------------------------------------------------------------
# _aggregate_benchmark_results
# ---------------------------------------------------------------------------


class AggregateBenchmarkResultsTests(SimpleTestCase):
    """Sum py/cpp ms across modules and derive overall benchmark_status."""

    def test_empty_results(self):
        result = _aggregate_benchmark_results({})
        self.assertEqual(result["benchmark_status"], "benchmark_failed")
        self.assertIsNone(result["overall_speedup"])

    def test_faster_speedup(self):
        benchmarks = {
            "a": {
                "benchmark_status": "benchmarked_faster",
                "python_ms": 10.0,
                "cpp_ms": 1.0,
                "proof_available": True,
            }
        }
        result = _aggregate_benchmark_results(benchmarks)
        self.assertEqual(result["benchmark_status"], "benchmarked_faster")
        self.assertEqual(result["overall_speedup"], 10.0)

    def test_no_material_speedup(self):
        benchmarks = {
            "a": {
                "benchmark_status": "no_material_speedup",
                "python_ms": 1.0,
                "cpp_ms": 1.0,
                "proof_available": True,
            }
        }
        result = _aggregate_benchmark_results(benchmarks)
        self.assertEqual(result["benchmark_status"], "no_material_speedup")

    def test_slower_than_python(self):
        benchmarks = {
            "a": {
                "benchmark_status": "slower_than_python",
                "python_ms": 1.0,
                "cpp_ms": 5.0,
                "proof_available": True,
            }
        }
        result = _aggregate_benchmark_results(benchmarks)
        self.assertEqual(result["benchmark_status"], "slower_than_python")
        self.assertEqual(result["overall_speedup"], 0.2)

    def test_mixed_with_failures(self):
        benchmarks = {
            "a": {
                "benchmark_status": "benchmarked_faster",
                "python_ms": 10.0,
                "cpp_ms": 2.0,
                "proof_available": True,
            },
            "b": {
                "benchmark_status": "benchmark_failed",
                "python_ms": None,
                "cpp_ms": None,
                "proof_available": False,
            },
        }
        result = _aggregate_benchmark_results(benchmarks)
        self.assertEqual(result["failures"], ["b"])
        self.assertEqual(len(result["proof_ready"]), 1)
        self.assertEqual(result["benchmark_status"], "benchmarked_faster")


# ---------------------------------------------------------------------------
# _native_scoring_metadata
# ---------------------------------------------------------------------------


class NativeScoringMetadataTests(SimpleTestCase):
    """The 18-key metadata payload returned by check_native_scoring."""

    def _classification(
        self, *, critical: int = 0, degraded: int = 0, healthy: int = 1
    ) -> dict:
        return {
            "critical_failures": [{"module": f"c{i}"} for i in range(critical)],
            "degraded_modules": [{"module": f"d{i}"} for i in range(degraded)],
            "healthy_modules": [{"module": f"h{i}"} for i in range(healthy)],
            "compiled_count": healthy + degraded + critical,
            "importable_count": healthy,
            "fallback_active": bool(critical or degraded),
        }

    def _aggregate(self, status: str = "benchmarked_faster") -> dict:
        return {
            "proof_ready": [{}],
            "failures": [],
            "overall_cpp_ms": 1.0,
            "overall_python_ms": 5.0,
            "overall_speedup": 5.0,
            "benchmark_status": status,
        }

    def test_all_healthy_runtime_path_is_cpp(self):
        statuses = [{"module": "a", "fallback_reason": ""}]
        meta = _native_scoring_metadata(
            statuses, self._classification(), self._aggregate(), {}
        )
        self.assertEqual(meta["runtime_path"], "cpp")
        self.assertTrue(meta["safe_to_use"])
        self.assertTrue(meta["native_scoring_active"])

    def test_runtime_path_is_python_when_no_healthy_modules(self):
        statuses = [{"module": "a", "fallback_reason": "down"}]
        meta = _native_scoring_metadata(
            statuses,
            self._classification(critical=1, healthy=0),
            self._aggregate(),
            {},
        )
        self.assertEqual(meta["runtime_path"], "python")
        self.assertFalse(meta["safe_to_use"])


# ---------------------------------------------------------------------------
# _native_scoring_module_failure_result + _native_scoring_benchmark_result
# ---------------------------------------------------------------------------


class NativeScoringResultTests(SimpleTestCase):
    """Five branches: failed / degraded-failures / degraded-bench-fail / degraded-no-speedup / healthy."""

    def _classification(self, *, critical: int = 0, degraded: int = 0) -> dict:
        return {
            "critical_failures": [{"module": f"c{i}"} for i in range(critical)],
            "degraded_modules": [{"module": f"d{i}"} for i in range(degraded)],
            "healthy_modules": [],
            "compiled_count": 0,
            "importable_count": 0,
            "fallback_active": bool(critical or degraded),
        }

    def test_critical_failure_returns_failed(self):
        meta: dict = {}
        result = _native_scoring_module_failure_result(
            self._classification(critical=1), meta
        )
        self.assertIsNotNone(result)
        state, _, _, m = result
        self.assertEqual(state, "failed")
        self.assertIn("Python fallback", m["fallback_reason"])

    def test_degraded_modules_returns_degraded(self):
        meta: dict = {}
        result = _native_scoring_module_failure_result(
            self._classification(degraded=2), meta
        )
        self.assertIsNotNone(result)
        state, _, _, m = result
        self.assertEqual(state, "degraded")
        self.assertIn("optional", m["fallback_reason"])

    def test_no_module_failures_returns_none(self):
        meta: dict = {}
        result = _native_scoring_module_failure_result(self._classification(), meta)
        self.assertIsNone(result)

    def test_benchmark_failed_returns_degraded(self):
        meta: dict = {}
        result = _native_scoring_benchmark_result("benchmark_failed", meta)
        self.assertIsNotNone(result)
        state, _, _, m = result
        self.assertEqual(state, "degraded")
        self.assertIn("Benchmarks", m["fallback_reason"])

    def test_no_material_speedup_returns_degraded(self):
        meta: dict = {}
        result = _native_scoring_benchmark_result("no_material_speedup", meta)
        self.assertIsNotNone(result)
        state, _, _, _ = result
        self.assertEqual(state, "degraded")

    def test_slower_than_python_returns_degraded(self):
        meta: dict = {}
        result = _native_scoring_benchmark_result("slower_than_python", meta)
        self.assertIsNotNone(result)
        state, _, _, _ = result
        self.assertEqual(state, "degraded")

    def test_benchmark_faster_returns_none(self):
        meta: dict = {}
        result = _native_scoring_benchmark_result("benchmarked_faster", meta)
        self.assertIsNone(result)

    def test_full_pipeline_healthy(self):
        meta: dict = {}
        aggregate = {
            "benchmark_status": "benchmarked_faster",
            "proof_ready": [{}],
            "failures": [],
            "overall_cpp_ms": 1.0,
            "overall_python_ms": 5.0,
            "overall_speedup": 5.0,
        }
        state, _, next_step, _ = _native_scoring_result(
            self._classification(), aggregate, meta
        )
        self.assertEqual(state, "healthy")
        self.assertEqual(next_step, "No action needed.")


# ---------------------------------------------------------------------------
# Per-module benchmark helpers (_benchmark_scoring, _benchmark_texttok, etc.)
# ---------------------------------------------------------------------------


class BenchmarkScoringTests(SimpleTestCase):
    """The scoring benchmark runs Python ranker vs scoring C++ extension; both errors fall through."""

    def test_returns_error_result_on_kernel_failure(self):
        with patch(
            "apps.pipeline.services.ranker._calculate_composite_scores_full_batch_py",
            side_effect=RuntimeError("simulated"),
        ):
            result = _benchmark_scoring()
        self.assertEqual(result["benchmark_status"], "benchmark_failed")
        self.assertFalse(result["proof_available"])

    def test_returns_result_dict_shape(self):
        result = _benchmark_scoring()
        for key in ("benchmark_status", "python_ms", "cpp_ms", "proof_available"):
            self.assertIn(key, result)


class BenchmarkTexttokTests(SimpleTestCase):
    """The texttok benchmark runs Python tokenizer vs texttok C++ extension."""

    def test_returns_error_result_on_kernel_failure(self):
        # Force the C++ kernel call to raise so we exercise the helper's except branch
        # (sys.modules patching is unreliable here because `extensions.texttok` is also
        # exposed as an attribute on the extensions package).
        with patch(
            "extensions.texttok.tokenize_text_batch",
            side_effect=RuntimeError("simulated"),
        ):
            result = _benchmark_texttok()
        self.assertEqual(result["benchmark_status"], "benchmark_failed")

    def test_returns_result_dict_shape(self):
        result = _benchmark_texttok()
        self.assertIn("benchmark_status", result)


class BenchmarkSimsearchTests(SimpleTestCase):
    """The simsearch benchmark runs NumPy argpartition vs simsearch C++ extension."""

    def test_returns_error_result_on_kernel_failure(self):
        with patch(
            "numpy.argpartition",
            side_effect=RuntimeError("simulated"),
        ):
            result = _benchmark_simsearch()
        self.assertEqual(result["benchmark_status"], "benchmark_failed")

    def test_returns_result_dict_shape(self):
        result = _benchmark_simsearch()
        self.assertIn("benchmark_status", result)


class BenchmarkPagerankTests(SimpleTestCase):
    """The pagerank benchmark runs Python step kernel vs pagerank C++ extension."""

    def test_returns_error_result_on_kernel_failure(self):
        with patch(
            "apps.pipeline.services.weighted_pagerank._pagerank_step_py",
            side_effect=RuntimeError("simulated"),
        ):
            result = _benchmark_pagerank()
        self.assertEqual(result["benchmark_status"], "benchmark_failed")

    def test_returns_result_dict_shape(self):
        result = _benchmark_pagerank()
        self.assertIn("benchmark_status", result)


class BenchmarkFeedrerankTests(SimpleTestCase):
    """The feedrerank benchmark runs Python max-sim loop vs feedrerank C++ extension."""

    def test_returns_error_result_on_kernel_failure(self):
        with patch(
            "numpy.dot",
            side_effect=RuntimeError("simulated"),
        ):
            result = _benchmark_feedrerank()
        self.assertEqual(result["benchmark_status"], "benchmark_failed")

    def test_returns_result_dict_shape(self):
        result = _benchmark_feedrerank()
        self.assertIn("benchmark_status", result)


# ---------------------------------------------------------------------------
# Conflict detector helpers
# ---------------------------------------------------------------------------


class ConflictAnalyticsMissingTests(SimpleTestCase):
    """Analytics-missing conflict fires only when SearchMetric.objects.count() == 0."""

    @patch("apps.analytics.models.SearchMetric.objects")
    def test_returns_conflict_when_no_rows(self, mock_objects):
        mock_objects.count.return_value = 0
        result = _conflict_analytics_missing()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Analytics Data Missing")
        self.assertEqual(result[0]["severity"], "medium")

    @patch("apps.analytics.models.SearchMetric.objects")
    def test_returns_empty_when_rows_present(self, mock_objects):
        mock_objects.count.return_value = 1
        self.assertEqual(_conflict_analytics_missing(), [])


class ConflictOrphanedSuggestionsTests(SimpleTestCase):
    """Orphaned-suggestions conflict fires when destination__isnull=True count > 0."""

    @patch("apps.diagnostics.health.Suggestion")
    def test_returns_conflict_when_orphans_exist(self, mock_suggestion):
        mock_suggestion.objects.filter.return_value.count.return_value = 3
        result = _conflict_orphaned_suggestions()
        self.assertEqual(len(result), 1)
        self.assertIn("3 suggestion", result[0]["description"])
        self.assertEqual(result[0]["severity"], "high")

    @patch("apps.diagnostics.health.Suggestion")
    def test_returns_empty_when_no_orphans(self, mock_suggestion):
        mock_suggestion.objects.filter.return_value.count.return_value = 0
        self.assertEqual(_conflict_orphaned_suggestions(), [])


class ConflictNativeUnhealthyTests(SimpleTestCase):
    """Native-unhealthy conflict severity branches on failed vs degraded."""

    @patch("apps.diagnostics.health.check_native_scoring")
    def test_returns_empty_when_healthy(self, mock_check):
        mock_check.return_value = ("healthy", "", "", {})
        self.assertEqual(_conflict_native_unhealthy(), [])

    @patch("apps.diagnostics.health.check_native_scoring")
    def test_severity_is_high_when_failed(self, mock_check):
        mock_check.return_value = ("failed", "", "", {"fallback_reason": "boom"})
        result = _conflict_native_unhealthy()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["severity"], "high")
        self.assertEqual(result[0]["next_step"], "boom")

    @patch("apps.diagnostics.health.check_native_scoring")
    def test_severity_is_medium_when_degraded(self, mock_check):
        mock_check.return_value = ("degraded", "", "", {"fallback_reason": ""})
        result = _conflict_native_unhealthy()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["severity"], "medium")
        self.assertIn("Rebuild", result[0]["next_step"])


class ConflictDevRuntimeTests(SimpleTestCase):
    """Dev-runtime conflict fires only when DJANGO_SETTINGS_MODULE ends in '.development'."""

    @patch.dict("os.environ", {"DJANGO_SETTINGS_MODULE": "config.settings.development"})
    def test_returns_conflict_when_dev_settings_active(self):
        result = _conflict_dev_runtime()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Development Runtime Active")

    @patch.dict("os.environ", {"DJANGO_SETTINGS_MODULE": "config.settings.production"})
    def test_returns_empty_when_production_settings(self):
        self.assertEqual(_conflict_dev_runtime(), [])


class ConflictPlannedServicesTests(SimpleTestCase):
    """Planned-services conflict fires for each ga4/gsc snapshot in 'planned_only' state."""

    @patch("apps.diagnostics.health.ServiceStatusSnapshot")
    def test_returns_conflict_per_planned_only_snapshot(self, mock_snapshot):
        snapshot_planned = MagicMock(state="planned_only")
        snapshot_other = MagicMock(state="healthy")
        mock_snapshot.objects.get_or_create.side_effect = [
            (snapshot_planned, False),
            (snapshot_other, False),
        ]
        result = _conflict_planned_services()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["severity"], "low")

    @patch("apps.diagnostics.health.ServiceStatusSnapshot")
    def test_returns_empty_when_no_planned_only(self, mock_snapshot):
        snapshot_healthy = MagicMock(state="healthy")
        mock_snapshot.objects.get_or_create.return_value = (snapshot_healthy, False)
        self.assertEqual(_conflict_planned_services(), [])


class PersistConflictsTests(SimpleTestCase):
    """_persist_conflicts upserts each dict into SystemConflict via get_or_create."""

    @patch("apps.diagnostics.health.SystemConflict")
    def test_no_calls_on_empty_list(self, mock_model):
        _persist_conflicts([])
        self.assertFalse(mock_model.objects.get_or_create.called)

    @patch("apps.diagnostics.health.SystemConflict")
    def test_one_get_or_create_per_conflict(self, mock_model):
        conflicts = [
            {
                "type": "drift",
                "title": "A",
                "description": "d1",
                "severity": "low",
                "location": "loc1",
                "why": "w1",
                "next_step": "n1",
            },
            {
                "type": "mismatch",
                "title": "B",
                "description": "d2",
                "severity": "high",
                "location": "loc2",
                "why": "w2",
                "next_step": "n2",
            },
        ]
        _persist_conflicts(conflicts)
        self.assertEqual(mock_model.objects.get_or_create.call_count, 2)
        first_kwargs = mock_model.objects.get_or_create.call_args_list[0].kwargs
        self.assertEqual(first_kwargs["title"], "A")
        self.assertEqual(first_kwargs["defaults"]["conflict_type"], "drift")


# ---------------------------------------------------------------------------
# Sanity checks on existing pre-extraction helpers (regression guards)
# ---------------------------------------------------------------------------


class BenchmarkResultDispatchTests(SimpleTestCase):
    """The pre-existing _benchmark_result and _benchmark_error_result keep their contract."""

    def test_benchmarked_faster_when_speedup_high(self):
        result = _benchmark_result(10.0, 1.0)
        self.assertEqual(result["benchmark_status"], "benchmarked_faster")
        self.assertEqual(result["speedup_vs_python"], 10.0)
        self.assertTrue(result["proof_available"])

    def test_no_material_speedup_band(self):
        result = _benchmark_result(1.0, 1.0)
        self.assertEqual(result["benchmark_status"], "no_material_speedup")

    def test_slower_than_python_band(self):
        result = _benchmark_result(1.0, 5.0)
        self.assertEqual(result["benchmark_status"], "slower_than_python")

    def test_invalid_when_zero_or_negative(self):
        result = _benchmark_result(0.0, 1.0)
        self.assertEqual(result["benchmark_status"], "invalid_result")
        self.assertFalse(result["proof_available"])

    def test_error_result_shape(self):
        result = _benchmark_error_result(RuntimeError("boom"))
        self.assertEqual(result["benchmark_status"], "benchmark_failed")
        self.assertIn("boom", result["error"])
        self.assertFalse(result["proof_available"])
