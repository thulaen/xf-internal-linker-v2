"""Convention-named SimpleTestCase coverage for apps/observability/urls.py.

The app exposes exactly one route, ``stack/``, namespaced under
``observability`` and bound to ``ObservabilityStackView``. These tests inspect
the URL patterns and the namespace directly (no request, no database, no
network). Exact ``assertEqual`` on the route string, the namespace, the name,
and the bound view class pins every literal so the diff-scoped mutation gate
cannot survive a changed constant or a swapped view.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability import urls
from apps.observability.views import ObservabilityStackView


class ObservabilityUrlConfTests(SimpleTestCase):
    def test_app_name_is_observability(self) -> None:
        self.assertEqual(urls.app_name, "observability")

    def test_exactly_one_route_is_declared(self) -> None:
        # Exact count kills the +1 mutation that would survive a >= check.
        self.assertEqual(len(urls.urlpatterns), 1)

    def test_stack_route_pattern_name_and_view(self) -> None:
        entry = urls.urlpatterns[0]
        self.assertEqual(str(entry.pattern), "stack/")
        self.assertEqual(entry.name, "stack")
        bound_view = entry.callback
        self.assertIs(bound_view.view_class, ObservabilityStackView)
