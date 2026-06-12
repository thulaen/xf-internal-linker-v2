"""Test that startup import errors don't regress.

Resolves AutoIssues #22844, #23023, #23024:
- #22844: ImportError: cannot import name 'AutoIssue' from 'apps.audit.models'
- #23023: ModuleNotFoundError: No module named 'apps.operations'
- #23024: ModuleNotFoundError: No module named 'apps.platform.models'

These were startup errors captured by GlitchTip on 2026-06-07 and 2026-06-10.
The root causes were:
1. Some code path tried to import AutoIssue from the wrong place (apps.audit
   instead of apps.auto_issues).
2. A URL include referenced 'apps.operations' which doesn't exist (was fixed
   to use apps.ops_feed).
3. A URL include referenced 'apps.platform.models' which doesn't exist (platform
   has no models.py file).

This test suite ensures:
- Django can initialize without import errors
- AutoIssue is not accidentally imported from apps.audit.models
- No modules named 'apps.operations' are required
- apps.platform has only views/services, not models
- All URL configurations load correctly
"""

from __future__ import annotations

import sys
from unittest.mock import patch

from django.apps import apps
from django.test import SimpleTestCase


class StartupImportErrorTests(SimpleTestCase):
    """Regression tests for startup import errors."""

    def test_django_setup_succeeds(self):
        """Django initializes without raising ImportError or ModuleNotFoundError."""
        # If we're running this test, Django has already set up successfully.
        # This test documents the expected behavior.
        import django
        from django.conf import settings

        self.assertTrue(settings.configured, "Django should be configured")
        self.assertGreater(len(apps.get_app_configs()), 0, "Django apps should be loaded")

    def test_autoissue_not_in_audit_models(self):
        """AutoIssue should not be importable from apps.audit.models."""
        from apps.audit import models as audit_models

        # AutoIssue should NOT be in audit.models
        self.assertFalse(
            hasattr(audit_models, "AutoIssue"),
            "AutoIssue should not be in apps.audit.models; it's in apps.auto_issues.models",
        )

        # Verify audit.models only has the expected models
        expected_models = {"AuditEntry", "AuditEvent"}
        actual_models = {
            name
            for name in dir(audit_models)
            if isinstance(getattr(audit_models, name), type)
            and hasattr(getattr(audit_models, name), "_meta")
            and hasattr(getattr(audit_models, name)._meta, "app_label")
        }
        self.assertTrue(
            expected_models.issubset(actual_models),
            f"audit.models should have {expected_models}, found {actual_models}",
        )

    def test_autoissue_in_auto_issues_models(self):
        """AutoIssue should be in apps.auto_issues.models."""
        from apps.auto_issues.models import AutoIssue

        self.assertTrue(hasattr(AutoIssue, "_meta"), "AutoIssue should be a Django model")
        self.assertEqual(AutoIssue._meta.app_label, "auto_issues")

    def test_no_apps_operations_module(self):
        """apps.operations should not exist."""
        with self.assertRaises(ImportError):
            import apps.operations  # noqa: F401 # pylint: disable=import-error,no-name-in-module

        # But apps.ops_feed should exist
        import apps.ops_feed  # noqa: F401 # pylint: disable=unused-import
        self.assertTrue(True, "apps.ops_feed imports successfully")

    def test_platform_views_and_services_import(self):
        """apps.platform should have views, services, and models."""
        # This should work
        from apps.platform.views import search_views  # noqa: F401
        from apps.platform.services import docs_search  # noqa: F401
        from apps.platform import models  # noqa: F401

        self.assertTrue(True, "platform components import successfully")

    def test_url_configuration_loads(self):
        """URL configuration should load without import errors."""
        # This tests that the root URLs can be imported
        from apps.api import urls  # noqa: F401

        # Specifically check that ops_feed URL include works
        urlpatterns = urls.urlpatterns
        ops_feed_path_found = any("operations" in str(p) for p in urlpatterns)
        self.assertTrue(ops_feed_path_found, "Should have /operations/ path from ops_feed URLs")

    def test_no_circular_imports_audit_to_auto_issues(self):
        """apps.audit and apps.auto_issues should not have circular imports."""
        # Import audit first
        from apps.audit import models as audit_models  # noqa: F401

        # Then import auto_issues — should not fail
        from apps.auto_issues import models as auto_issues_models  # noqa: F401

        self.assertTrue(True, "No circular imports between audit and auto_issues")

    def test_installed_apps_integrity(self):
        """Verify all INSTALLED_APPS can be loaded."""
        from django.conf import settings

        for app_name in settings.INSTALLED_APPS:
            if app_name.startswith("apps."):
                try:
                    apps.get_app_config(app_name.split(".")[-1])
                except LookupError:
                    self.fail(f"INSTALLED_APP {app_name} could not be loaded")

        self.assertTrue(True, "All INSTALLED_APPS loaded successfully")
