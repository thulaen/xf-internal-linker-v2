"""Tests for FR-247 (fast-path observability) and FR-249 (embedding age decay).

Both are new in 2026-05-07 and shipped default-on as part of the
embedding-pipeline weakness audit. Tests run as SimpleTestCase.

Sources of truth:
    * FR-247 — Beyer et al. 2016 *Site Reliability Engineering* Chapter
      4 (SLO-tracked counter per pathway). Sridharan 2018 *Distributed
      Systems Observability* Chapter 4 (cardinality budget).
    * FR-249 — Liu 2009 *Learning to Rank for IR* Foundations and
      Trends in IR 3(3) §1.5.4 (DOI 10.1561/1500000016). Newton's
      law of cooling. Rigutini et al. 2008 ICANN (temporal-decay
      multiplier pattern).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from apps.pipeline.services.embedding_age import (
    DEFAULT_HALF_LIFE_DAYS,
    compute_embedding_age_decay,
)
from apps.pipeline.services.pipeline_stages import (
    _record_stage2_path,
    get_stage2_path_counters,
    get_stage2_path_runtime_status,
    reset_stage2_path_counters,
)


class Stage2PathCounterTests(SimpleTestCase):
    """FR-247 — counter tracks C++ vs Python pathway use."""

    def setUp(self):
        reset_stage2_path_counters()

    def test_counters_start_at_zero(self):
        # Edge case: fresh process, no Stage-2 calls yet.
        counters = get_stage2_path_counters()
        self.assertEqual(counters, {"cpp": 0, "python": 0})

    def test_record_increments_correct_bucket(self):
        # Happy path: each `_record_stage2_path` bumps its bucket.
        _record_stage2_path("cpp")
        _record_stage2_path("cpp")
        _record_stage2_path("python")
        counters = get_stage2_path_counters()
        self.assertEqual(counters, {"cpp": 2, "python": 1})

    def test_runtime_status_reports_no_calls_state(self):
        # Beyer 2016 Ch. 4 — operator-visible status when nothing has run.
        status = get_stage2_path_runtime_status()
        self.assertEqual(status["cpp_calls"], 0)
        self.assertEqual(status["python_calls"], 0)
        self.assertFalse(status["alert"])

    def test_runtime_status_alert_fires_above_threshold(self):
        # Beyer 2016 Ch. 4 — SLO violation at 5% pathway divergence.
        # Default threshold 0.05; here we make python 50% of calls
        # (>> 5%) so the alert fires.
        for _ in range(5):
            _record_stage2_path("cpp")
        for _ in range(5):
            _record_stage2_path("python")
        status = get_stage2_path_runtime_status()
        self.assertEqual(status["python_calls"], 5)
        self.assertEqual(status["cpp_calls"], 5)
        self.assertEqual(status["python_share"], 0.5)
        self.assertTrue(status["alert"])

    def test_runtime_status_no_alert_below_threshold(self):
        # 1 python out of 100 = 1% < 5% threshold → no alert.
        for _ in range(99):
            _record_stage2_path("cpp")
        _record_stage2_path("python")
        status = get_stage2_path_runtime_status()
        self.assertEqual(status["python_share"], 0.01)
        self.assertFalse(status["alert"])

    def test_get_counters_returns_copy_not_live_reference(self):
        # Sridharan 2018 Ch. 4 — read-only contract on observability data.
        _record_stage2_path("cpp")
        snapshot = get_stage2_path_counters()
        snapshot["cpp"] = 999
        # Live counters unaffected.
        self.assertEqual(get_stage2_path_counters()["cpp"], 1)


class EmbeddingAgeDecayTests(SimpleTestCase):
    """FR-249 — exponential decay multiplier in [0, 1]."""

    def test_default_half_life_is_one_year(self):
        # Liu 2009 §1.5.4 — one-year half-life as the gold standard
        # default for stable corpora. Lock the constant in.
        self.assertEqual(DEFAULT_HALF_LIFE_DAYS, 365)

    def test_zero_age_returns_one(self):
        # Happy path: today's embedding has no penalty.
        now = datetime(2026, 5, 7, tzinfo=timezone.utc)
        decay = compute_embedding_age_decay(now, now=now)
        self.assertAlmostEqual(decay, 1.0, places=6)

    def test_one_half_life_returns_one_half(self):
        # Newton's cooling — at one half-life the multiplier is exactly 0.5.
        now = datetime(2026, 5, 7, tzinfo=timezone.utc)
        embedded = now - timedelta(days=365)
        decay = compute_embedding_age_decay(embedded, now=now)
        self.assertAlmostEqual(decay, 0.5, places=6)

    def test_two_half_lives_returns_one_quarter(self):
        # Newton's cooling — at two half-lives the multiplier is 0.25.
        now = datetime(2026, 5, 7, tzinfo=timezone.utc)
        embedded = now - timedelta(days=730)
        decay = compute_embedding_age_decay(embedded, now=now)
        self.assertAlmostEqual(decay, 0.25, places=6)

    def test_none_timestamp_returns_one(self):
        # Edge case: embedding has no timestamp → no penalty for unknown.
        decay = compute_embedding_age_decay(None)
        self.assertEqual(decay, 1.0)

    def test_future_timestamp_clamps_to_one(self):
        # Adversarial: clock-skew could produce a "future" embedding.
        # Documented contract: clamp to 1.0; never produce negative-day
        # decay. Avoids mathematical absurdity.
        now = datetime(2026, 5, 7, tzinfo=timezone.utc)
        embedded = now + timedelta(days=10)  # in the future
        decay = compute_embedding_age_decay(embedded, now=now)
        self.assertEqual(decay, 1.0)

    def test_zero_half_life_returns_one_no_divide_by_zero(self):
        # Adversarial: degenerate config; safe pass-through.
        now = datetime(2026, 5, 7, tzinfo=timezone.utc)
        embedded = now - timedelta(days=100)
        decay = compute_embedding_age_decay(embedded, now=now, half_life_days=0)
        self.assertEqual(decay, 1.0)

    def test_naive_datetime_treated_as_utc(self):
        # Edge case: a tz-naive datetime (e.g. from an old DB row).
        # Documented contract: interpret as UTC.
        now = datetime(2026, 5, 7, tzinfo=timezone.utc)
        embedded = datetime(2025, 5, 7)  # naive == UTC
        decay = compute_embedding_age_decay(embedded, now=now)
        self.assertAlmostEqual(decay, 0.5, places=6)

    def test_custom_half_life(self):
        # Operator override: 30-day half-life (e.g. for fast-moving
        # news corpus). At 30 days the multiplier should be 0.5.
        now = datetime(2026, 5, 7, tzinfo=timezone.utc)
        embedded = now - timedelta(days=30)
        decay = compute_embedding_age_decay(embedded, now=now, half_life_days=30)
        self.assertAlmostEqual(decay, 0.5, places=6)
