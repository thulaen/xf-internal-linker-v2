"""Convention-named SimpleTestCase coverage for apps/observability/urls.py.

The app exposes two routes — ``stack/`` (bound to ``ObservabilityStackView``)
and ``prometheus-summary/`` (bound to ``PrometheusSummaryView``) — namespaced
under ``observability``. These tests inspect the URL patterns and the namespace
directly (no request, no database, no network). Exact ``assertEqual`` on each
route string, the namespace, the name, and the bound view class pins every
literal so the diff-scoped mutation gate cannot survive a changed constant or a
swapped view.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability import urls
from apps.observability.views import ObservabilityStackView, PrometheusSummaryView


class ObservabilityUrlConfTests(SimpleTestCase):
    def test_app_name_is_observability(self) -> None:
        self.assertEqual(urls.app_name, "observability")

    def test_exactly_two_routes_are_declared(self) -> None:
        # Exact count kills the +1/-1 mutation that would survive a >= check.
        self.assertEqual(len(urls.urlpatterns), 2)

    def test_stack_route_pattern_name_and_view(self) -> None:
        entry = urls.urlpatterns[0]
        self.assertEqual(str(entry.pattern), "stack/")
        self.assertEqual(entry.name, "stack")
        bound_view = entry.callback
        self.assertIs(bound_view.view_class, ObservabilityStackView)

    def test_prometheus_summary_route_pattern_name_and_view(self) -> None:
        entry = urls.urlpatterns[1]
        self.assertEqual(str(entry.pattern), "prometheus-summary/")
        self.assertEqual(entry.name, "prometheus-summary")
        self.assertIs(entry.callback.view_class, PrometheusSummaryView)
