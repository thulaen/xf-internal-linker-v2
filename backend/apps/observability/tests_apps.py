"""Convention-named SimpleTestCase coverage for apps/observability/apps.py.

``ObservabilityConfig`` is the Django app registration. The three attributes it
declares (``default_auto_field``, ``name``, ``verbose_name``) are pinned with
exact ``assertEqual`` so the diff-scoped mutation gate cannot survive a changed
string literal. The config is read as a class attribute only — no app registry
boot, no database, no network.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability.apps import ObservabilityConfig


class ObservabilityConfigTests(SimpleTestCase):
    def test_default_auto_field_is_big_auto_field(self) -> None:
        # Exact string kills the mutmut wrap of the literal; a substring check
        # would let a reworded path survive.
        self.assertEqual(
            ObservabilityConfig.default_auto_field,
            "django.db.models.BigAutoField",
        )

    def test_app_dotted_name_is_apps_observability(self) -> None:
        self.assertEqual(ObservabilityConfig.name, "apps.observability")

    def test_verbose_name_is_observability(self) -> None:
        self.assertEqual(ObservabilityConfig.verbose_name, "Observability")
