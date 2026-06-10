"""Tests for apps.auto_issues.services.scoring.

The docstring in scoring.py references ``tests_scoring.py`` but that file
was never created. This file provides the missing coverage for all seven
public functions plus the ``ScoringWeights`` dataclass.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.scoring import (
    Candidate,
    ScoringWeights,
    auto_close_stale_threshold,
    blast_factor,
    cost_inv_factor,
    recency_factor,
    regression_factor,
    score_candidate,
    severity_factor,
    top_k,
)


# ── ScoringWeights ────────────────────────────────────────────────────────


class ScoringWeightsTests(SimpleTestCase):
    def test_default_weights_sum_to_one(self):
        w = ScoringWeights()
        total = w.severity + w.recency + w.recurrence + w.blast + w.cost_inv
        self.assertAlmostEqual(total, 1.0, places=9)

    def test_weights_not_summing_to_one_raises(self):
        """Bug 2 fix: ScoringWeights must raise ValueError when weights do not sum to 1.0."""
        with self.assertRaises(ValueError):
            ScoringWeights(
                severity=0.9,
                recency=0.9,
                recurrence=0.9,
                blast=0.9,
                cost_inv=0.9,
            )

    def test_weights_slightly_over_tolerance_raises(self):
        """Sharp: sum 1.5e-6 over 1.0 exceeds the 1e-6 tolerance — must raise.

        This kills mutant that widens tolerance to 2e-6: 1.5e-6 > 1e-6 (raises)
        but 1.5e-6 is NOT > 2e-6 (mutant would silently accept it).
        """
        with self.assertRaises(ValueError):
            ScoringWeights(
                severity=0.3500015,
                recency=0.20,
                recurrence=0.20,
                blast=0.15,
                cost_inv=0.10,
            )

    def test_weights_error_message_starts_with_scoring_weights(self):
        """Sharp: checks the exact message prefix to kill the XX...XX string mutant."""
        with self.assertRaisesRegex(ValueError, r"^ScoringWeights must sum to 1\.0"):
            ScoringWeights(
                severity=0.50,
                recency=0.20,
                recurrence=0.20,
                blast=0.15,
                cost_inv=0.10,
            )

    def test_weights_too_low_raises(self):
        with self.assertRaises(ValueError):
            ScoringWeights(
                severity=0.10,
                recency=0.10,
                recurrence=0.10,
                blast=0.10,
                cost_inv=0.10,
            )

    def test_custom_valid_weights_accepted(self):
        w = ScoringWeights(
            severity=0.40,
            recency=0.25,
            recurrence=0.15,
            blast=0.12,
            cost_inv=0.08,
        )
        total = w.severity + w.recency + w.recurrence + w.blast + w.cost_inv
        self.assertAlmostEqual(total, 1.0, places=9)

    def test_float_rounding_within_tolerance_accepted(self):
        # 0.1 + 0.1 + 0.1 = 0.30000000000000004 in IEEE 754 — must be accepted.
        w = ScoringWeights(
            severity=0.35,
            recency=0.20,
            recurrence=0.20,
            blast=0.15,
            cost_inv=0.10,
        )
        self.assertIsNotNone(w)

    def test_default_weights_exact_values(self):
        """Sharp: every default value must be precisely what the spec says.

        This test kills mutants that nudge any single default — the sum check
        alone would not catch a swap between two equal values.
        """
        w = ScoringWeights()
        self.assertEqual(w.severity, 0.35)
        self.assertEqual(w.recency, 0.20)
        self.assertEqual(w.recurrence, 0.20)
        self.assertEqual(w.blast, 0.15)
        self.assertEqual(w.cost_inv, 0.10)

    def test_weights_frozen(self):
        """The dataclass is frozen — writing any field must raise."""
        from dataclasses import FrozenInstanceError

        w = ScoringWeights()
        with self.assertRaises(FrozenInstanceError):
            w.severity = 0.99  # type: ignore[misc]


# ── severity_factor ───────────────────────────────────────────────────────


class SeverityFactorTests(SimpleTestCase):
    def test_glitchtip_critical_returns_one(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_CRITICAL),
            1.0,
        )

    def test_glitchtip_high_returns_point_85(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_HIGH),
            0.85,
        )

    def test_glitchtip_medium_returns_point_60(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_MEDIUM),
            0.60,
        )

    def test_glitchtip_low_returns_point_20(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_LOW),
            0.20,
        )

    def test_pyroscope_high_returns_point_75(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_PYROSCOPE, AutoIssue.SEVERITY_HIGH),
            0.75,
        )

    def test_agent_medium_returns_point_40(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_AGENT, AutoIssue.SEVERITY_MEDIUM),
            0.40,
        )

    def test_unknown_source_returns_zero(self):
        self.assertEqual(severity_factor("banana", AutoIssue.SEVERITY_HIGH), 0.0)

    def test_unknown_severity_in_known_source_returns_zero(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_GLITCHTIP, "ultra-critical"),
            0.0,
        )

    def test_all_glitchtip_severities_are_positive(self):
        for sev in (
            AutoIssue.SEVERITY_CRITICAL,
            AutoIssue.SEVERITY_HIGH,
            AutoIssue.SEVERITY_MEDIUM,
            AutoIssue.SEVERITY_LOW,
        ):
            score = severity_factor(AutoIssue.SOURCE_GLITCHTIP, sev)
            self.assertGreater(score, 0.0, msg=f"{sev} must have a positive score")

    def test_glitchtip_severities_are_strictly_ordered(self):
        critical = severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_CRITICAL)
        high = severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_HIGH)
        medium = severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_MEDIUM)
        low = severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_LOW)
        self.assertGreater(critical, high)
        self.assertGreater(high, medium)
        self.assertGreater(medium, low)

    def test_pyroscope_critical_returns_point_90(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_PYROSCOPE, AutoIssue.SEVERITY_CRITICAL),
            0.90,
        )

    def test_pyroscope_medium_returns_point_50(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_PYROSCOPE, AutoIssue.SEVERITY_MEDIUM),
            0.50,
        )

    def test_pyroscope_low_returns_point_10(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_PYROSCOPE, AutoIssue.SEVERITY_LOW),
            0.10,
        )

    def test_agent_critical_returns_point_80(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_AGENT, AutoIssue.SEVERITY_CRITICAL),
            0.80,
        )

    def test_agent_high_returns_point_60(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_AGENT, AutoIssue.SEVERITY_HIGH),
            0.60,
        )

    def test_agent_low_returns_point_10(self):
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_AGENT, AutoIssue.SEVERITY_LOW),
            0.10,
        )

    def test_glitchtip_all_exact_values(self):
        """Sharp: kills mutants that adjust any individual GlitchTip table entry."""
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_CRITICAL),
            1.00,
        )
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_HIGH),
            0.85,
        )
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_MEDIUM),
            0.60,
        )
        self.assertEqual(
            severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_LOW),
            0.20,
        )

    # ── Missing severity tables for 18/21 sources (Fix #1) ────────────────



    def test_severity_factor_all_missing_sources_have_nonzero_critical(self):
        """All 18 previously-missing sources must return >0 for CRITICAL severity."""
        missing_sources = [
            AutoIssue.SOURCE_TEMPO,
            AutoIssue.SOURCE_TEMPO,
            AutoIssue.SOURCE_LOKI,
            AutoIssue.SOURCE_FARO,
            AutoIssue.SOURCE_VMALERT,
            AutoIssue.SOURCE_RUST_DEFECT,
            AutoIssue.SOURCE_PPROF,
            AutoIssue.SOURCE_ALLOY,
            AutoIssue.SOURCE_PERFETTO,
            AutoIssue.SOURCE_GWP_ASAN,
            AutoIssue.SOURCE_PROMETHEUS,
            AutoIssue.SOURCE_PG_STAT,
            AutoIssue.SOURCE_LIGHTHOUSE,
            AutoIssue.SOURCE_TEST_FAILURE,
            AutoIssue.SOURCE_MUTATION,
            AutoIssue.SOURCE_FUZZ,
            AutoIssue.SOURCE_CONTRACT,
            AutoIssue.SOURCE_GH_CI,
        ]
        for source in missing_sources:
            with self.subTest(source=source):
                score = severity_factor(source, AutoIssue.SEVERITY_CRITICAL)
                self.assertGreater(
                    score, 0.0, msg=f"{source} CRITICAL must be >0"
                )

    def test_default_table_severity_ordering_is_strict(self):
        """Default table values must be strictly ordered: CRITICAL > HIGH > MEDIUM > LOW."""
        source = AutoIssue.SOURCE_TEMPO
        critical = severity_factor(source, AutoIssue.SEVERITY_CRITICAL)
        high = severity_factor(source, AutoIssue.SEVERITY_HIGH)
        medium = severity_factor(source, AutoIssue.SEVERITY_MEDIUM)
        low = severity_factor(source, AutoIssue.SEVERITY_LOW)
        self.assertGreater(critical, high)
        self.assertGreater(high, medium)
        self.assertGreater(medium, low)
        self.assertGreater(low, 0.0)

    def test_default_table_values_do_not_exceed_glitchtip(self):
        """Default table is conservative — its HIGH must be <= GlitchTip HIGH (0.85)."""
        default_high = severity_factor(AutoIssue.SOURCE_TEMPO, AutoIssue.SEVERITY_HIGH)
        glitchtip_high = severity_factor(AutoIssue.SOURCE_GLITCHTIP, AutoIssue.SEVERITY_HIGH)
        self.assertLessEqual(default_high, glitchtip_high)

    def test_default_table_exact_values_via_tempo(self):
        """Exact values for _SEV_TABLE_DEFAULT — kills value-nudge mutants."""
        self.assertAlmostEqual(
            severity_factor(AutoIssue.SOURCE_TEMPO, AutoIssue.SEVERITY_CRITICAL), 0.90
        )
        self.assertAlmostEqual(
            severity_factor(AutoIssue.SOURCE_TEMPO, AutoIssue.SEVERITY_HIGH), 0.75
        )
        self.assertAlmostEqual(
            severity_factor(AutoIssue.SOURCE_TEMPO, AutoIssue.SEVERITY_MEDIUM), 0.50
        )
        self.assertAlmostEqual(
            severity_factor(AutoIssue.SOURCE_TEMPO, AutoIssue.SEVERITY_LOW), 0.15
        )

    def test_all_default_sources_share_identical_values(self):
        """All 18 default-table sources must return the same value for each severity.

        Kills mutants that redirect a source to a different table.
        """
        _DEFAULT_SOURCES = [
            AutoIssue.SOURCE_TEMPO,
            AutoIssue.SOURCE_TEMPO,
            AutoIssue.SOURCE_LOKI,
            AutoIssue.SOURCE_FARO,
            AutoIssue.SOURCE_VMALERT,
            AutoIssue.SOURCE_RUST_DEFECT,
            AutoIssue.SOURCE_PPROF,
            AutoIssue.SOURCE_ALLOY,
            AutoIssue.SOURCE_PERFETTO,
            AutoIssue.SOURCE_GWP_ASAN,
            AutoIssue.SOURCE_PROMETHEUS,
            AutoIssue.SOURCE_PG_STAT,
            AutoIssue.SOURCE_LIGHTHOUSE,
            AutoIssue.SOURCE_TEST_FAILURE,
            AutoIssue.SOURCE_MUTATION,
            AutoIssue.SOURCE_FUZZ,
            AutoIssue.SOURCE_CONTRACT,
            AutoIssue.SOURCE_GH_CI,
        ]
        for sev in (
            AutoIssue.SEVERITY_CRITICAL,
            AutoIssue.SEVERITY_HIGH,
            AutoIssue.SEVERITY_MEDIUM,
            AutoIssue.SEVERITY_LOW,
        ):
            ref = severity_factor(AutoIssue.SOURCE_TEMPO, sev)
            for source in _DEFAULT_SOURCES[1:]:
                with self.subTest(source=source, sev=sev):
                    self.assertEqual(
                        severity_factor(source, sev),
                        ref,
                        msg=f"{source}/{sev} must equal tempo/{sev}",
                    )


# ── recency_factor ────────────────────────────────────────────────────────


class RecencyFactorTests(SimpleTestCase):
    _NOW = datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)

    def test_just_seen_returns_one(self):
        score = recency_factor(self._NOW, now=self._NOW)
        self.assertAlmostEqual(score, 1.0, places=5)

    def test_seven_days_ago_returns_e_to_minus_one(self):
        last_seen = self._NOW - timedelta(days=7)
        score = recency_factor(last_seen, now=self._NOW)
        self.assertAlmostEqual(score, math.exp(-1.0), places=5)

    def test_fourteen_days_returns_e_to_minus_two(self):
        last_seen = self._NOW - timedelta(days=14)
        score = recency_factor(last_seen, now=self._NOW)
        self.assertAlmostEqual(score, math.exp(-2.0), places=5)

    def test_far_past_approaches_zero(self):
        last_seen = self._NOW - timedelta(days=365)
        score = recency_factor(last_seen, now=self._NOW)
        self.assertLess(score, 0.001)

    def test_naive_datetime_treated_as_utc(self):
        """Naive datetimes must not raise TypeError — coerced to UTC."""
        naive = datetime(2026, 5, 27, 12, 0, 0)  # no tzinfo
        score = recency_factor(naive, now=self._NOW)
        self.assertAlmostEqual(score, 1.0, places=5)

    def test_result_always_in_zero_one(self):
        for days in (0, 1, 7, 30, 180, 365):
            last_seen = self._NOW - timedelta(days=days)
            score = recency_factor(last_seen, now=self._NOW)
            self.assertGreaterEqual(score, 0.0, msg=f"days={days}")
            self.assertLessEqual(score, 1.0, msg=f"days={days}")

    def test_future_last_seen_clamped_to_zero_days(self):
        future = self._NOW + timedelta(days=1)
        score = recency_factor(future, now=self._NOW)
        self.assertAlmostEqual(score, 1.0, places=5)

    def test_one_day_uses_86400_second_divisor(self):
        """Sharp: checks the exact 86400.0 constant in the days-ago formula.

        1 day = 86400 seconds exactly.  exp(-1/7) is the expected value only
        when the divisor is exactly 86400, not 86401 or any nearby value.
        """
        last_seen = self._NOW - timedelta(seconds=86400)
        score = recency_factor(last_seen, now=self._NOW)
        self.assertAlmostEqual(score, math.exp(-1.0 / 7.0), places=10)


# ── regression_factor ─────────────────────────────────────────────────────


class RegressionFactorTests(TestCase):
    def test_no_prior_resolved_row_returns_zero(self):
        score = regression_factor(
            fingerprint="regrtest-fp-no-prior",
            last_seen=datetime(2026, 5, 27, tzinfo=timezone.utc),
        )
        self.assertEqual(score, 0.0)

    def test_regressed_issue_returns_one(self):
        from django.utils import timezone as dj_tz

        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="regr-prior-1",
            fingerprint="regr-fp-1",
            title="Prior resolved issue",
            severity=AutoIssue.SEVERITY_HIGH,
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=dj_tz.now() - timedelta(days=5),
        )
        last_seen = dj_tz.now()
        score = regression_factor(fingerprint="regr-fp-1", last_seen=last_seen)
        self.assertEqual(score, 1.0)

    def test_resolved_at_none_treated_as_no_regression(self):
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="regr-no-ts-1",
            fingerprint="regr-fp-no-ts",
            title="Resolved without timestamp",
            severity=AutoIssue.SEVERITY_MEDIUM,
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=None,
        )
        score = regression_factor(
            fingerprint="regr-fp-no-ts",
            last_seen=datetime(2026, 5, 27, tzinfo=timezone.utc),
        )
        self.assertEqual(score, 0.0)

    def test_last_seen_before_resolved_at_is_not_regression(self):
        from django.utils import timezone as dj_tz

        resolved_time = dj_tz.now()
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="regr-before-1",
            fingerprint="regr-fp-before",
            title="Resolved before last_seen",
            severity=AutoIssue.SEVERITY_HIGH,
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=resolved_time,
        )
        last_seen = resolved_time - timedelta(hours=1)
        score = regression_factor(fingerprint="regr-fp-before", last_seen=last_seen)
        self.assertEqual(score, 0.0)

    def test_naive_last_seen_coerced(self):
        from django.utils import timezone as dj_tz

        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="regr-naive-1",
            fingerprint="regr-fp-naive",
            title="Naive datetime regression test",
            severity=AutoIssue.SEVERITY_MEDIUM,
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=dj_tz.now() - timedelta(days=3),
        )
        naive_last_seen = (dj_tz.now() + timedelta(hours=1)).replace(tzinfo=None)
        score = regression_factor(fingerprint="regr-fp-naive", last_seen=naive_last_seen)
        self.assertEqual(score, 1.0)

    def test_last_seen_equal_to_resolved_at_is_not_regression(self):
        """Sharp: > operator, not >=.  Exactly at resolved_at is NOT a regression."""
        from django.utils import timezone as dj_tz

        resolved_time = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="regr-eq-resolved-1",
            fingerprint="regr-fp-equal",
            title="Equal timestamp not a regression",
            severity=AutoIssue.SEVERITY_HIGH,
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=resolved_time,
        )
        # last_seen == resolved_at → strictly not a regression
        score = regression_factor(fingerprint="regr-fp-equal", last_seen=resolved_time)
        self.assertEqual(score, 0.0)

    def test_naive_resolved_at_coerced(self):
        """Line 112 coverage: if the DB somehow returns a naive resolved_at, it must not raise."""
        from unittest.mock import MagicMock, patch

        mock_prior = MagicMock()
        mock_prior.resolved_at = datetime(2026, 1, 1, 0, 0, 0)  # naive — no tzinfo

        with patch(
            "apps.auto_issues.services.scoring.AutoIssue.objects"
        ) as mock_qs:
            mock_qs.filter.return_value.order_by.return_value.first.return_value = mock_prior
            score = regression_factor(
                fingerprint="naive-resolved-at-fp",
                last_seen=datetime(2026, 5, 27, tzinfo=timezone.utc),
            )
        self.assertEqual(score, 1.0)


# ── blast_factor ──────────────────────────────────────────────────────────


class BlastFactorTests(SimpleTestCase):
    def test_equal_observed_and_max_returns_one(self):
        self.assertEqual(blast_factor(5.0, max_observed=5.0), 1.0)

    def test_observed_exceeds_max_clamped_to_one(self):
        self.assertEqual(blast_factor(10.0, max_observed=5.0), 1.0)

    def test_zero_observed_returns_zero(self):
        self.assertEqual(blast_factor(0.0, max_observed=10.0), 0.0)

    def test_zero_max_returns_zero(self):
        """Division by zero guard: max_observed=0 must return 0."""
        self.assertEqual(blast_factor(5.0, max_observed=0.0), 0.0)

    def test_negative_max_returns_zero(self):
        self.assertEqual(blast_factor(5.0, max_observed=-1.0), 0.0)

    def test_partial_blast(self):
        self.assertAlmostEqual(blast_factor(3.0, max_observed=10.0), 0.3, places=9)

    def test_max_observed_one_is_not_zero(self):
        """Sharp: max_observed=1 must NOT return 0.0.

        Mutant changes `<= 0` to `<= 1` in the guard, which would make every
        call with max_observed=1 return 0.0 incorrectly.
        """
        self.assertAlmostEqual(blast_factor(0.5, max_observed=1.0), 0.5, places=9)
        self.assertEqual(blast_factor(1.0, max_observed=1.0), 1.0)

    def test_result_always_in_zero_one(self):
        for obs, mx in ((0.0, 10.0), (5.0, 10.0), (10.0, 10.0), (15.0, 10.0)):
            result = blast_factor(obs, max_observed=mx)
            self.assertGreaterEqual(result, 0.0)
            self.assertLessEqual(result, 1.0)


# ── cost_inv_factor ───────────────────────────────────────────────────────


class CostInvFactorTests(SimpleTestCase):
    def test_zero_files_returns_one(self):
        self.assertAlmostEqual(cost_inv_factor(0), 1.0, places=9)

    def test_one_file_matches_formula(self):
        expected = 1.0 / (1.0 + math.log(2.0))
        self.assertAlmostEqual(cost_inv_factor(1), expected, places=9)

    def test_larger_file_counts_decrease_score(self):
        self.assertGreater(cost_inv_factor(1), cost_inv_factor(5))
        self.assertGreater(cost_inv_factor(5), cost_inv_factor(50))

    def test_many_files_approaches_zero(self):
        self.assertLess(cost_inv_factor(10_000), 0.10)

    def test_negative_num_files_treated_as_zero(self):
        self.assertAlmostEqual(cost_inv_factor(-5), cost_inv_factor(0), places=9)

    def test_result_always_positive(self):
        for n in (0, 1, 5, 50, 500):
            self.assertGreater(cost_inv_factor(n), 0.0, msg=f"n={n}")


# ── Candidate dataclass ───────────────────────────────────────────────────


class CandidateFrozenTests(SimpleTestCase):
    _NOW = datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)

    def _make(self) -> Candidate:
        return Candidate(
            source=AutoIssue.SOURCE_AGENT,
            external_id="frozen-test-1",
            fingerprint="frozen-fp",
            severity=AutoIssue.SEVERITY_MEDIUM,
            last_seen=self._NOW,
            blast_observed=1.0,
            blast_max=2.0,
            num_affected_files=1,
        )

    def test_candidate_is_frozen(self):
        """Sharp: frozen=True on Candidate — writing any field must raise."""
        from dataclasses import FrozenInstanceError

        c = self._make()
        with self.assertRaises(FrozenInstanceError):
            c.external_id = "mutated"  # type: ignore[misc]


# ── top_k ─────────────────────────────────────────────────────────────────


class TopKTests(TestCase):
    _NOW = datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)

    def _make_candidate(self, external_id: str, severity: str = AutoIssue.SEVERITY_MEDIUM) -> Candidate:
        return Candidate(
            source=AutoIssue.SOURCE_AGENT,
            external_id=external_id,
            fingerprint=f"topk-fp-{external_id}",
            severity=severity,
            last_seen=self._NOW,
            blast_observed=1.0,
            blast_max=1.0,
            num_affected_files=1,
        )

    def test_returns_k_items(self):
        candidates = [self._make_candidate(str(i)) for i in range(20)]
        result = top_k(candidates, k=5)
        self.assertEqual(len(result), 5)

    def test_empty_candidates_returns_empty(self):
        self.assertEqual(top_k([], k=10), [])

    def test_k_larger_than_candidates_returns_all(self):
        candidates = [self._make_candidate(str(i)) for i in range(3)]
        result = top_k(candidates, k=100)
        self.assertEqual(len(result), 3)

    def test_negative_k_raises_value_error(self):
        """Bug 7 fix: negative k must raise ValueError, not silently return []."""
        with self.assertRaisesRegex(ValueError, r"^k must be"):
            top_k([], k=-1)

    def test_zero_k_raises_value_error(self):
        """Bug 7 fix: k=0 must raise ValueError — no legitimate use case for zero candidates."""
        with self.assertRaisesRegex(ValueError, r"^k must be"):
            top_k([], k=0)

    def test_default_k_is_10(self):
        """Sharp: kills mutant 105 — default k=10 changed to k=11.

        With 20 candidates and no explicit k, top_k must return exactly 10.
        """
        candidates = [self._make_candidate(str(i)) for i in range(20)]
        result = top_k(candidates)
        self.assertEqual(len(result), 10)

    def test_result_is_sorted_descending_by_score(self):
        candidates = [
            self._make_candidate("low", AutoIssue.SEVERITY_LOW),
            self._make_candidate("high", AutoIssue.SEVERITY_HIGH),
            self._make_candidate("medium", AutoIssue.SEVERITY_MEDIUM),
        ]
        result = top_k(candidates, k=3)
        scores = [score_candidate(c, now=self._NOW) for c in result]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_result_contains_highest_scored_candidates(self):
        high = self._make_candidate("high-one", AutoIssue.SEVERITY_HIGH)
        low = self._make_candidate("low-one", AutoIssue.SEVERITY_LOW)
        result = top_k([low, high], k=1)
        self.assertEqual(result[0].external_id, "high-one")


# ── score_candidate ───────────────────────────────────────────────────────


class ScoreCandidateTests(TestCase):
    _NOW = datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)

    def _make_candidate(self, fingerprint: str = "score-fp-x") -> Candidate:
        return Candidate(
            source=AutoIssue.SOURCE_GLITCHTIP,
            external_id="score-ext-1",
            fingerprint=fingerprint,
            severity=AutoIssue.SEVERITY_HIGH,
            last_seen=self._NOW,
            blast_observed=5.0,
            blast_max=10.0,
            num_affected_files=3,
        )

    def test_score_is_within_zero_and_one(self):
        cand = self._make_candidate()
        score = score_candidate(cand, now=self._NOW)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_regression_candidate_scores_higher(self):
        from django.utils import timezone as dj_tz

        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_GLITCHTIP,
            external_id="sc-reg-prior",
            fingerprint="sc-reg-fp",
            title="Prior resolved",
            severity=AutoIssue.SEVERITY_HIGH,
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=dj_tz.now() - timedelta(days=5),
        )
        cand_reg = self._make_candidate(fingerprint="sc-reg-fp")
        cand_noreg = self._make_candidate(fingerprint="sc-noreg-fp")
        score_reg = score_candidate(cand_reg, now=dj_tz.now())
        score_noreg = score_candidate(cand_noreg, now=dj_tz.now())
        self.assertGreater(score_reg, score_noreg)

    def test_non_regression_result_clamped_to_one(self):
        """Bug 3 fix: non-regression path applies min(1.0, base)."""
        cand = Candidate(
            source=AutoIssue.SOURCE_GLITCHTIP,
            external_id="clamp-1",
            fingerprint="clamp-fp-noreg",  # no prior resolved row
            severity=AutoIssue.SEVERITY_CRITICAL,
            last_seen=self._NOW,
            blast_observed=1.0,
            blast_max=1.0,
            num_affected_files=1,
        )
        score = score_candidate(cand, now=self._NOW)
        self.assertLessEqual(score, 1.0)

    def test_non_regression_clamp_uses_one_as_hard_cap(self):
        """A defensive clamp must keep scores at 1.0 even if factor inputs drift upward."""
        cand = self._make_candidate(fingerprint="clamp-hard-cap-fp")
        with (
            patch("apps.auto_issues.services.scoring.severity_factor", return_value=2.0),
            patch("apps.auto_issues.services.scoring.recency_factor", return_value=2.0),
            patch("apps.auto_issues.services.scoring.regression_factor", return_value=0.0),
            patch("apps.auto_issues.services.scoring.blast_factor", return_value=2.0),
            patch("apps.auto_issues.services.scoring.cost_inv_factor", return_value=2.0),
        ):
            score = score_candidate(cand, now=self._NOW)

        self.assertEqual(score, 1.0)

    def test_custom_weights_change_score(self):
        # Weights that are identical except recency are swapped with recurrence.
        w = ScoringWeights(
            severity=0.35,
            recency=0.10,
            recurrence=0.30,  # bumped recurrence weight
            blast=0.15,
            cost_inv=0.10,
        )
        cand = self._make_candidate()
        score = score_candidate(cand, weights=w, now=self._NOW)
        default_score = score_candidate(cand, now=self._NOW)
        # With no prior resolved row, recurrence contributes 0 regardless.
        # A lower recency weight means slightly lower default score.
        self.assertNotEqual(score, default_score)

    def test_regression_multiplier_is_exactly_1_5(self):
        """Sharp: verifies the 1.5 regression multiplier constant.

        Construct a candidate where the base score is known exactly, then
        check that the regression path returns base * 1.5 (clamped to 1.0).
        We use a candidate that scores low enough that 1.5× stays below 1.0
        so we can verify the exact multiplied value rather than the clamped 1.0.
        """
        from django.utils import timezone as dj_tz
        import math as _math

        resolved_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="mult-prior-1",
            fingerprint="mult-fp-1",
            title="Multiplier regression test",
            severity=AutoIssue.SEVERITY_MEDIUM,
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=resolved_time,
        )
        # All-zero blast, high cost, medium sev → low base score
        cand = Candidate(
            source=AutoIssue.SOURCE_AGENT,
            external_id="mult-1",
            fingerprint="mult-fp-1",
            severity=AutoIssue.SEVERITY_LOW,
            last_seen=datetime(2026, 1, 2, tzinfo=timezone.utc),  # after resolved
            blast_observed=0.0,
            blast_max=10.0,
            num_affected_files=50,
        )
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        w = ScoringWeights(
            severity=0.35,
            recency=0.20,
            recurrence=0.20,
            blast=0.15,
            cost_inv=0.10,
        )
        # Compute expected base manually:
        sev = 0.10   # SOURCE_AGENT LOW
        rec = 1.0    # last_seen == now, so days_ago = 0 → exp(0) = 1.0
        reg = 1.0    # regression detected
        blast = 0.0  # 0 / 10
        cost = 1.0 / (1.0 + _math.log(1.0 + 50))
        base = (
            w.severity * sev
            + w.recency * rec
            + w.recurrence * reg
            + w.blast * blast
            + w.cost_inv * cost
        )
        expected = min(1.0, base * 1.5)
        actual = score_candidate(cand, weights=w, now=now)
        self.assertAlmostEqual(actual, expected, places=9)
        # Also assert the multiplier pushes the score above the non-regression path
        self.assertGreater(actual, min(1.0, base))

    def test_regression_path_clamps_score_to_one(self):
        """Sharp: kills mutant 102 — min(1.0, base*1.5) → min(2.0, base*1.5).

        When all factors = 1.0 and weights sum to 1.0, base = 1.0 and
        base*1.5 = 1.5. min(1.0, 1.5) = 1.0; min(2.0, 1.5) = 1.5.
        """
        resolved_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_GLITCHTIP,
            external_id="clamp-reg-prior-1",
            fingerprint="clamp-reg-fp-1",
            title="Clamp regression test",
            severity=AutoIssue.SEVERITY_CRITICAL,
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=resolved_time,
        )
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        cand = Candidate(
            source=AutoIssue.SOURCE_GLITCHTIP,
            external_id="clamp-reg-1",
            fingerprint="clamp-reg-fp-1",
            severity=AutoIssue.SEVERITY_CRITICAL,  # sev=1.0
            last_seen=now,                          # rec=1.0
            blast_observed=1.0,
            blast_max=1.0,                          # blast=1.0
            num_affected_files=0,                   # cost_inv(0)=1.0
        )
        score = score_candidate(cand, now=now)
        self.assertEqual(score, 1.0)

    def test_score_without_weights_arg_uses_defaults(self):
        """Sharp: calling score_candidate() with no weights argument must work.

        With the None-default fix, the default ScoringWeights() is created
        inside the function body at call time (not at module import time).
        """
        cand = self._make_candidate()
        score = score_candidate(cand, now=self._NOW)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_recency_weight_uses_multiplication_not_division(self):
        """Sharp: kills mutant 92 — weights.recency * rec → weights.recency / rec.

        When rec = exp(-1) ≈ 0.368 (candidate seen exactly 7 days ago),
        multiplication gives 0.20 × 0.368 ≈ 0.074 while
        division gives 0.20 / 0.368 ≈ 0.544 — vastly different.
        The test fails iff the division mutant is active.
        """
        seven_days_ago = self._NOW - timedelta(days=7)
        cand = Candidate(
            source=AutoIssue.SOURCE_AGENT,
            external_id="recency-mult-test-1",
            fingerprint="recency-mult-fp",   # no prior resolved row
            severity=AutoIssue.SEVERITY_LOW,
            last_seen=seven_days_ago,
            blast_observed=0.0,
            blast_max=10.0,
            num_affected_files=1,
        )
        w = ScoringWeights()
        rec = math.exp(-1.0)           # 7 days / tau=7 → exp(-1)
        sev = 0.10                     # SOURCE_AGENT LOW
        blast_score = 0.0              # 0.0 / 10.0
        cost = 1.0 / (1.0 + math.log(1.0 + 1))
        expected = min(
            1.0,
            w.severity * sev
            + w.recency * rec
            + w.recurrence * 0.0
            + w.blast * blast_score
            + w.cost_inv * cost,
        )
        actual = score_candidate(cand, weights=w, now=self._NOW)
        self.assertAlmostEqual(actual, expected, places=9)

    def test_severity_weight_uses_multiplication_not_division(self):
        """Sharp: kills any mutant that changes weights.severity * sev → / sev.

        Use a candidate where sev = 0.10 (not 1.0) so * and / differ.
        With AGENT LOW → sev=0.10: 0.35 * 0.10 = 0.035 vs 0.35 / 0.10 = 3.5.
        """
        cand = Candidate(
            source=AutoIssue.SOURCE_AGENT,
            external_id="sev-mult-test-1",
            fingerprint="sev-mult-fp",
            severity=AutoIssue.SEVERITY_LOW,
            last_seen=self._NOW,
            blast_observed=0.0,
            blast_max=10.0,
            num_affected_files=1,
        )
        w = ScoringWeights()
        sev = 0.10
        rec = 1.0
        blast_score = 0.0
        cost = 1.0 / (1.0 + math.log(2.0))
        expected = min(
            1.0,
            w.severity * sev + w.recency * rec + w.recurrence * 0.0
            + w.blast * blast_score + w.cost_inv * cost,
        )
        actual = score_candidate(cand, weights=w, now=self._NOW)
        self.assertAlmostEqual(actual, expected, places=9)

    def test_blast_weight_uses_multiplication_not_division(self):
        """Sharp: kills mutants that change weights.blast * blast → / blast.

        Use blast = 0.5 (not 1.0) so * and / give different results.
        """
        cand = Candidate(
            source=AutoIssue.SOURCE_AGENT,
            external_id="blast-mult-test-1",
            fingerprint="blast-mult-fp",
            severity=AutoIssue.SEVERITY_LOW,
            last_seen=self._NOW,
            blast_observed=5.0,
            blast_max=10.0,   # blast = 0.5
            num_affected_files=1,
        )
        w = ScoringWeights()
        sev = 0.10
        rec = 1.0
        blast_score = 0.5
        cost = 1.0 / (1.0 + math.log(2.0))
        expected = min(
            1.0,
            w.severity * sev + w.recency * rec + w.recurrence * 0.0
            + w.blast * blast_score + w.cost_inv * cost,
        )
        actual = score_candidate(cand, weights=w, now=self._NOW)
        self.assertAlmostEqual(actual, expected, places=9)

    def test_cost_inv_weight_uses_multiplication_not_division(self):
        """Sharp: kills mutants that change weights.cost_inv * cost → / cost.

        Use num_files=1 so cost ≈ 0.59 (not 1.0), making * and / differ.
        """
        cand = Candidate(
            source=AutoIssue.SOURCE_AGENT,
            external_id="cost-mult-test-1",
            fingerprint="cost-mult-fp",
            severity=AutoIssue.SEVERITY_LOW,
            last_seen=self._NOW,
            blast_observed=0.0,
            blast_max=10.0,
            num_affected_files=1,
        )
        w = ScoringWeights()
        sev = 0.10
        rec = 1.0
        blast_score = 0.0
        cost = 1.0 / (1.0 + math.log(2.0))  # ≈ 0.591
        expected = min(
            1.0,
            w.severity * sev + w.recency * rec + w.recurrence * 0.0
            + w.blast * blast_score + w.cost_inv * cost,
        )
        actual = score_candidate(cand, weights=w, now=self._NOW)
        self.assertAlmostEqual(actual, expected, places=9)


# ── auto_close_stale_threshold ────────────────────────────────────────────


class AutoCloseStaleThresholdTests(SimpleTestCase):
    def test_default_idle_days_is_30(self):
        td, _ = auto_close_stale_threshold()
        self.assertEqual(td, timedelta(days=30))

    def test_default_score_floor_is_point_3(self):
        _, floor = auto_close_stale_threshold()
        self.assertEqual(floor, 0.3)

    def test_custom_idle_days(self):
        td, _ = auto_close_stale_threshold(idle_days=14)
        self.assertEqual(td, timedelta(days=14))

    def test_custom_score_floor(self):
        _, floor = auto_close_stale_threshold(score_floor=0.5)
        self.assertEqual(floor, 0.5)

    def test_returns_tuple_of_two(self):
        result = auto_close_stale_threshold()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
