from __future__ import annotations

from django.test import SimpleTestCase

from apps.auto_issues.services.megalinter_mapper import (
    UNKNOWN_CATEGORY,
    UNKNOWN_ENABLED,
    UNKNOWN_SEVERITY,
    lookup,
)


class MegalinterMapperLookupTests(SimpleTestCase):
    def test_gitleaks_returns_security_critical_enabled(self):
        category, severity, enabled = lookup("REPOSITORY_GITLEAKS")
        self.assertEqual(category, "security")
        self.assertEqual(severity, "critical")
        self.assertTrue(enabled)

    def test_secretlint_returns_security_critical_enabled(self):
        category, severity, enabled = lookup("REPOSITORY_SECRETLINT")
        self.assertEqual(category, "security")
        self.assertEqual(severity, "critical")
        self.assertTrue(enabled)

    def test_shellcheck_returns_correctness_medium_enabled(self):
        category, severity, enabled = lookup("SHELL_SHELLCHECK")
        self.assertEqual(category, "correctness")
        self.assertEqual(severity, "medium")
        self.assertTrue(enabled)

    def test_hadolint_returns_correctness_medium_enabled(self):
        category, severity, enabled = lookup("DOCKERFILE_HADOLINT")
        self.assertEqual(category, "correctness")
        self.assertEqual(severity, "medium")
        self.assertTrue(enabled)

    def test_shfmt_is_disabled(self):
        _, _, enabled = lookup("SHELL_SHFMT")
        self.assertFalse(enabled)

    def test_python_ruff_is_disabled(self):
        _, _, enabled = lookup("PYTHON_RUFF")
        self.assertFalse(enabled)

    def test_repository_jscpd_is_disabled(self):
        _, _, enabled = lookup("REPOSITORY_JSCPD")
        self.assertFalse(enabled)

    def test_unknown_linter_returns_defaults(self):
        category, severity, enabled = lookup("UNKNOWN_LINTER_XYZ_999")
        self.assertEqual(category, UNKNOWN_CATEGORY)
        self.assertEqual(severity, UNKNOWN_SEVERITY)
        self.assertEqual(enabled, UNKNOWN_ENABLED)

    def test_unknown_linter_is_enabled_by_default(self):
        _, _, enabled = lookup("BRAND_NEW_LINTER")
        self.assertTrue(enabled)

    def test_lookup_return_type_is_three_tuple(self):
        result = lookup("REPOSITORY_GITLEAKS")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)
        category, severity, enabled = result
        self.assertIsInstance(category, str)
        self.assertIsInstance(severity, str)
        self.assertIsInstance(enabled, bool)
