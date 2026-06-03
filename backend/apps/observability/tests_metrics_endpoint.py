from __future__ import annotations

from django.test import TestCase, override_settings
from apps.observability.api import Counter, register_metric


class MetricsEndpointTests(TestCase):
    @override_settings(METRICS_TOKEN="secret")
    def test_metrics_endpoint_requires_token(self):
        """Given no token, When /metrics is scraped, Then it rejects access."""
        response = self.client.get("/metrics/")
        self.assertEqual(response.status_code, 403)

    @override_settings(METRICS_TOKEN="secret")
    def test_metrics_endpoint_returns_prometheus_text(self):
        """Given token, When /metrics is scraped, Then text format is returned."""
        response = self.client.get("/metrics/", HTTP_X_METRICS_TOKEN="secret")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("# HELP", body)
        self.assertIn("# TYPE", body)

    @override_settings(METRICS_TOKEN="secret")
    def test_register_metric_exposes_same_registry(self):
        """Given registered counter, When scraped, Then metric appears."""
        metric = register_metric(Counter, "xf_test_contract_total", "test contract")
        metric.inc()

        response = self.client.get("/metrics/", HTTP_X_METRICS_TOKEN="secret")

        self.assertContains(response, "xf_test_contract_total")
