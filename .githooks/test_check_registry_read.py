"""Tests for `check-registry-read.py` (the auto-fix-12-issues guard).

Runnable on the host (no Django, no Docker). Exercise via:

    python -m unittest .githooks.test_check_registry_read
    # OR from the repo root:
    python .githooks/test_check_registry_read.py

The hook validates the per-source marker + 12-pick segment + drought
substitution clause introduced 2026-05-10 per plan
``does-adding-qodana-make-swift-wall.md`` Stream 5.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_HOOK_PATH = Path(__file__).resolve().parent / "check-registry-read.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location(
        "check_registry_read_hook", _HOOK_PATH
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CheckRegistryReadHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    # --- Marker validation -------------------------------------------

    def test_legacy_marker_is_rejected(self):
        added = (
            "[REGISTRY READ: 4 open auto-issues, 0 registry — "
            "picked: #1, #2, #3]"
        )
        self.assertEqual(self.hook._validate_marker(added), 1)

    def test_new_marker_with_correct_sum_accepted(self):
        added = (
            "[REGISTRY READ: 12 open (3 agent / 4 glitchtip / "
            "3 pyroscope / 2 loki), 4 registry — picked: #1, #2, #3, #4 "
            "| gp: #5, #6, #7, #8 | l: #9, #10, #11, #12]"
        )
        self.assertEqual(self.hook._validate_marker(added), 0)

    def test_new_marker_mismatched_sum_rejected(self):
        added = (
            "[REGISTRY READ: 12 open (3 agent / 4 glitchtip / "
            "3 pyroscope / 1 loki), 4 registry — picked: ...]"
        )
        # 3+4+3+1 = 11, header says 12 -> fail.
        self.assertEqual(self.hook._validate_marker(added), 1)

    def test_no_marker_rejected(self):
        added = "Some random commit body without a marker."
        self.assertEqual(self.hook._validate_marker(added), 1)

    # --- Pick validation ---------------------------------------------

    def test_satisfier_exemption_accepted(self):
        added = (
            "[REGISTRY READ: 4 open (4 agent / 0 glitchtip / "
            "0 pyroscope / 0 loki), 4 registry] auto-fix-12 satisfier"
        )
        self.assertEqual(self.hook._validate_picks(added), 0)

    def test_legacy_satisfier_phrase_still_accepted(self):
        # Backwards compat: existing 'auto-fix-3 satisfier' phrase.
        added = "auto-fix-3 satisfier — session task is itself a 3-bug fix."
        self.assertEqual(self.hook._validate_picks(added), 0)

    def test_twelve_picks_accepted(self):
        added = (
            "[REGISTRY READ: 12 open (3 agent / 4 glitchtip / "
            "3 pyroscope / 2 loki), 4 registry — picked: #1, #2, #3, #4 "
            "| gp: #5, #6, #7, #8 | l: #9, #10, #11, #12]"
        )
        self.assertEqual(self.hook._validate_picks(added), 0)

    def test_eleven_picks_rejected(self):
        added = (
            "[REGISTRY READ: 11 open (3 agent / 4 glitchtip / "
            "2 pyroscope / 2 loki), 4 registry — picked: #1, #2, #3, #4 "
            "| gp: #5, #6, #7, #8 | l: #9, #10, #11]"
        )
        self.assertEqual(self.hook._validate_picks(added), 1)

    def test_drought_substitution_with_phrase_accepted(self):
        added = (
            "[REGISTRY READ: 8 open (4 agent / 4 glitchtip / "
            "0 pyroscope / 0 loki), 4 registry — picked: #1, #2, #3, #4 "
            "| gp: #5, #6, #7, #8 "
            "| l: 0 found + 4 from agent: #9, #10, #11, #12 "
            "(drought logged: #99)]"
        )
        self.assertEqual(self.hook._validate_picks(added), 0)

    def test_drought_substitution_without_phrase_rejected(self):
        added = (
            "[REGISTRY READ: 8 open (4 agent / 4 glitchtip / "
            "0 pyroscope / 0 loki), 4 registry — picked: #1, #2, #3, #4 "
            "| gp: #5, #6, #7, #8 "
            "| l: 0 found + 4 from agent: #9, #10, #11, #12]"
        )
        self.assertEqual(self.hook._validate_picks(added), 1)


if __name__ == "__main__":
    unittest.main()
