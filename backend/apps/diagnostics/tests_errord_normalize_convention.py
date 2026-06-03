"""Convention tests pinning errord_client._normalize_action exact behavior.

These tests tightly assert the string prefix, the already-prefixed passthrough
branch, and the upper/strip normalization so mutmut cannot silently survive on
the changed lines (string literal, .startswith branch, both return paths).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.diagnostics._sidecars.errord_client import _normalize_action


class NormalizeActionConventionTests(SimpleTestCase):
    def test_plain_label_gets_act_prefix_exactly(self) -> None:
        self.assertEqual(_normalize_action("retry"), "ACT_RETRY")

    def test_already_prefixed_label_passes_through_unchanged(self) -> None:
        self.assertEqual(_normalize_action("ACT_ALERT"), "ACT_ALERT")

    def test_lowercase_already_prefixed_is_uppercased_then_passed_through(self) -> None:
        self.assertEqual(_normalize_action("act_swallow"), "ACT_SWALLOW")

    def test_surrounding_whitespace_is_stripped_before_prefix(self) -> None:
        self.assertEqual(_normalize_action("  alert  "), "ACT_ALERT")
