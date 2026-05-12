"""Tests for the mutation picker — Phase 6 of the test-hardening plan."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.auto_issues.services import mutation


class MutationPickerTests(SimpleTestCase):
    def test_missing_report_files_return_zero(self) -> None:
        # All three tool readers should return 0 cleanly when their JSON
        # report files are absent (the default state on a fresh checkout).
        self.assertEqual(mutation._pick_mutmut(), 0)
        self.assertEqual(mutation._pick_stryker(), 0)
        self.assertEqual(mutation._pick_mull(), 0)

    def test_aggregate_returns_zero_when_all_absent(self) -> None:
        self.assertEqual(mutation.pick_mutation_survivors(), 0)
