"""Focused tests for the per-row helpers in ``pipeline_persist``.

Each helper extracted from ``_build_suggestion_records`` gets its own test
class. ``unittest.mock`` patches out the calibration / conformal / QL
loaders, so every test runs as ``SimpleTestCase`` (no DB).
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.pipeline.services import pipeline_persist as pp


class SafeLoadCalibrationSnapshotTests(SimpleTestCase):
    def test_returns_value_from_loader(self) -> None:
        sentinel = object()
        with patch(
            "apps.pipeline.services.score_calibrator.load_snapshot",
            return_value=sentinel,
        ):
            self.assertIs(pp._safe_load_calibration_snapshot(), sentinel)

    def test_failure_returns_none_and_calls_ingest_error(self) -> None:
        with (
            patch(
                "apps.pipeline.services.score_calibrator.load_snapshot",
                side_effect=RuntimeError("fixture missing"),
            ),
            patch("apps.audit.error_ingest.ingest_error") as ingest,
        ):
            out = pp._safe_load_calibration_snapshot()

        self.assertIsNone(out)
        ingest.assert_called_once()
        self.assertEqual(
            ingest.call_args.kwargs["step"], "load_calibration_snapshot"
        )


class SafeLoadConformalSnapshotTests(SimpleTestCase):
    def test_returns_value_from_loader(self) -> None:
        sentinel = object()
        with patch(
            "apps.pipeline.services.conformal_predictor.load_snapshot",
            return_value=sentinel,
        ):
            self.assertIs(pp._safe_load_conformal_snapshot(), sentinel)

    def test_failure_returns_none_and_logs_via_ingest_error(self) -> None:
        with (
            patch(
                "apps.pipeline.services.conformal_predictor.load_snapshot",
                side_effect=ValueError("bad row"),
            ),
            patch("apps.audit.error_ingest.ingest_error") as ingest,
        ):
            out = pp._safe_load_conformal_snapshot()

        self.assertIsNone(out)
        self.assertEqual(ingest.call_args.kwargs["step"], "load_conformal_snapshot")


class SafeBuildQlStatsTests(SimpleTestCase):
    def test_returns_none_when_baseline_missing(self) -> None:
        self.assertIsNone(pp._safe_build_ql_stats(None))

    def test_returns_none_when_total_terms_zero(self) -> None:
        baseline = SimpleNamespace(total_terms=0, term_counts={})
        self.assertIsNone(pp._safe_build_ql_stats(baseline))

    def test_constructs_stats_when_baseline_non_empty(self) -> None:
        baseline = SimpleNamespace(total_terms=42, term_counts={"foo": 5})
        with patch(
            "apps.pipeline.services.query_likelihood.CollectionStatistics"
        ) as Stats:
            Stats.return_value = "stats-instance"
            out = pp._safe_build_ql_stats(baseline)

        self.assertEqual(out, "stats-instance")
        Stats.assert_called_once_with(
            collection_term_counts={"foo": 5}, collection_length=42
        )


class LoadPersistenceSnapshotsTests(SimpleTestCase):
    def test_bundles_results_from_three_sub_helpers(self) -> None:
        baseline = SimpleNamespace(total_terms=10, term_counts={})
        with (
            patch.object(
                pp, "_safe_load_calibration_snapshot", return_value="calib"
            ),
            patch.object(
                pp, "_safe_load_conformal_snapshot", return_value="conf"
            ),
            patch.object(pp, "_safe_build_ql_stats", return_value="ql"),
        ):
            snaps = pp._load_persistence_snapshots(baseline)

        self.assertEqual(snaps.calibration, "calib")
        self.assertEqual(snaps.conformal, "conf")
        self.assertEqual(snaps.ql_stats, "ql")


class ComputeQlLogScoreTests(SimpleTestCase):
    def test_returns_zero_when_ql_stats_is_none(self) -> None:
        host = SimpleNamespace(text="any")
        dest = SimpleNamespace(distilled_text="any")

        self.assertEqual(pp._compute_ql_log_score(host, dest, ql_stats=None), 0.0)

    def test_returns_zero_when_query_or_doc_tokens_empty(self) -> None:
        host = SimpleNamespace(text="")
        dest = SimpleNamespace(distilled_text="")
        with (
            patch(
                "apps.pipeline.services.text_tokens.tokenize_text", return_value=[]
            ),
            patch(
                "apps.pipeline.services.query_likelihood.score_document"
            ) as score,
            patch(
                "apps.pipeline.services.query_likelihood.tokenised_to_counter"
            ),
        ):
            out = pp._compute_ql_log_score(host, dest, ql_stats=MagicMock())

        self.assertEqual(out, 0.0)
        score.assert_not_called()

    def test_returns_log_score_when_corpus_present(self) -> None:
        host = SimpleNamespace(text="alpha beta")
        dest = SimpleNamespace(distilled_text="alpha gamma")
        ql_stats = MagicMock()
        with (
            patch(
                "apps.pipeline.services.text_tokens.tokenize_text",
                side_effect=[["alpha", "beta"], ["alpha", "gamma"]],
            ),
            patch(
                "apps.pipeline.services.query_likelihood.tokenised_to_counter",
                side_effect=lambda toks: {t: 1 for t in toks},
            ),
            patch(
                "apps.pipeline.services.query_likelihood.score_document",
                return_value=SimpleNamespace(log_score=-3.14),
            ),
        ):
            out = pp._compute_ql_log_score(host, dest, ql_stats=ql_stats)

        self.assertAlmostEqual(out, -3.14)

    def test_failure_falls_back_to_zero_and_calls_ingest_error(self) -> None:
        host = SimpleNamespace(text="x")
        dest = SimpleNamespace(distilled_text="y")
        with (
            patch(
                "apps.pipeline.services.text_tokens.tokenize_text",
                side_effect=KeyError("boom"),
            ),
            patch("apps.audit.error_ingest.ingest_error") as ingest,
        ):
            out = pp._compute_ql_log_score(host, dest, ql_stats=MagicMock())

        self.assertEqual(out, 0.0)
        self.assertEqual(ingest.call_args.kwargs["step"], "compute_ql_log_score")


class ComputeCalibratedProbabilityTests(SimpleTestCase):
    def test_returns_none_when_no_snapshot(self) -> None:
        self.assertIsNone(pp._compute_calibrated_probability(0.7, snapshot=None))

    def test_passes_through_calibrate_score(self) -> None:
        with patch(
            "apps.pipeline.services.score_calibrator.calibrate_score",
            return_value=0.42,
        ) as calibrate:
            out = pp._compute_calibrated_probability(0.7, snapshot="snap")

        self.assertEqual(out, 0.42)
        calibrate.assert_called_once_with(0.7, snapshot="snap")


class ComputeLeastConfidenceUncertaintyTests(SimpleTestCase):
    def test_none_in_returns_none_out(self) -> None:
        self.assertIsNone(pp._compute_least_confidence_uncertainty(None))

    def test_returns_half_at_max_uncertainty(self) -> None:
        self.assertAlmostEqual(
            pp._compute_least_confidence_uncertainty(0.5), 0.5
        )

    def test_returns_low_uncertainty_for_confident_probability(self) -> None:
        self.assertAlmostEqual(
            pp._compute_least_confidence_uncertainty(0.9), 0.1
        )

    def test_symmetric_around_half(self) -> None:
        self.assertAlmostEqual(
            pp._compute_least_confidence_uncertainty(0.1), 0.1
        )


class ComputeConformalBandTests(SimpleTestCase):
    def test_returns_none_pair_on_cold_start(self) -> None:
        self.assertEqual(pp._compute_conformal_band(0.7, snapshot=None), (None, None))

    def test_unpacks_lower_and_upper_from_predict_interval(self) -> None:
        snapshot = MagicMock()
        snapshot.to_calibration.return_value.predict_interval.return_value = (
            SimpleNamespace(lower=0.42, upper=0.71)
        )
        lower, upper = pp._compute_conformal_band(0.6, snapshot=snapshot)

        self.assertAlmostEqual(lower, 0.42)
        self.assertAlmostEqual(upper, 0.71)
        snapshot.to_calibration.return_value.predict_interval.assert_called_once_with(
            0.6
        )


class ConstantsTests(SimpleTestCase):
    def test_elo_default_matches_documented_value(self) -> None:
        self.assertEqual(pp._ELO_DEFAULT_RATING, 1500.0)

    def test_elo_default_within_published_range(self) -> None:
        self.assertGreater(pp._ELO_DEFAULT_RATING, 0.0)
        self.assertTrue(math.isfinite(pp._ELO_DEFAULT_RATING))
