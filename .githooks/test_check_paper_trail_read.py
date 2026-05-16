#!/usr/bin/env python3
"""Tests for check-paper-trail-read.py.

Run from repo root: `python .githooks/test_check_paper_trail_read.py`.

Quota lowered from 10 to 3 on 2026-05-16 and broadened to every commit.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


def _load_hook():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "check_paper_trail_read",
        here / "check-paper-trail-read.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_QUOTA = 3


def _full_marker(n: int = _QUOTA, picks: str | None = None) -> str:
    if picks is None:
        picks = ", ".join(f"#{i}" for i in range(1, _QUOTA + 1))
    breakdown_counts = [
        ("autoissue_deferral", n // 16 + (1 if n % 16 > 0 else 0)),
        ("cve_upgrade", n // 16),
        ("coverage_gap", n // 16),
        ("infrastructure", n // 16),
        ("ruff_sweep", n // 16),
        ("mutation_survivor", n // 16),
        ("debt_reduction", n // 16),
        ("feature_decision", n // 16),
        ("tooling_gap", n // 16),
        ("documentation", n // 16),
        ("dependency_upgrade", n // 16),
        ("refactor", n // 16),
        ("performance", n // 16),
        ("security", n // 16),
        ("accessibility", n // 16),
        ("other", n // 16),
    ]
    actual_sum = sum(c for _, c in breakdown_counts)
    # Pad "other" to make the bucket sum == declared N
    breakdown_counts[-1] = ("other", breakdown_counts[-1][1] + (n - actual_sum))
    breakdown_str = " / ".join(f"{c} {cat}" for cat, c in breakdown_counts)
    return f"[PAPER TRAIL READ: {n} open ({breakdown_str}) — picked: {picks}]"


class MarkerValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def test_valid_marker_with_three_picks_accepted(self):
        marker = _full_marker(n=_QUOTA)
        code, ids = self.hook._validate_marker(marker)
        self.assertEqual(code, 0)
        self.assertEqual(len(ids), _QUOTA)

    def test_missing_marker_rejected(self):
        code, ids = self.hook._validate_marker("Some commit body with no marker.")
        self.assertEqual(code, 2)
        self.assertEqual(ids, [])

    def test_wrong_breakdown_sum_rejected(self):
        marker = (
            "[PAPER TRAIL READ: 100 open ("
            "1 autoissue_deferral / 1 cve_upgrade / 1 coverage_gap / "
            "1 infrastructure / 1 ruff_sweep / 1 mutation_survivor / "
            "1 debt_reduction / 1 feature_decision / 1 tooling_gap / "
            "1 documentation / 1 dependency_upgrade / 1 refactor / "
            "1 performance / 1 security / 1 accessibility / 1 other"
            ") — picked: #1, #2, #3]"
        )
        code, _ids = self.hook._validate_marker(marker)
        self.assertEqual(code, 2)

    def test_two_picks_rejected(self):
        """Quota is now 3 — fewer ids than that must FAIL."""
        two = ", ".join(f"#{i}" for i in range(1, 3))
        marker = _full_marker(n=_QUOTA, picks=two)
        code, _ids = self.hook._validate_marker(marker)
        self.assertEqual(code, 2)

    def test_four_picks_rejected(self):
        """The hook expects exactly _QUOTA picks — overshoot is also FAIL."""
        four = ", ".join(f"#{i}" for i in range(1, 5))
        marker = _full_marker(n=_QUOTA + 1, picks=four)
        code, _ids = self.hook._validate_marker(marker)
        self.assertEqual(code, 2)

    def test_drought_form_rejected(self):
        """Drought form was the legacy escape hatch — now banned on every
        commit. Agents must file new defer_work entries until the picker
        returns 3.
        """
        marker = _full_marker(
            n=1,
            picks="#1 (drought; file the remainder per docs/PAPER-TRAIL.md)",
        )
        code, _ids = self.hook._validate_marker(marker)
        self.assertEqual(code, 2)

    def test_satisfier_phrase_rejected_legacy(self):
        marker = _full_marker(n=_QUOTA) + " auto-defer-10 satisfier"
        code, _ids = self.hook._validate_marker(marker)
        self.assertEqual(code, 2)

    def test_satisfier_phrase_rejected_new(self):
        """The lowered-quota equivalent is also banned."""
        marker = _full_marker(n=_QUOTA) + " auto-defer-3 satisfier"
        code, _ids = self.hook._validate_marker(marker)
        self.assertEqual(code, 2)

    def test_missing_category_rejected(self):
        # Drop the 'security' bucket from the breakdown.
        marker = (
            "[PAPER TRAIL READ: 0 open ("
            "0 autoissue_deferral / 0 cve_upgrade / 0 coverage_gap / "
            "0 infrastructure / 0 ruff_sweep / 0 mutation_survivor / "
            "0 debt_reduction / 0 feature_decision / 0 tooling_gap / "
            "0 documentation / 0 dependency_upgrade / 0 refactor / "
            "0 performance / 0 accessibility / 0 other"  # security missing
            ") — picked: #1, #2, #3]"
        )
        code, _ids = self.hook._validate_marker(marker)
        self.assertEqual(code, 2)


class HardBlockQuotaTests(unittest.TestCase):
    """The _verify_quota path MUST return 2 (hard fail) on any escape
    hatch: docker missing, command timeout, command rejects. There is
    no return code 1 ("skipped").
    """

    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def test_docker_unavailable_is_hard_fail(self):
        """If subprocess.run raises FileNotFoundError, the gate must
        FAIL (return 2), not skip (return 1).
        """
        import subprocess as sp
        original = sp.run

        def fake_run(*args, **kwargs):
            raise FileNotFoundError("docker not on PATH")

        sp.run = fake_run
        try:
            result = self.hook._verify_quota(ids=list(range(1, _QUOTA + 1)))
        finally:
            sp.run = original
        self.assertEqual(result, 2)

    def test_command_timeout_is_hard_fail(self):
        """If the verify_paper_trail_quota subprocess times out, the
        gate must FAIL (return 2), not skip.
        """
        import subprocess as sp
        original = sp.run

        def fake_run(*args, **kwargs):
            raise sp.TimeoutExpired(cmd="dummy", timeout=60)

        sp.run = fake_run
        try:
            result = self.hook._verify_quota(ids=list(range(1, _QUOTA + 1)))
        finally:
            sp.run = original
        self.assertEqual(result, 2)

    def test_command_rejects_is_hard_fail(self):
        """If verify_paper_trail_quota returns non-zero, the gate fails."""
        import subprocess as sp
        original = sp.run

        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = "Not resolved: #1"

        def fake_run(*args, **kwargs):
            return FakeResult()

        sp.run = fake_run
        try:
            result = self.hook._verify_quota(ids=list(range(1, _QUOTA + 1)))
        finally:
            sp.run = original
        self.assertEqual(result, 2)

    def test_command_passes_emits_marker(self):
        """When verify_paper_trail_quota returns 0, the gate writes the
        VERIFIED marker to stdout and returns 0.
        """
        import io
        import subprocess as sp
        import sys

        original_run = sp.run
        original_stdout = sys.stdout

        class FakeResult:
            returncode = 0
            stdout = ""
            stderr = ""

        captured = io.StringIO()
        sp.run = lambda *a, **kw: FakeResult()
        sys.stdout = captured
        try:
            result = self.hook._verify_quota(ids=list(range(1, _QUOTA + 1)))
        finally:
            sp.run = original_run
            sys.stdout = original_stdout
        self.assertEqual(result, 0)
        self.assertIn(f"QUOTA VERIFIED: {_QUOTA} resolved", captured.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
