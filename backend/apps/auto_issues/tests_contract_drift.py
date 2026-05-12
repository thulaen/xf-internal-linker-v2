"""Tests for the contract_drift picker — Phase 6 of the test-hardening plan."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.auto_issues.services import contract_drift


class ContractDriftPickerTests(SimpleTestCase):
    def test_missing_results_file_returns_zero(self) -> None:
        # The pact-provider-results.json file doesn't exist on a fresh
        # checkout — the future Pact CI job will create it. Picker must
        # handle that gracefully.
        self.assertEqual(contract_drift.pick_contract_drift(), 0)
