from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
import math
from apps.pipeline.services.score_calibration import (
    calibrated_probability,
    PlattParams,
    COLD_START_PARAMS,
    fit_platt_sigmoid,
    passes_calibrated_threshold,
    get_calibration_status,
    load_active_params,
    persist_active_params,
    train_calibration_sigmoid,
)

class _StopAfterGuard(Exception): pass

class ScoreCalibrationTests(SimpleTestCase):
    def test_calibrated_probability_default(self):
        # z = 6.0*0.25 - 1.5 = 0.0 -> 1/(1+1) = 0.5
        prob = calibrated_probability(0.25)
        self.assertEqual(prob, 0.5)

    def test_calibrated_probability_custom_params_positive_z(self):
        params = PlattParams(a=2.0, b=-0.5)
        # z = 2.0*1.0 - 0.5 = 1.5
        prob = calibrated_probability(1.0, params=params)
        expected = 1.0 / (1.0 + math.exp(-1.5))
        self.assertEqual(prob, expected)

    def test_calibrated_probability_custom_params_negative_z(self):
        params = PlattParams(a=2.0, b=-0.5)
        # z = 2.0*0.0 - 0.5 = -0.5
        prob = calibrated_probability(0.0, params=params)
        expected = math.exp(-0.5) / (1.0 + math.exp(-0.5))
        self.assertEqual(prob, expected)

    def test_train_calibration_sigmoid_logs(self):
        with patch('apps.pipeline.services.score_calibration.logger.info') as mock_info:
            train_calibration_sigmoid()
            mock_info.assert_called_once_with(
                "Skipping train_calibration_sigmoid: training-pipeline wire-in is deferred until >=1000 labeled pairs."
            )

    def test_fit_platt_sigmoid_mismatched_length(self):
        with self.assertRaisesMessage(ValueError, "scores and labels must have equal length"):
            fit_platt_sigmoid([1.0], [])

    def test_fit_platt_sigmoid_not_enough_pairs(self):
        with patch('apps.pipeline.services.score_calibration.logger.info') as mock_info:
            res = fit_platt_sigmoid([0.5], [1])
            self.assertIsNone(res)
            mock_info.assert_called_once_with(
                "FR-245 — validation set size %d below minimum %d; skipping fit",
                1,
                1000,
            )

    def test_fit_platt_sigmoid_degenerate_all_pos(self):
        scores = [0.5] * 1000
        labels = [1] * 1000
        with patch('apps.pipeline.services.score_calibration.logger.info') as mock_info:
            res = fit_platt_sigmoid(scores, labels)
            self.assertIsNone(res)
            mock_info.assert_called_once_with("FR-245 — degenerate labels (all-pos or all-neg); skipping fit")

    def test_fit_platt_sigmoid_degenerate_all_neg(self):
        scores = [0.5] * 1000
        labels = [0] * 1000
        with patch('apps.pipeline.services.score_calibration.logger.info') as mock_info:
            res = fit_platt_sigmoid(scores, labels)
            self.assertIsNone(res)
            mock_info.assert_called_once_with("FR-245 — degenerate labels (all-pos or all-neg); skipping fit")

    def test_fit_platt_sigmoid_valid(self):
        scores = [0.1] * 500 + [0.9] * 500
        labels = [0] * 500 + [1] * 500
        res = fit_platt_sigmoid(scores, labels, max_iters=2)
        self.assertIsNotNone(res)
        self.assertIsInstance(res, PlattParams)

    def test_passes_calibrated_threshold(self):
        self.assertTrue(passes_calibrated_threshold(0.25))
        self.assertFalse(passes_calibrated_threshold(0.24))

    @patch('apps.core.models.AppSetting.objects.filter')
    def test_load_active_params_none(self, mock_filter):
        mock_qs = MagicMock()
        mock_filter.return_value = mock_qs
        mock_qs.values_list.return_value = mock_qs
        mock_qs.first.return_value = None
        self.assertIsNone(load_active_params())

    @patch('apps.core.models.AppSetting.objects.filter')
    def test_load_active_params_valid(self, mock_filter):
        mock_qs_a = MagicMock()
        mock_qs_b = MagicMock()
        def filter_side_effect(key):
            if key == "pipeline.calibration_platt_a": return mock_qs_a
            return mock_qs_b
        mock_filter.side_effect = filter_side_effect
        mock_qs_a.values_list.return_value.first.return_value = "1.5"
        mock_qs_b.values_list.return_value.first.return_value = "-0.5"
        params = load_active_params()
        self.assertEqual(params.a, 1.5)
        self.assertEqual(params.b, -0.5)

    @patch('apps.core.models.AppSetting.objects.update_or_create')
    def test_persist_active_params(self, mock_uoc):
        params = PlattParams(a=1.5, b=-0.5)
        persist_active_params(params, validation_pairs=1000)
        self.assertEqual(mock_uoc.call_count, 4)

    @patch('apps.pipeline.services.score_calibration.load_active_params')
    def test_get_calibration_status_cold_start(self, mock_load):
        mock_load.return_value = None
        status = get_calibration_status()
        self.assertFalse(status["available"])
        self.assertEqual(status["path"], "cold_start_logistic")
        expected_reason = (
            "No fitted Platt sigmoid yet. Using cold-start logistic "
            f"params (A={COLD_START_PARAMS.a}, B={COLD_START_PARAMS.b}) "
            "tuned to roughly match the historical 0.25-cosine cutoff. "
            "Run ``pipeline.calibration_fit`` once the feedback store "
            "has ≥1000 approved/rejected pairs (Niculescu-Mizil & "
            "Caruana 2005 §4)."
        )
        self.assertEqual(status["reason"], expected_reason)

    @patch('apps.pipeline.services.score_calibration.load_active_params')
    @patch('apps.core.models.AppSetting.objects.filter')
    def test_get_calibration_status_active(self, mock_filter, mock_load):
        mock_load.return_value = PlattParams(a=1.5, b=-0.5)
        mock_qs = MagicMock()
        mock_filter.return_value = mock_qs
        mock_qs.values_list.return_value = mock_qs
        mock_qs.first.side_effect = ["2023-01-01", "1000"]
        status = get_calibration_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["path"], "fitted_platt_sigmoid")
        self.assertEqual(status["params_a"], 1.5)
        self.assertEqual(status["params_b"], -0.5)
        self.assertEqual(status["fitted_at"], "2023-01-01")
        self.assertEqual(status["validation_pairs"], 1000)
        expected_reason = (
            "Active Platt fit (A=1.5000, B=-0.5000) "
            "trained on 1000 pairs at 2023-01-01."
        )
        self.assertEqual(status["reason"], expected_reason)
