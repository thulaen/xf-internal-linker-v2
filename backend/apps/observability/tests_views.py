"""Convention-named SimpleTestCase coverage for apps/observability/views.py.

``MetricsView`` guards the Prometheus scrape endpoint with a shared token, and
``ObservabilityStackView`` wraps the stack-status service. These tests call the
view ``get`` methods directly with a stub request, patch the heavy registry and
stack-status calls, and pin the exact status codes and bodies so the
diff-scoped mutation gate cannot survive a changed literal or flipped guard.
No real HTTP, database, or network access happens.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.observability import views


def _request(token: str | None) -> MagicMock:
    request = MagicMock()
    request.META = {}
    if token is not None:
        request.META["HTTP_X_METRICS_TOKEN"] = token
    return request


class MetricsViewTokenGuardTests(SimpleTestCase):
    @override_settings(METRICS_TOKEN="secret")
    def test_wrong_token_is_rejected_with_403_and_exact_detail(self) -> None:
        response = views.MetricsView().get(_request("nope"))
        # Exact status and exact detail string kill the literal mutations; a
        # substring check would let a reworded message survive.
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data, {"detail": "Metrics token is missing or wrong."})

    @override_settings(METRICS_TOKEN="secret")
    def test_correct_token_returns_prometheus_body(self) -> None:
        with patch.object(views, "generate_latest", return_value=b"# HELP x\n"), patch.object(
            views, "get_registry", return_value=MagicMock()
        ):
            response = views.MetricsView().get(_request("secret"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], views.CONTENT_TYPE_LATEST)

    @override_settings(METRICS_TOKEN="")
    def test_blank_expected_token_skips_the_guard(self) -> None:
        with patch.object(views, "generate_latest", return_value=b"# HELP x\n"), patch.object(
            views, "get_registry", return_value=MagicMock()
        ):
            response = views.MetricsView().get(_request(None))
        self.assertEqual(response.status_code, 200)


class ObservabilityStackViewTests(SimpleTestCase):
    def test_stack_view_wraps_service_status_under_services_key(self) -> None:
        with patch.object(views, "build_stack_status", return_value=[{"service_name": "Grafana"}]):
            response = views.ObservabilityStackView().get(_request(None))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"services": [{"service_name": "Grafana"}]})
