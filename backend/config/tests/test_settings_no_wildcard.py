"""Regression test that pins SonarQube `python:S2208` compliance via the
documented ``__all__`` exception clause.

The development, production, and test settings modules each use
``from .base import *``. SonarSource's ``python:S2208`` rule documents
an exception: the rule does NOT raise when the imported module declares
``__all__`` (see https://rules.sonarsource.com/python/RSPEC-2208 —
"This rule will not raise an issue if the imported module declares an
``__all__`` attribute, as it is a way to declare a public API.").

This test asserts two invariants:

1. ``config.settings.base`` declares ``__all__`` at module scope, and
   that ``__all__`` contains every Django setting the project depends
   on. If a future refactor drops ``__all__`` from base, this test
   fails before SonarSource's next scan re-opens the S2208 finding.
2. The loaded downstream modules expose the public-Django-settings
   attributes that the project depends on. If a future change breaks
   the re-export chain, this test fails before Django itself does.
"""
from __future__ import annotations

import importlib
from pathlib import Path

from django.test import SimpleTestCase


_SETTINGS_DIR = Path(__file__).resolve().parents[1] / "settings"

_TARGET_FILES = ("development.py", "production.py", "test.py")

# Settings names every downstream module must surface after re-exporting
# from ``base``.  Picked from base.py's public globals + the names each
# downstream file touches directly (LOGGING, DATABASES, env, etc.).
_REQUIRED_EXPORTS = (
    "BASE_DIR",
    "DATABASES",
    "INSTALLED_APPS",
    "LOGGING",
    "MIDDLEWARE",
    "SECRET_KEY",
    "TEMPLATES",
    "env",
)


class BaseSettingsDeclaresAllTests(SimpleTestCase):
    """`config.settings.base` must declare ``__all__`` so the wildcard
    imports in development.py / production.py / test.py are exempt from
    SonarSource ``python:S2208``."""

    def test_base_declares_all(self) -> None:
        from config.settings import base  # noqa: PLC0415

        all_attr = getattr(base, "__all__", None)
        self.assertIsNotNone(
            all_attr,
            msg=(
                "config/settings/base.py is missing its ``__all__`` "
                "declaration. Without it, every `from .base import *` "
                "downstream re-triggers SonarSource python:S2208."
            ),
        )
        self.assertIsInstance(all_attr, list)
        for required in _REQUIRED_EXPORTS:
            self.assertIn(
                required,
                all_attr,
                msg=(
                    f"`__all__` in config/settings/base.py is missing "
                    f"`{required}`. Downstream settings modules rely on "
                    "every key Django setting being exported by name."
                ),
            )


class SettingsStillExposeBaseAttributesTests(SimpleTestCase):
    """After dropping `import *` the downstream modules must still expose
    the Django settings the project consumes."""

    def test_development_exposes_required_attributes(self) -> None:
        self._assert_module_exposes("config.settings.development")

    def test_production_exposes_required_attributes(self) -> None:
        self._assert_module_exposes("config.settings.production")

    def test_test_exposes_required_attributes(self) -> None:
        self._assert_module_exposes("config.settings.test")

    def _assert_module_exposes(self, dotted_name: str) -> None:
        module = importlib.import_module(dotted_name)
        missing = [name for name in _REQUIRED_EXPORTS if not hasattr(module, name)]
        self.assertEqual(
            missing,
            [],
            msg=(
                f"{dotted_name} is missing re-exports: {missing}. "
                "Make sure the module re-exports every public symbol "
                "from `config.settings.base`."
            ),
        )
