"""Regression test for the GSC brand colour in the backend appearance default.

Covers the changed lines in apps/core/views.py: DEFAULT_APPEARANCE must carry
the GSC brand blue #4285f4 so the stored default matches the SCSS design token
and the frontend AppearanceService default, keeping all three brand sources in
lockstep (see docs/specs/fr-gsc-brand-and-input-fix.md).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.core.views import DEFAULT_APPEARANCE


class DefaultAppearanceBrandColourTests(SimpleTestCase):
    def test_primary_colour_is_gsc_blue(self) -> None:
        self.assertEqual(DEFAULT_APPEARANCE["primaryColor"], "#4285f4")

    def test_accent_colour_matches_primary(self) -> None:
        self.assertEqual(DEFAULT_APPEARANCE["accentColor"], "#4285f4")
