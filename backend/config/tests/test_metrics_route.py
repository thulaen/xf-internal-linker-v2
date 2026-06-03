"""Pin the ``metrics/`` route added to config/urls.py.

config/urls.py now wires ``path("metrics/", MetricsView.as_view(),
name="metrics")`` so the Prometheus-style metrics endpoint is reachable. This
test resolves the named route through the live URLconf and asserts the exact
path string, killing a mutant that renames the route or changes the prefix
(e.g. ``"metrics/"`` -> ``"XXmetricsXX/"``).
"""

from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import resolve, reverse


class MetricsRouteTests(SimpleTestCase):
    def test_metrics_route_reverses_to_exact_path(self) -> None:
        self.assertEqual(reverse("metrics"), "/metrics/")

    def test_metrics_path_resolves_to_named_route(self) -> None:
        match = resolve("/metrics/")
        self.assertEqual(match.url_name, "metrics")
