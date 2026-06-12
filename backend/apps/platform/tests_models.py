"""Regression tests for the apps.platform model stub.

GlitchTip #23024 recorded ``ModuleNotFoundError: No module named
'apps.platform.models'``. The module is a deliberate model-less stub;
these tests pin both import forms so the error cannot return.
"""

from __future__ import annotations

import importlib

from django.db.models import Model
from django.test import SimpleTestCase


class PlatformModelsImportTests(SimpleTestCase):
    """GlitchTip #23024: apps.platform.models must stay importable."""

    def test_import_module_path_succeeds(self):
        module = importlib.import_module("apps.platform.models")
        self.assertIsNotNone(module)

    def test_from_package_import_form_succeeds(self):
        from apps.platform import models

        self.assertEqual(models.__name__, "apps.platform.models")

    def test_stub_declares_no_django_models(self):
        module = importlib.import_module("apps.platform.models")
        declared = [
            name
            for name, value in vars(module).items()
            if isinstance(value, type) and issubclass(value, Model)
        ]
        self.assertEqual(
            declared,
            [],
            "apps.platform.models is documented as a model-less stub; "
            "register the app in INSTALLED_APPS before adding real models",
        )
