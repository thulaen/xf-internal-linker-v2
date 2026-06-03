"""Tests for performance_mode.py bug fix.

Fix 8: get_requested_performance_mode() had a bare `except Exception:`
that swallowed ImportError and AttributeError — development bugs that
should surface loudly. The fix narrows the clause to
`except (OperationalError, ProgrammingError):` so real DB-unavailable
errors are handled but code bugs are not silenced.
"""

from __future__ import annotations

from unittest.mock import patch

from django.db import OperationalError, ProgrammingError
from django.test import SimpleTestCase

from apps.core.performance_mode import (
    PERFORMANCE_MODE_BALANCED,
    PERFORMANCE_MODE_HIGH,
    PERFORMANCE_MODE_SAFE,
    get_requested_performance_mode,
    is_high_performance_mode,
    normalize_performance_mode,
)


class NormalizePerformanceModeTests(SimpleTestCase):
    def test_none_returns_balanced(self):
        self.assertEqual(normalize_performance_mode(None), PERFORMANCE_MODE_BALANCED)

    def test_canonical_names_pass_through(self):
        self.assertEqual(normalize_performance_mode("safe"), PERFORMANCE_MODE_SAFE)
        self.assertEqual(normalize_performance_mode("balanced"), PERFORMANCE_MODE_BALANCED)
        self.assertEqual(normalize_performance_mode("high"), PERFORMANCE_MODE_HIGH)

    def test_aliases_resolve(self):
        self.assertEqual(normalize_performance_mode("standard"), PERFORMANCE_MODE_BALANCED)
        self.assertEqual(normalize_performance_mode("high_performance"), PERFORMANCE_MODE_HIGH)

    def test_case_insensitive(self):
        self.assertEqual(normalize_performance_mode("HIGH"), PERFORMANCE_MODE_HIGH)
        self.assertEqual(normalize_performance_mode("BALANCED"), PERFORMANCE_MODE_BALANCED)

    def test_unknown_returns_balanced_with_warning(self):
        result = normalize_performance_mode("turbo", warn=False)
        self.assertEqual(result, PERFORMANCE_MODE_BALANCED)

    def test_empty_string_returns_balanced(self):
        self.assertEqual(normalize_performance_mode(""), PERFORMANCE_MODE_BALANCED)


class GetRequestedPerformanceModeTests(SimpleTestCase):
    """get_requested_performance_mode must handle DB errors gracefully without swallowing bugs."""

    def test_handles_operational_error_gracefully(self):
        """AutoIssue Fix 8: OperationalError must be caught; function returns a valid mode."""
        with patch("apps.core.models.AppSetting") as mock_cls:
            mock_cls.objects.filter.return_value.values_list.return_value.first.side_effect = (
                OperationalError("DB unavailable")
            )
            result = get_requested_performance_mode()
        self.assertIn(result, [PERFORMANCE_MODE_SAFE, PERFORMANCE_MODE_BALANCED, PERFORMANCE_MODE_HIGH])

    def test_handles_programming_error_gracefully(self):
        """AutoIssue Fix 8: ProgrammingError (e.g. table missing during migration) must be caught."""
        with patch("apps.core.models.AppSetting") as mock_cls:
            mock_cls.objects.filter.return_value.values_list.return_value.first.side_effect = (
                ProgrammingError("relation does not exist")
            )
            result = get_requested_performance_mode()
        self.assertIn(result, [PERFORMANCE_MODE_SAFE, PERFORMANCE_MODE_BALANCED, PERFORMANCE_MODE_HIGH])

    def test_does_not_catch_attribute_error(self):
        """AutoIssue Fix 8: AttributeError is a code bug — must NOT be swallowed."""
        with patch("apps.core.models.AppSetting") as mock_cls:
            mock_cls.objects.filter.return_value.values_list.return_value.first.side_effect = (
                AttributeError("unexpected attr bug")
            )
            with self.assertRaises(AttributeError):
                get_requested_performance_mode()

    def test_does_not_catch_import_error(self):
        """AutoIssue Fix 8: ImportError from a broken import — must NOT be swallowed."""
        import sys

        original = sys.modules.get("apps.core.models")
        try:
            sys.modules["apps.core.models"] = None  # type: ignore[assignment]
            with self.assertRaises((ImportError, AttributeError)):
                get_requested_performance_mode()
        finally:
            if original is not None:
                sys.modules["apps.core.models"] = original
            elif "apps.core.models" in sys.modules:
                del sys.modules["apps.core.models"]

    def test_returns_db_value_when_available(self):
        with patch("apps.core.models.AppSetting") as mock_cls:
            mock_cls.objects.filter.return_value.values_list.return_value.first.return_value = "high"
            result = get_requested_performance_mode()
        self.assertEqual(result, PERFORMANCE_MODE_HIGH)


class IsHighPerformanceModeTests(SimpleTestCase):
    def test_returns_true_when_high(self):
        with patch(
            "apps.core.performance_mode.get_requested_performance_mode",
            return_value=PERFORMANCE_MODE_HIGH,
        ):
            self.assertTrue(is_high_performance_mode())

    def test_returns_false_when_balanced(self):
        with patch(
            "apps.core.performance_mode.get_requested_performance_mode",
            return_value=PERFORMANCE_MODE_BALANCED,
        ):
            self.assertFalse(is_high_performance_mode())
