"""Convention tests pinning bullboard_client._normalize_severity exact behavior.

These tests tightly assert the SEV_ prefix string, the already-prefixed
passthrough branch, and the upper/strip normalization so mutmut cannot silently
survive on the changed lines (string literal, .startswith branch, both returns).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.ops_feed._sidecars.bullboard_client import _normalize_severity


class NormalizeSeverityConventionTests(SimpleTestCase):
    def test_plain_label_gets_sev_prefix_exactly(self) -> None:
        self.assertEqual(_normalize_severity("error"), "SEV_ERROR")

    def test_already_prefixed_label_passes_through_unchanged(self) -> None:
        self.assertEqual(_normalize_severity("SEV_CRITICAL"), "SEV_CRITICAL")

    def test_lowercase_already_prefixed_is_uppercased_then_passed_through(self) -> None:
        self.assertEqual(_normalize_severity("sev_warning"), "SEV_WARNING")

    def test_surrounding_whitespace_is_stripped_before_prefix(self) -> None:
        self.assertEqual(_normalize_severity("  info  "), "SEV_INFO")
