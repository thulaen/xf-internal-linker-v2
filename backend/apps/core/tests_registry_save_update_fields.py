"""
Tests that views_runtime_registry uses update_fields when saving existing
RuntimeModelRegistry rows (RUSTBUG-PERF-008 fix).

Without update_fields, registry.save() writes ALL 18 columns back to Postgres
on every registration request — including status, health_result, and
algorithm_version — even when the caller only changed one field. This causes
unnecessary write amplification and risks overwriting concurrent in-progress
health checks.

AutoIssue: #2161
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class ApplyRegistryUpdatesTests(SimpleTestCase):
    """_apply_registry_updates returns only the names of fields that were set."""

    def test_returns_changed_fields_for_supplied_keys(self):
        from apps.core.views_runtime_registry import _apply_registry_updates  # noqa: PLC0415

        mock_reg = MagicMock()
        changed = _apply_registry_updates(mock_reg, {"model_family": "open", "dimension": 768})
        self.assertIn("model_family", changed)
        self.assertIn("dimension", changed)

    def test_does_not_include_keys_absent_from_data(self):
        from apps.core.views_runtime_registry import _apply_registry_updates  # noqa: PLC0415

        mock_reg = MagicMock()
        changed = _apply_registry_updates(mock_reg, {"dimension": 512})
        self.assertNotIn("model_family", changed)
        self.assertNotIn("role", changed)
        self.assertNotIn("memory_profile", changed)

    def test_includes_memory_profile_when_present(self):
        from apps.core.views_runtime_registry import _apply_registry_updates  # noqa: PLC0415

        mock_reg = MagicMock()
        changed = _apply_registry_updates(mock_reg, {"memory_profile": {"peak_mb": 2048}})
        self.assertIn("memory_profile", changed)

    def test_includes_role_when_present(self):
        from apps.core.views_runtime_registry import _apply_registry_updates  # noqa: PLC0415

        mock_reg = MagicMock()
        changed = _apply_registry_updates(mock_reg, {"role": "active"})
        self.assertIn("role", changed)

    def test_sets_attribute_on_registry_for_each_changed_field(self):
        from apps.core.views_runtime_registry import _apply_registry_updates  # noqa: PLC0415

        mock_reg = MagicMock()
        _apply_registry_updates(mock_reg, {"model_family": "hf", "batch_size": 64})
        self.assertEqual(mock_reg.model_family, "hf")
        self.assertEqual(mock_reg.batch_size, 64)
