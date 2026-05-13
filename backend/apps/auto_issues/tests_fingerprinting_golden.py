"""Golden-fixture regression test for `canonical_fingerprint`.

Scaffolding example for FR-251 Level A — every Level A area should ship
at least one `tests_<area>_golden.py` reader alongside the property tests.
This file is the copyable template.

The fixture lives at `tests_data/golden/canonical_fp_examples.json` and
contains (input, expected_output) pairs. Any change to the output requires
explicit human review (update the snapshot deliberately, do not auto-fix).
"""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase

from apps.auto_issues.services.fingerprinting import _normalise, canonical_fingerprint

_GOLDEN_PATH = (
    Path(__file__).parent / "tests_data" / "golden" / "canonical_fp_examples.json"
)


class CanonicalFingerprintGolden(SimpleTestCase):
    """Replay every fixture case and assert the function output is stable."""

    def test_all_golden_cases_produce_expected_fingerprint(self) -> None:
        with _GOLDEN_PATH.open("r", encoding="utf-8") as f:
            fixture = json.load(f)

        cases = fixture.get("cases", [])
        self.assertGreater(len(cases), 0, "golden fixture must contain at least one case")

        for case in cases:
            expected = case["expected_fingerprint"]
            if expected == "PLACEHOLDER":
                # Allow committing the fixture with PLACEHOLDER values that
                # the operator fills in once the real fingerprint is captured
                # on a known-good checkout. Skip the assert for those rows.
                continue
            with self.subTest(case=case["name"]):
                actual = canonical_fingerprint(case["title"], case["culprit"])
                self.assertEqual(
                    actual,
                    expected,
                    msg=(
                        f"Golden mismatch for case '{case['name']}'. "
                        f"If this change is intentional, update the fixture "
                        f"at {_GOLDEN_PATH} after reviewing the diff visually."
                    ),
                )

    def test_variable_values_are_normalised_to_lowercase_placeholders(self) -> None:
        self.assertEqual(
            _normalise(
                "Crash at 0xDEADBEEF for "
                "550e8400-e29b-41d4-a716-446655440000 in /tmp/app.py:1234"
            ),
            "crash at <hex> for <uuid> in <path>",
        )

    def test_default_culprit_matches_empty_culprit(self) -> None:
        self.assertEqual(
            canonical_fingerprint("Connection failed"),
            canonical_fingerprint("Connection failed", ""),
        )
