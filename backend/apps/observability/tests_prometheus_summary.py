"""Tests for the Prometheus summary service and view.

TDD cycle:
- RED: tests written first, then the implementation was added
- GREEN: all tests pass after implementation

These tests avoid Docker/network — they mock _instant_query so no real
VictoriaMetrics connection is needed. Django SimpleTestCase so no DB
required. Covers:
  - happy path: float values returned
  - VictoriaMetrics down: "unavailable" state for all metrics
  - no data (metric not emitted yet): "no_data" state
  - NaN/Inf values: treated as "no_data"
  - view authentication: 401 without credentials
  - view returns correct HTTP 200 with dict payload when authenticated
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.observability.services.prometheus_summary import (
    _instant_query,
    get_prometheus_summary,
)


class TestInstantQuery(SimpleTestCase):
    """Unit-test the VictoriaMetrics HTTP helper in isolation."""

    def test_returns_float_on_success(self):
        """A well-formed single-result response returns a float."""
        mock_payload = b'{"data":{"result":[{"value":[1718000000,"3.14"]}]}}'
        with patch("urllib.request.urlopen") as mock_open:
            mock_cm = mock_open.return_value.__enter__.return_value
            mock_cm.read.return_value = mock_payload
            result = _instant_query('up{job="backend"}')
        self.assertEqual(result, 3.14)

    def test_returns_unavailable_on_url_error(self):
        """A connection error returns an 'unavailable:' string."""
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            result = _instant_query('up{job="backend"}')
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("unavailable:"))

    def test_returns_no_data_on_empty_result(self):
        """An empty result list (metric not scraped yet) returns 'no_data'."""
        mock_payload = b'{"data":{"result":[]}}'
        with patch("urllib.request.urlopen") as mock_open:
            mock_cm = mock_open.return_value.__enter__.return_value
            mock_cm.read.return_value = mock_payload
            result = _instant_query('xf_missing_metric')
        self.assertEqual(result, "no_data")

    def test_returns_no_data_on_nan_value(self):
        """A 'NaN' value (histogram_quantile with no data) returns 'no_data'."""
        mock_payload = b'{"data":{"result":[{"value":[1718000000,"NaN"]}]}}'
        with patch("urllib.request.urlopen") as mock_open:
            mock_cm = mock_open.return_value.__enter__.return_value
            mock_cm.read.return_value = mock_payload
            result = _instant_query('histogram_quantile(0.95, ...)')
        self.assertEqual(result, "no_data")

    def test_returns_no_data_on_inf(self):
        """A '+Inf' value returns 'no_data'."""
        mock_payload = b'{"data":{"result":[{"value":[1718000000,"+Inf"]}]}}'
        with patch("urllib.request.urlopen") as mock_open:
            mock_cm = mock_open.return_value.__enter__.return_value
            mock_cm.read.return_value = mock_payload
            result = _instant_query('some_metric')
        self.assertEqual(result, "no_data")


class TestGetPrometheusSummary(SimpleTestCase):
    """Unit-test the summary aggregator function."""

    def test_all_ok_when_all_queries_return_floats(self):
        """All metrics show state='ok' when every query returns a number."""
        with patch(
            "apps.observability.services.prometheus_summary._instant_query",
            return_value=1.0,
        ):
            result = get_prometheus_summary()
        self.assertIn("request_rate_per_sec", result)
        for key, entry in result.items():
            self.assertEqual(entry["state"], "ok", f"{key} should be ok")
            self.assertIsInstance(entry["value"], float)
            self.assertIn("unit", entry)
            self.assertIn("description", entry)

    def test_unavailable_state_when_vm_is_down(self):
        """All metrics show state='unavailable' when VictoriaMetrics is down."""
        with patch(
            "apps.observability.services.prometheus_summary._instant_query",
            return_value="unavailable: Connection refused",
        ):
            result = get_prometheus_summary()
        for key, entry in result.items():
            self.assertEqual(entry["state"], "unavailable", f"{key} should be unavailable")
            self.assertIsNone(entry["value"])

    def test_no_data_state_when_metric_not_emitted_yet(self):
        """All metrics show state='no_data' when no series exist yet."""
        with patch(
            "apps.observability.services.prometheus_summary._instant_query",
            return_value="no_data",
        ):
            result = get_prometheus_summary()
        for key, entry in result.items():
            self.assertEqual(entry["state"], "no_data", f"{key} should be no_data")
            self.assertIsNone(entry["value"])

    def test_required_keys_always_present(self):
        """The six expected keys are always present in the result."""
        with patch(
            "apps.observability.services.prometheus_summary._instant_query",
            return_value="no_data",
        ):
            result = get_prometheus_summary()
        expected_keys = {
            "request_rate_per_sec",
            "latency_p95_seconds",
            "error_rate_per_sec",
            "ranking_latency_p95_seconds",
            "db_connections",
            "embedding_queue_depth",
        }
        self.assertEqual(set(result.keys()), expected_keys)


class TestPrometheusSummaryView(TestCase):
    """Integration tests for the DRF view (requires DB for auth)."""

    def test_unauthenticated_returns_401(self):
        """Hitting the endpoint without auth returns 401 (or 403)."""
        url = "/api/observability/prometheus-summary/"
        response = self.client.get(url)
        self.assertIn(response.status_code, (401, 403))

    def test_authenticated_returns_200_with_metric_keys(self):
        """An authenticated request returns 200 with the expected metric keys."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(username="test_metrics_user", password="testpass123")  # noqa: S106
        self.client.login(username="test_metrics_user", password="testpass123")  # noqa: S106
        with patch(
            "apps.observability.services.prometheus_summary._instant_query",
            return_value=0.5,
        ):
            response = self.client.get("/api/observability/prometheus-summary/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("request_rate_per_sec", data)
        self.assertIn("latency_p95_seconds", data)
        user.delete()
