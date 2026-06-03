"""DB-free tests for the 'Why is it slow?' bottleneck classifier.

``analyze_slowness`` samples live CPU / disk / Postgres state and turns
the readings into one verdict. We mock ``_sample_all_signals`` so the
test injects exact readings and asserts the exact verdict, why-string,
and confidence — no psutil, no disk, no database.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.diagnostics.services import slowness_analyzer as sa


def _analyze_with(signals: dict) -> sa.SlownessVerdict:
    with patch.object(sa, "_sample_all_signals", return_value=signals):
        return sa.analyze_slowness(task_name="t")


class SingleSignalVerdictTests(SimpleTestCase):
    def test_when_no_signal_then_unknown_confidence_0_3(self) -> None:
        verdict = _analyze_with({})
        self.assertEqual(verdict.verdict, "unknown")
        self.assertEqual(verdict.confidence, 0.3)

    def test_when_thermal_over_threshold_then_thermal_throttled(self) -> None:
        verdict = _analyze_with({"thermal_c": 90.0})
        self.assertEqual(verdict.verdict, "thermal_throttled")
        self.assertEqual(verdict.confidence, 0.9)

    def test_when_thermal_then_why_string_is_exact_host_wording(self) -> None:
        # Pins the changed why-string literal (was "GPU temperature",
        # now "Host temperature"). Exact match kills the string mutant on
        # the diff-scoped line.
        verdict = _analyze_with({"thermal_c": 90.0})
        self.assertEqual(
            verdict.why,
            "Host temperature is 90°C — clocks may be throttled.",
        )

    def test_when_locks_at_threshold_then_lock_waiting(self) -> None:
        verdict = _analyze_with({"lock_wait_rows": 5})
        self.assertEqual(verdict.verdict, "lock_waiting")
        self.assertEqual(verdict.confidence, 0.85)

    def test_when_disk_wait_high_then_disk_bound_0_75(self) -> None:
        verdict = _analyze_with({"disk_wait_pct": 30.0})
        self.assertEqual(verdict.verdict, "disk_bound")
        self.assertEqual(verdict.confidence, 0.75)

    def test_when_cpu_saturated_then_cpu_bound_0_7(self) -> None:
        verdict = _analyze_with({"cpu_pct": 90.0})
        self.assertEqual(verdict.verdict, "cpu_bound")
        self.assertEqual(verdict.confidence, 0.7)

    def test_when_low_free_ram_then_cpu_bound_0_6(self) -> None:
        verdict = _analyze_with({"mem_free_fraction": 0.05})
        self.assertEqual(verdict.verdict, "cpu_bound")
        self.assertEqual(verdict.confidence, 0.6)


class ThresholdBoundaryTests(SimpleTestCase):
    def test_when_thermal_just_below_threshold_then_unknown(self) -> None:
        verdict = _analyze_with({"thermal_c": 84.9})
        self.assertEqual(verdict.verdict, "unknown")

    def test_when_locks_just_below_threshold_then_unknown(self) -> None:
        verdict = _analyze_with({"lock_wait_rows": 4})
        self.assertEqual(verdict.verdict, "unknown")

    def test_when_disk_wait_just_below_threshold_then_unknown(self) -> None:
        verdict = _analyze_with({"disk_wait_pct": 24.9})
        self.assertEqual(verdict.verdict, "unknown")


class MultiSignalAgreementTests(SimpleTestCase):
    def test_when_two_signals_then_highest_wins_with_boost(self) -> None:
        # thermal (0.9) + cpu (0.7): thermal wins, +0.1 boost -> 1.0.
        verdict = _analyze_with({"thermal_c": 90.0, "cpu_pct": 90.0})
        self.assertEqual(verdict.verdict, "thermal_throttled")
        self.assertEqual(verdict.confidence, 1.0)

    def test_when_three_signals_then_boost_capped_at_1_0(self) -> None:
        verdict = _analyze_with(
            {"thermal_c": 90.0, "lock_wait_rows": 9, "cpu_pct": 99.0}
        )
        self.assertEqual(verdict.verdict, "thermal_throttled")
        self.assertEqual(verdict.confidence, 1.0)

    def test_when_disk_wait_and_disk_free_then_higher_disk_signal_wins(self) -> None:
        # disk_wait (0.75) beats disk_free (0.70); +0.1 boost -> 0.85.
        verdict = _analyze_with({"disk_wait_pct": 30.0, "disk_free_fraction": 0.05})
        self.assertEqual(verdict.verdict, "disk_bound")
        self.assertEqual(verdict.confidence, 0.85)


class VerdictShapeTests(SimpleTestCase):
    def test_when_verdict_returned_then_sampled_at_is_populated(self) -> None:
        verdict = _analyze_with({"cpu_pct": 90.0})
        self.assertTrue(verdict.sampled_at)
        self.assertIn("cpu_bound", verdict.verdict)

    def test_when_why_string_then_includes_reading(self) -> None:
        verdict = _analyze_with({"cpu_pct": 90.0})
        self.assertEqual(
            verdict.why, "CPU is at 90% — the system is compute-saturated."
        )
