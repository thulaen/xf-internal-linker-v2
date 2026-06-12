"""Regression tests for import errors captured in GlitchTip.

These tests prevent recurrence of three high-severity import failures:

  #22844 — ImportError: cannot import name 'AutoIssue' from 'apps.audit.models'
  #23023 — ModuleNotFoundError: No module named 'apps.operations'
  #23024 — ModuleNotFoundError: No module named 'apps.platform.models'

All three errors occurred because code or tests temporarily referenced
non-existent import locations. This file pins the correct import paths
as executable contracts so any future regression is caught immediately.
"""

from __future__ import annotations

import importlib

from django.test import SimpleTestCase


class AutoIssueImportLocationTests(SimpleTestCase):
    """GlitchTip #22844: AutoIssue must come from apps.auto_issues.models."""

    def test_autoissue_importable_from_auto_issues_models(self):
        module = importlib.import_module("apps.auto_issues.models")
        self.assertTrue(
            hasattr(module, "AutoIssue"),
            "AutoIssue must be defined in apps.auto_issues.models",
        )

    def test_autoissue_not_in_audit_models(self):
        module = importlib.import_module("apps.audit.models")
        self.assertFalse(
            hasattr(module, "AutoIssue"),
            "AutoIssue must NOT exist in apps.audit.models; "
            "it lives in apps.auto_issues.models",
        )

    def test_audit_models_contains_expected_symbols(self):
        module = importlib.import_module("apps.audit.models")
        for name in ("ErrorLog", "AuditEntry", "AuditEvent", "FeatureFlag"):
            self.assertTrue(
                hasattr(module, name),
                f"apps.audit.models is missing expected model {name!r}",
            )


class PlatformModelsImportTests(SimpleTestCase):
    """GlitchTip #23024: apps.platform.models must be importable."""

    def test_platform_package_importable(self):
        module = importlib.import_module("apps.platform")
        self.assertIsNotNone(module)

    def test_platform_models_importable(self):
        # Was failing with: ModuleNotFoundError: No module named 'apps.platform.models'
        module = importlib.import_module("apps.platform.models")
        self.assertIsNotNone(module)

    def test_platform_services_importable(self):
        module = importlib.import_module("apps.platform.services.docs_search")
        self.assertTrue(hasattr(module, "federated_search"))

    def test_platform_views_importable(self):
        module = importlib.import_module("apps.platform.views.search_views")
        self.assertTrue(hasattr(module, "FederatedSearchView"))


class OperationsModuleAbsenceTests(SimpleTestCase):
    """GlitchTip #23023: apps.operations does not exist (planned for slice 9).

    Nothing in the current codebase should import from apps.operations.
    This test documents that the module is intentionally absent until
    slice 9 creates it (paper-trail #571 tracks the work).
    """

    def test_operations_module_does_not_exist(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("apps.operations")
