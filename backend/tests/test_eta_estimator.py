"""Tests for the ETA estimation service."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase

from apps.pipeline.services.eta_estimator import estimate_eta


class EtaEstimatorTests(TestCase):
    """Test ETA estimation from historical run durations."""

    @patch("apps.pipeline.services.eta_estimator._get_historical_durations")
    def test_returns_none_with_insufficient_history(self, mock_durations):
        mock_durations.return_value = [100.0, 200.0]  # Only 2, need 3
        result = estimate_eta("nightly-xenforo-sync")
        assert result is None

    @patch("apps.pipeline.services.eta_estimator._get_historical_durations")
    def test_returns_median_duration(self, mock_durations):
        mock_durations.return_value = [100.0, 200.0, 300.0]
        result = estimate_eta("nightly-xenforo-sync")
        assert result == timedelta(seconds=200.0)

    @patch("apps.pipeline.services.eta_estimator._get_historical_durations")
    def test_subtracts_elapsed_for_running_tasks(self, mock_durations):
        mock_durations.return_value = [100.0, 200.0, 300.0]
        result = estimate_eta("nightly-xenforo-sync", elapsed_seconds=150.0)
        # median=200, elapsed=150, remaining=50
        assert result == timedelta(seconds=50.0)

    @patch("apps.pipeline.services.eta_estimator._get_historical_durations")
    def test_finishing_soon_when_over_median(self, mock_durations):
        mock_durations.return_value = [100.0, 200.0, 300.0]
        result = estimate_eta("nightly-xenforo-sync", elapsed_seconds=250.0)
        # Over median — should return small positive (30s "finishing soon")
        assert result == timedelta(seconds=30)

    @patch("apps.pipeline.services.eta_estimator._get_historical_durations")
    def test_even_number_of_durations(self, mock_durations):
        mock_durations.return_value = [100.0, 200.0, 300.0, 400.0]
        result = estimate_eta("nightly-xenforo-sync")
        # median of [100,200,300,400] = 250
        assert result == timedelta(seconds=250.0)
