"""Tests for the pure-function helpers extracted from diagnostics/views.py.

These helpers replaced ~700 lines of inlined branching across the
9 long ``get``/``post``/``_*_tile`` entrypoints. Each is independently
testable in ``SimpleTestCase`` (no DB) so a future tweak to a state
threshold or message string shows up here before it ships.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.diagnostics.views import (
    _apply_root_cause_dedup,
    _build_embeddings_label,
    _classify_anti_spam,
    _classify_helper_nodes,
    _classify_model_runtime,
    _count_signal_errors,
    _embeddings_tile_message,
    _pipeline_tile,
    _resolve_signal_cpp_status,
    _resolve_signal_weight,
    _signals_tile,
    _suggestion_readiness_tile,
)


class BuildEmbeddingsLabelTests(SimpleTestCase):
    """``_build_embeddings_label`` formats the ``model on device`` label."""

    def test_active_model_with_dimension(self):
        name, label = _build_embeddings_label(
            {"model_name": "BAAI/bge-m3", "dimension": 1024, "device_target": "cuda"},
            {},
        )
        self.assertEqual(name, "BAAI/bge-m3")
        self.assertEqual(label, "BAAI/bge-m3 on cuda (1024d)")

    def test_falls_back_to_runtime_device(self):
        _, label = _build_embeddings_label({"model_name": "x"}, {"device": "cpu"})
        self.assertEqual(label, "x on cpu")

    def test_default_model_when_missing(self):
        name, label = _build_embeddings_label({}, {})
        self.assertEqual(name, "BAAI/bge-m3")
        self.assertEqual(label, "BAAI/bge-m3 on cpu")


class EmbeddingsTileMessageTests(SimpleTestCase):
    """``_embeddings_tile_message`` formats the progress sentence."""

    def test_complete_uses_all_phrasing(self):
        msg = _embeddings_tile_message(
            done=10,
            total=10,
            model_label="bge",
            helper_assisted=True,
        )
        self.assertIn("All 10 items", msg)
        self.assertIn("Helper-assisted: yes", msg)

    def test_partial_uses_n_of_m(self):
        msg = _embeddings_tile_message(
            done=3,
            total=10,
            model_label="bge",
            helper_assisted=False,
        )
        self.assertIn("3 of 10 items", msg)
        self.assertIn("Helper-assisted: no", msg)


class ClassifyModelRuntimeTests(SimpleTestCase):
    """``_classify_model_runtime`` picks the right tile by status."""

    def _call(self, **kwargs):
        defaults = {
            "active_name": "bge-m3",
            "active_status": "ready",
            "device": "cuda",
            "backfill": {},
            "candidate_model": {},
        }
        defaults.update(kwargs)
        return _classify_model_runtime(**defaults)

    def test_failed_status_returns_failed(self):
        tile = self._call(active_status="failed")
        self.assertEqual(tile["state"], "FAILED")

    def test_running_backfill_returns_degraded_with_progress(self):
        tile = self._call(backfill={"status": "running", "progress_pct": 50.0})
        self.assertEqual(tile["state"], "DEGRADED")
        self.assertAlmostEqual(tile["progress"], 0.50)

    def test_candidate_model_returns_degraded(self):
        tile = self._call(candidate_model={"model_name": "new", "status": "warming"})
        self.assertEqual(tile["state"], "DEGRADED")
        self.assertIn("Candidate", tile["plain_english"])

    def test_no_blockers_returns_working(self):
        tile = self._call()
        self.assertEqual(tile["state"], "WORKING")


class ClassifyHelperNodesTests(SimpleTestCase):
    """``_classify_helper_nodes`` thresholds: 0/0/0/0 → IDLE; high RAM → DEGRADED."""

    def _call(self, **kwargs):
        defaults = {
            "online": 0,
            "busy": 0,
            "stale": 0,
            "offline": 0,
            "aggregate_ram_pressure": 0.0,
            "busiest": {},
        }
        defaults.update(kwargs)
        return _classify_helper_nodes(**defaults)

    def test_no_helpers_returns_idle(self):
        tile = self._call()
        self.assertEqual(tile["state"], "IDLE")

    def test_all_offline_returns_failed(self):
        tile = self._call(offline=2)
        self.assertEqual(tile["state"], "FAILED")

    def test_all_offline_with_stale_returns_degraded(self):
        tile = self._call(offline=1, stale=1)
        self.assertEqual(tile["state"], "DEGRADED")

    def test_high_ram_pressure_returns_degraded(self):
        tile = self._call(online=2, aggregate_ram_pressure=0.95, busiest={"name": "h1"})
        self.assertEqual(tile["state"], "DEGRADED")

    def test_normal_returns_working(self):
        tile = self._call(online=2, busy=1, aggregate_ram_pressure=0.4)
        self.assertEqual(tile["state"], "WORKING")


class ClassifyAntiSpamTests(SimpleTestCase):
    """``_classify_anti_spam`` flags disabled / zero-weight signals."""

    def test_all_enabled_with_weight_returns_working(self):
        tile = _classify_anti_spam(
            {
                "Anchor diversity": {"enabled": True, "ranking_weight": 0.05},
                "Keyword stuffing": {"enabled": True, "ranking_weight": 0.05},
                "Link farm": {"enabled": True, "ranking_weight": 0.05},
            }
        )
        self.assertEqual(tile["state"], "WORKING")

    def test_one_disabled_returns_degraded(self):
        tile = _classify_anti_spam(
            {
                "Anchor diversity": {"enabled": False, "ranking_weight": 0.05},
                "Keyword stuffing": {"enabled": True, "ranking_weight": 0.05},
                "Link farm": {"enabled": True, "ranking_weight": 0.05},
            }
        )
        self.assertEqual(tile["state"], "DEGRADED")
        self.assertIn("Disabled signals", tile["plain_english"])

    def test_zero_weight_returns_degraded(self):
        tile = _classify_anti_spam(
            {
                "Anchor diversity": {"enabled": True, "ranking_weight": 0.0},
                "Keyword stuffing": {"enabled": True, "ranking_weight": 0.05},
                "Link farm": {"enabled": True, "ranking_weight": 0.05},
            }
        )
        self.assertEqual(tile["state"], "DEGRADED")
        self.assertIn("Zero-weight signals", tile["plain_english"])


class PipelineTileTests(SimpleTestCase):
    """``_pipeline_tile`` priority: master_pause → heavy_lock → idle."""

    def test_master_pause_wins(self):
        tile = _pipeline_tile({"heavy": "import:foo"}, master_pause=True)
        self.assertEqual(tile["state"], "PAUSED")
        self.assertIn("Resume", tile["actions"])

    def test_heavy_holder_returns_working(self):
        tile = _pipeline_tile({"heavy": "import:foo"}, master_pause=False)
        self.assertEqual(tile["state"], "WORKING")
        self.assertIn("import", tile["plain_english"])

    def test_no_holder_no_pause_returns_idle(self):
        tile = _pipeline_tile({}, master_pause=False)
        self.assertEqual(tile["state"], "IDLE")


class SignalsTileTests(SimpleTestCase):
    """``_signals_tile`` mirrors pipeline pattern but for signal lock."""

    def test_signal_holder_returns_working(self):
        tile = _signals_tile({"signal": "compute_signal_phrase_quality"})
        self.assertEqual(tile["state"], "WORKING")

    def test_no_holder_returns_idle(self):
        tile = _signals_tile({})
        self.assertEqual(tile["state"], "IDLE")


class SuggestionReadinessTileTests(SimpleTestCase):
    """``_suggestion_readiness_tile`` flags blocking prereqs."""

    def test_all_ready_returns_working(self):
        tile = _suggestion_readiness_tile(
            [
                {"id": "x", "status": "ready", "name": "X", "plain_english": "x"},
            ]
        )
        self.assertEqual(tile["state"], "WORKING")

    def test_blocked_status_returns_failed(self):
        tile = _suggestion_readiness_tile(
            [
                {"id": "x", "status": "blocked", "name": "X", "plain_english": "x"},
            ]
        )
        self.assertEqual(tile["state"], "FAILED")

    def test_other_non_ready_status_returns_degraded(self):
        tile = _suggestion_readiness_tile(
            [
                {"id": "x", "status": "warming", "name": "X", "plain_english": "x"},
            ]
        )
        self.assertEqual(tile["state"], "DEGRADED")


class ApplyRootCauseDedupTests(SimpleTestCase):
    """``_apply_root_cause_dedup`` collapses tiles below pipeline_gate=blocked."""

    def test_blocked_pipeline_marks_dependent_tiles(self):
        tiles = [
            {"id": "pipeline", "group": None, "root_cause": None},
            {"id": "embeddings", "group": None, "root_cause": None},
            {"id": "weight_tuning", "group": "algorithms", "root_cause": None},
            {"id": "external_gsc", "group": None, "root_cause": None},
        ]
        prereqs = [{"id": "pipeline_gate", "status": "blocked"}]
        _apply_root_cause_dedup(tiles, prereqs)
        self.assertEqual(tiles[0]["root_cause"], "pipeline_gate")
        self.assertEqual(tiles[1]["root_cause"], "pipeline_gate")
        self.assertEqual(tiles[2]["root_cause"], "pipeline_gate")
        # External tiles do NOT get marked.
        self.assertIsNone(tiles[3]["root_cause"])

    def test_unblocked_pipeline_does_nothing(self):
        tiles = [{"id": "pipeline", "group": None, "root_cause": None}]
        _apply_root_cause_dedup(tiles, [{"id": "pipeline_gate", "status": "ready"}])
        self.assertIsNone(tiles[0]["root_cause"])


class ResolveSignalWeightTests(SimpleTestCase):
    """``_resolve_signal_weight`` parses the AppSetting into a float."""

    def _sig(self, weight_key="ranking.foo.weight"):
        sig = mock.Mock()
        sig.weight_key = weight_key
        return sig

    def test_returns_float_when_key_present(self):
        self.assertEqual(
            _resolve_signal_weight(self._sig(), {"ranking.foo.weight": "0.05"}), 0.05
        )

    def test_default_zero_when_missing(self):
        self.assertEqual(_resolve_signal_weight(self._sig(), {}), 0.0)

    def test_no_weight_key_returns_zero(self):
        # When sig.weight_key is None, the helper short-circuits to "N/A"
        # internally, then converts that sentinel back to 0.0 so downstream
        # JSON consumers see a numeric type. This is the contract the UI
        # cards rely on (zero-weight = signal not contributing).
        sig = self._sig(weight_key=None)
        self.assertEqual(_resolve_signal_weight(sig, {}), 0.0)

    def test_invalid_value_returns_passthrough(self):
        # Non-float values pass through (legacy / accidental string).
        self.assertEqual(
            _resolve_signal_weight(self._sig(), {"ranking.foo.weight": "abc"}),
            "abc",
        )


class ResolveSignalCppStatusTests(SimpleTestCase):
    """``_resolve_signal_cpp_status`` returns ``(active, status_label)``."""

    def _sig(self, cpp_kernel=None):
        sig = mock.Mock()
        sig.cpp_kernel = cpp_kernel
        return sig

    def test_no_kernel_returns_not_supported(self):
        active, label = _resolve_signal_cpp_status(self._sig(), {})
        self.assertFalse(active)
        self.assertEqual(label, "Not Supported")

    def test_kernel_not_loaded(self):
        active, label = _resolve_signal_cpp_status(
            self._sig(cpp_kernel="scoring.matmul"),
            {},
        )
        self.assertFalse(active)
        self.assertEqual(label, "Available (Not Loaded)")

    def test_healthy_kernel(self):
        active, label = _resolve_signal_cpp_status(
            self._sig(cpp_kernel="scoring.matmul"),
            {"scoring": {"state": "healthy"}},
        )
        self.assertTrue(active)
        self.assertEqual(label, "Active (C++)")

    def test_degraded_kernel(self):
        active, label = _resolve_signal_cpp_status(
            self._sig(cpp_kernel="scoring.matmul"),
            {"scoring": {"state": "degraded"}},
        )
        self.assertFalse(active)
        self.assertEqual(label, "Degraded (Python Fallback)")


class CountSignalErrorsTests(SimpleTestCase):
    """``_count_signal_errors`` matches by signal id or kernel module."""

    def _sig(self, sig_id="phrase_quality", cpp_kernel=None):
        sig = mock.Mock()
        sig.id = sig_id
        sig.cpp_kernel = cpp_kernel
        return sig

    def test_matches_signal_id_substring(self):
        n = _count_signal_errors(
            self._sig(),
            {"signal_compute:phrase_quality_train": 3},
        )
        self.assertEqual(n, 3)

    def test_matches_kernel_module(self):
        n = _count_signal_errors(
            self._sig(sig_id="other", cpp_kernel="scoring.matmul"),
            {"matmul:scoring_init": 5},
        )
        self.assertEqual(n, 5)

    def test_unrelated_keys_not_counted(self):
        n = _count_signal_errors(
            self._sig(),
            {"unrelated:thing": 99},
        )
        self.assertEqual(n, 0)
