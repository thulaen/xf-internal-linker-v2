"""Tests for W3a — Platt score calibration service (pick #32 wiring)."""

from __future__ import annotations

from django.test import TestCase

from apps.pipeline.services.score_calibrator import (
    KEY_BIAS,
    KEY_SLOPE,
    MIN_TRAINING_PAIRS,
    CalibrationSnapshot,
    calibrate_score,
    fit_and_persist_from_history,
    load_snapshot,
)


class LoadSnapshotTests(TestCase):
    def test_cold_start_returns_none(self) -> None:
        self.assertIsNone(load_snapshot())

    def test_returns_snapshot_after_persist(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_SLOPE, defaults={"value": "-1.5", "description": ""}
        )
        AppSetting.objects.update_or_create(
            key=KEY_BIAS, defaults={"value": "0.3", "description": ""}
        )
        snap = load_snapshot()
        self.assertIsNotNone(snap)
        self.assertAlmostEqual(snap.slope, -1.5)
        self.assertAlmostEqual(snap.bias, 0.3)

    def test_malformed_value_returns_none(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_SLOPE, defaults={"value": "not-a-number", "description": ""}
        )
        AppSetting.objects.update_or_create(
            key=KEY_BIAS, defaults={"value": "0.0", "description": ""}
        )
        self.assertIsNone(load_snapshot())


class CalibrateScoreTests(TestCase):
    def test_cold_start_returns_raw_score(self) -> None:
        # Without calibration, the helper falls back to identity so
        # the review UI doesn't lie about confidence.
        self.assertAlmostEqual(calibrate_score(0.42), 0.42)

    def test_calibration_maps_score_to_probability(self) -> None:
        snapshot = CalibrationSnapshot(
            slope=-2.0,
            bias=0.0,
            fitted_at=None,
            training_pairs=100,
        )
        # PlattCalibration.predict uses 1 / (1 + exp(slope*x + bias)).
        # slope=-2, bias=0 → score 0 → P=0.5; score 1 → P > 0.5.
        self.assertAlmostEqual(
            calibrate_score(0.0, snapshot=snapshot), 0.5
        )
        self.assertGreater(
            calibrate_score(1.0, snapshot=snapshot), 0.5
        )


class FitAndPersistTests(TestCase):
    """Use synthetic training pairs (mocked DB query) so the test
    doesn't need a full ContentItem + Sentence + PipelineRun fixture
    chain just to write a few Suggestion rows."""

    def test_returns_none_when_history_too_small(self) -> None:
        # Empty review history → not enough pairs to fit.
        result = fit_and_persist_from_history()
        self.assertIsNone(result)
        self.assertIsNone(load_snapshot())

    def test_returns_none_when_only_one_class(self) -> None:
        from unittest.mock import patch

        from apps.pipeline.services import score_calibrator

        # All-approvals stream — Platt can't fit a sigmoid.
        synthetic = [(0.5 + 0.01 * i, 1) for i in range(MIN_TRAINING_PAIRS + 5)]
        with patch.object(
            score_calibrator,
            "_collect_training_pairs",
            return_value=iter(synthetic),
        ):
            self.assertIsNone(fit_and_persist_from_history())
        self.assertIsNone(load_snapshot())

    def test_persists_snapshot_on_balanced_set(self) -> None:
        from unittest.mock import patch

        from apps.pipeline.services import score_calibrator

        # Balanced stream above MIN_TRAINING_PAIRS — Platt should fit
        # cleanly and the snapshot should round-trip.
        synthetic = [
            (0.9, 1) if i % 2 == 0 else (0.1, 0)
            for i in range(MIN_TRAINING_PAIRS + 20)
        ]
        with patch.object(
            score_calibrator,
            "_collect_training_pairs",
            return_value=iter(synthetic),
        ):
            snapshot = fit_and_persist_from_history()
        self.assertIsNotNone(snapshot)
        loaded = load_snapshot()
        self.assertIsNotNone(loaded)
        self.assertAlmostEqual(loaded.slope, snapshot.slope, places=4)
        self.assertEqual(loaded.training_pairs, len(synthetic))
