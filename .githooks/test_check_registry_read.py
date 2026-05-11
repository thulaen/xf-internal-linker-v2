"""Tests for `check-registry-read.py` (the auto-fix-18-issues guard).

Runnable on the host (no Django, no Docker). Exercise via:

    python -m unittest .githooks.test_check_registry_read
    # OR from the repo root:
    python .githooks/test_check_registry_read.py

The hook validates the 6-source marker + 18-pick segment + drought
substitution clause introduced 2026-05-11 per plan
``~/.claude/plans/objective-deploy-and-integrate-zany-bee.md`` Stream 8.
The earlier 12-pick rule (2026-05-10) is now rejected with a helpful
pointer at the new format; the pre-2026-05-10 3-pick rule has been
rejected since the loki rollout.
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


def _ids(prefix: str, count: int) -> str:
    """Render `#prefix1, #prefix2, ...` for `count` IDs."""
    return ", ".join(f"#{prefix}{i}" for i in range(1, count + 1))


def _valid_six_source_marker(
    a=3, g=3, p=3, t=3, l=3, f=3, picks_a=3, picks_g=3, picks_p=3,
    picks_t=3, picks_l=3, picks_f=3, extra_phrase="",
) -> str:
    n = a + g + p + t + l + f
    picks = (
        f"picked: {_ids('a', picks_a)} | g: {_ids('g', picks_g)} "
        f"| p: {_ids('p', picks_p)} | t: {_ids('t', picks_t)} "
        f"| l: {_ids('l', picks_l)} | f: {_ids('f', picks_f)}"
    )
    return (
        f"[REGISTRY READ: {n} open ({a} agent / {g} glitchtip / "
        f"{p} pyroscope / {t} tempo / {l} loki / {f} faro), "
        f"6 registry — {picks}]{extra_phrase}"
    )


class CheckRegistryReadHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    # --- Marker validation -------------------------------------------

    def test_pre_2026_05_10_legacy_marker_rejected(self):
        added = (
            "[REGISTRY READ: 4 open auto-issues, 0 registry — "
            "picked: #1, #2, #3]"
        )
        self.assertEqual(self.hook._validate_marker(added), 1)

    def test_four_source_12_pick_marker_rejected(self):
        # The 2026-05-10 format — rejected after 2026-05-11 with a
        # helpful pointer at the new 6-source form.
        added = (
            "[REGISTRY READ: 12 open (3 agent / 4 glitchtip / "
            "3 pyroscope / 2 loki), 4 registry — picked: #1, #2, #3, #4 "
            "| gp: #5, #6, #7, #8 | l: #9, #10, #11, #12]"
        )
        self.assertEqual(self.hook._validate_marker(added), 1)

    def test_six_source_marker_with_correct_sum_accepted(self):
        added = _valid_six_source_marker(a=3, g=4, p=3, t=2, l=3, f=3)
        # Sum = 18, header says 18. ok.
        self.assertEqual(self.hook._validate_marker(added), 0)

    def test_six_source_marker_mismatched_sum_rejected(self):
        # Forge sum/header mismatch: numbers sum to 17, header claims 18.
        added = (
            "[REGISTRY READ: 18 open (3 agent / 4 glitchtip / "
            "3 pyroscope / 2 tempo / 3 loki / 2 faro), 6 registry — "
            "picked: #1]"
        )
        # 3+4+3+2+3+2 = 17, header says 18 — fail.
        self.assertEqual(self.hook._validate_marker(added), 1)

    def test_no_marker_rejected(self):
        added = "Some random commit body without a marker."
        self.assertEqual(self.hook._validate_marker(added), 1)

    # --- Pick validation ---------------------------------------------

    def test_auto_fix_18_satisfier_accepted(self):
        added = _valid_six_source_marker(extra_phrase=" auto-fix-18 satisfier")
        self.assertEqual(self.hook._validate_picks(added), 0)

    def test_auto_fix_12_satisfier_still_accepted(self):
        added = (
            "[REGISTRY READ: 0 open ...] auto-fix-12 satisfier — "
            "legacy backwards-compat phrase still works."
        )
        self.assertEqual(self.hook._validate_picks(added), 0)

    def test_auto_fix_3_satisfier_still_accepted(self):
        added = "auto-fix-3 satisfier — session task is itself a 3-bug fix."
        self.assertEqual(self.hook._validate_picks(added), 0)

    def test_eighteen_picks_accepted(self):
        added = _valid_six_source_marker()
        self.assertEqual(self.hook._validate_picks(added), 0)

    def test_seventeen_picks_rejected(self):
        # Drop one pick from the faro bucket — 17 total.
        added = _valid_six_source_marker(picks_f=2)
        self.assertEqual(self.hook._validate_picks(added), 1)

    def test_drought_in_tempo_bucket_with_phrase_accepted(self):
        # Tempo source is dry; the substitution form fills the bucket
        # from agent and logs the drought.
        added = (
            "[REGISTRY READ: 15 open (3 agent / 3 glitchtip / 3 pyroscope / "
            "0 tempo / 3 loki / 3 faro), 6 registry — "
            "picked: #a1, #a2, #a3 | g: #g1, #g2, #g3 "
            "| p: #p1, #p2, #p3 "
            "| t: 0 found + 3 from agent: #t1, #t2, #t3 (drought logged: #99) "
            "| l: #l1, #l2, #l3 | f: #f1, #f2, #f3]"
        )
        self.assertEqual(self.hook._validate_picks(added), 0)

    def test_drought_substitution_without_phrase_rejected(self):
        added = (
            "[REGISTRY READ: 15 open (3 agent / 3 glitchtip / 3 pyroscope / "
            "0 tempo / 3 loki / 3 faro), 6 registry — "
            "picked: #a1, #a2, #a3 | g: #g1, #g2, #g3 "
            "| p: #p1, #p2, #p3 "
            "| t: 0 found + 3 from agent: #t1, #t2, #t3 "
            "| l: #l1, #l2, #l3 | f: #f1, #f2, #f3]"
        )
        # Substitution form present, drought phrase missing — fail.
        self.assertEqual(self.hook._validate_picks(added), 1)


if __name__ == "__main__":
    unittest.main()
