"""Tests for machine-readable ML settings API documentation."""

from __future__ import annotations

import importlib

from django.test import SimpleTestCase


class FeedbackRerankSettingsSchemaTests(SimpleTestCase):
    def _module(self):
        return importlib.import_module("apps.core.views_ml_settings")

    def test_view_module_imports_without_circular_dependency(self) -> None:
        module = self._module()

        self.assertTrue(hasattr(module, "FeedbackRerankSettingsView"))

    def test_view_declares_serializer_class_for_schema_generation(self) -> None:
        module = self._module()
        serializer_class = module.FeedbackRerankSettingsView.serializer_class

        self.assertEqual(serializer_class.__name__, "FeedbackRerankSettingsSerializer")

    def test_serializer_matches_feedback_settings_payload(self) -> None:
        module = self._module()
        serializer = module.FeedbackRerankSettingsView.serializer_class()

        self.assertEqual(
            set(serializer.fields),
            {"enabled", "ranking_weight", "exploration_rate"},
        )
