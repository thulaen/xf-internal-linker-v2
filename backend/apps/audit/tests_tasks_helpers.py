"""
SimpleTestCase coverage for pure-function helpers in apps.audit.tasks.

All tests run without a database — no Django TestCase or fixtures needed.
DB-accessing helpers (_fetch_period_metrics, _collect_review_pairs,
_sync_one_glitchtip_issue) are exercised by the integration tests in
test_gt_phase.py instead.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.test import SimpleTestCase

from apps.audit.tasks import (
    _build_glitchtip_issue_kwargs,
    _compute_avg_review_time,
    _compute_rate,
    _extract_top_rejection_reasons,
    _glitchtip_why_message,
    _parse_glitchtip_tags,
    _scorecard_week_period,
)


# ── _scorecard_week_period ─────────────────────────────────────────────────


class ScoreCardWeekPeriodTests(SimpleTestCase):
    def test_monday_gives_previous_full_week(self):
        # Monday 2026-05-04 → period Mon 2026-04-27 … Sun 2026-05-03
        today = date(2026, 5, 4)
        start, end = _scorecard_week_period(today)
        self.assertEqual(end, date(2026, 5, 3))
        self.assertEqual(start, date(2026, 4, 27))
        self.assertEqual((end - start).days, 6)

    def test_midweek_gives_same_previous_week(self):
        # Wednesday 2026-05-06 → period Mon 2026-04-27 … Sun 2026-05-03
        today = date(2026, 5, 6)
        start, end = _scorecard_week_period(today)
        self.assertEqual(end, date(2026, 5, 5))
        self.assertEqual(start, date(2026, 4, 29))
        self.assertEqual((end - start).days, 6)


# ── _compute_rate ──────────────────────────────────────────────────────────


class ComputeRateTests(SimpleTestCase):
    def test_zero_denominator_returns_zero(self):
        self.assertEqual(_compute_rate(0, 0), 0.0)
        self.assertEqual(_compute_rate(5, 0), 0.0)

    def test_normal_rate(self):
        self.assertAlmostEqual(_compute_rate(3, 10), 30.0)

    def test_full_rate_is_100(self):
        self.assertAlmostEqual(_compute_rate(7, 7), 100.0)

    def test_partial_approval(self):
        self.assertAlmostEqual(_compute_rate(1, 4), 25.0)


# ── _compute_avg_review_time ───────────────────────────────────────────────

_UTC = dt_timezone.utc


def _dt(hours_ago: float) -> datetime:
    """Helper: a UTC datetime that many hours before a fixed reference."""
    ref = datetime(2026, 5, 6, 12, 0, 0, tzinfo=_UTC)
    return ref - timedelta(hours=hours_ago)


class ComputeAvgReviewTimeTests(SimpleTestCase):
    def test_empty_list_returns_none(self):
        self.assertIsNone(_compute_avg_review_time([]))

    def test_normal_average(self):
        # audit 2h after suggestion → 7200 s
        pairs = [(_dt(0), _dt(2)), (_dt(0), _dt(4))]  # 7200s and 14400s
        result = _compute_avg_review_time(pairs)
        self.assertAlmostEqual(result, (7200 + 14400) / 2)

    def test_filters_outliers_above_7_days(self):
        # 8 days elapsed → should be dropped; only the 1-hour pair survives
        pairs = [
            (_dt(0), _dt(1)),  # 3600 s — valid
            (_dt(0), _dt(24 * 8)),  # 691200 s > 604800 — outlier
        ]
        result = _compute_avg_review_time(pairs)
        self.assertAlmostEqual(result, 3600.0)

    def test_filters_negative_elapsed(self):
        # audit before suggestion → negative → dropped
        pairs = [(_dt(2), _dt(0))]  # audit earlier than suggestion
        self.assertIsNone(_compute_avg_review_time(pairs))

    def test_all_outliers_returns_none(self):
        pairs = [(_dt(0), _dt(24 * 9))]  # 9 days
        self.assertIsNone(_compute_avg_review_time(pairs))


# ── _extract_top_rejection_reasons ────────────────────────────────────────


class ExtractTopRejectionReasonsTests(SimpleTestCase):
    def test_empty_list(self):
        self.assertEqual(_extract_top_rejection_reasons([]), [])

    def test_counts_and_orders(self):
        details = [
            {"rejection_reason": "spam"},
            {"rejection_reason": "spam"},
            {"rejection_reason": "off_topic"},
        ]
        result = _extract_top_rejection_reasons(details)
        self.assertEqual(result[0], {"reason": "spam", "count": 2})
        self.assertEqual(result[1], {"reason": "off_topic", "count": 1})

    def test_none_detail_falls_back_to_unknown(self):
        result = _extract_top_rejection_reasons([None, None])
        self.assertEqual(result, [{"reason": "unknown", "count": 2}])

    def test_top_5_cap(self):
        details = [{"rejection_reason": str(i)} for i in range(10)]
        result = _extract_top_rejection_reasons(details)
        self.assertLessEqual(len(result), 5)

    def test_missing_key_falls_back_to_unknown(self):
        result = _extract_top_rejection_reasons([{"other_key": "x"}])
        self.assertEqual(result[0]["reason"], "unknown")


# ── _parse_glitchtip_tags ──────────────────────────────────────────────────


class ParseGlitchtipTagsTests(SimpleTestCase):
    def test_valid_tags_list(self):
        tags = [["server_name", "web-01"], ["node_id", "n1"]]
        result = _parse_glitchtip_tags(tags)
        self.assertEqual(result, {"server_name": "web-01", "node_id": "n1"})

    def test_none_tags_returns_empty(self):
        self.assertEqual(_parse_glitchtip_tags(None), {})

    def test_empty_list_returns_empty(self):
        self.assertEqual(_parse_glitchtip_tags([]), {})

    def test_malformed_tag_skipped(self):
        # Single-element list and non-list entry should both be skipped
        tags = [["good_key", "good_val"], ["only_one"], "not_a_list"]
        result = _parse_glitchtip_tags(tags)
        self.assertEqual(result, {"good_key": "good_val"})


# ── _glitchtip_why_message ─────────────────────────────────────────────────


class GlitchtipWhyMessageTests(SimpleTestCase):
    def test_with_culprit(self):
        msg = _glitchtip_why_message("error", "myapp.tasks.run", 3)
        self.assertIn("'error'", msg)
        self.assertIn("myapp.tasks.run", msg)
        self.assertIn("3 time(s)", msg)

    def test_without_culprit_shows_unknown(self):
        msg = _glitchtip_why_message("fatal", "", 1)
        self.assertIn("unknown", msg)
        self.assertIn("'fatal'", msg)


# ── _build_glitchtip_issue_kwargs ──────────────────────────────────────────


class BuildGlitchtipIssueKwargsTests(SimpleTestCase):
    def _suggest_stub(self, title: str, fingerprint: str, culprit: str) -> str:
        return "stub fix"

    def _make_issue(self, **overrides) -> dict:
        base = {
            "id": "42",
            "title": "NullPointerException",
            "culprit": "myapp.views.index",
            "level": "error",
            "count": 5,
            "fingerprint": ["abc", "def"],
            "tags": [["server_name", "web-01"]],
            "status": "unresolved",
        }
        base.update(overrides)
        return base

    def test_basic_kwargs_shape(self):
        kwargs = _build_glitchtip_issue_kwargs(
            self._make_issue(), "https://gt.example.com", self._suggest_stub
        )
        self.assertEqual(kwargs["source"], "glitchtip")
        self.assertEqual(kwargs["glitchtip_issue_id"], "42")
        self.assertEqual(kwargs["severity"], "high")  # "error" → "high"
        self.assertEqual(kwargs["occurrence_count"], 5)
        self.assertEqual(kwargs["node_hostname"], "web-01")

    def test_severity_mapping_fatal_to_critical(self):
        kwargs = _build_glitchtip_issue_kwargs(
            self._make_issue(level="fatal"),
            "https://gt.example.com",
            self._suggest_stub,
        )
        self.assertEqual(kwargs["severity"], "critical")

    def test_fingerprint_fallback_when_empty(self):
        kwargs = _build_glitchtip_issue_kwargs(
            self._make_issue(fingerprint=None),
            "https://gt.example.com",
            self._suggest_stub,
        )
        # fallback produces a 40-char SHA-1 hex string
        self.assertEqual(len(kwargs["fingerprint"]), 40)

    def test_fingerprint_truncated_to_255(self):
        long_fp = ["x" * 300]
        kwargs = _build_glitchtip_issue_kwargs(
            self._make_issue(fingerprint=long_fp),
            "https://gt.example.com",
            self._suggest_stub,
        )
        self.assertLessEqual(len(kwargs["fingerprint"]), 255)

    def test_tags_extracted_to_node_fields(self):
        tags = [["node_id", "n99"], ["node_role", "worker"], ["server_name", "srv-2"]]
        kwargs = _build_glitchtip_issue_kwargs(
            self._make_issue(tags=tags), "https://gt.example.com", self._suggest_stub
        )
        self.assertEqual(kwargs["node_id"], "n99")
        self.assertEqual(kwargs["node_role"], "worker")
        self.assertEqual(kwargs["node_hostname"], "srv-2")

    def test_suggest_fn_called_with_correct_args(self):
        calls: list[tuple] = []

        def recording_suggest(title, fingerprint, culprit):
            calls.append((title, fingerprint, culprit))
            return "fix it"

        _build_glitchtip_issue_kwargs(
            self._make_issue(), "https://gt.example.com", recording_suggest
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "NullPointerException")
        self.assertEqual(calls[0][2], "myapp.views.index")
