"""Tests for settings modules changed in this staged set.

These tests are intentionally lightweight: they only confirm that each
settings module imports successfully and exposes the expected marker
variables for its mode.
"""

from __future__ import annotations

import importlib


def _load_module(path: str):
    return importlib.import_module(path)


def test_development_settings_are_importable():
    module = _load_module("config.settings.development")
    assert getattr(module, "DEBUG", None) is not None
    assert "localhost" in module.ALLOWED_HOSTS


def test_production_settings_are_importable():
    module = _load_module("config.settings.production")
    assert module.DEBUG is False
    assert "whitenoise.middleware.WhiteNoiseMiddleware" in module.MIDDLEWARE


def test_test_settings_are_importable():
    module = _load_module("config.settings.test")
    assert module.TESTING is True
    assert module.DATABASES["default"]["ENGINE"]
