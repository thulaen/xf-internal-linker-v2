"""Tests for the daily issue pickers.

Covers:
  - `services.scoring` — the 5-factor blend (pure functions, fast).
  - `services.glitchtip_picker` — read mirror, score, upsert.
  - `services.pyroscope_picker` — diff parser + regression detection.
  - `tasks.close_stale_issues` — auto-defer rule.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone as dj_timezone

from apps.audit.models import ErrorLog
from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import scoring
from apps.auto_issues.services.glitchtip_picker import pick_glitchtip_issues
from apps.auto_issues.services.pyroscope_picker import (
    PyroscopeCandidate,
    _compare_sides,
    _extract_function_totals,
    _stable_fingerprint,
    pick_pyroscope_regressions,
)
from apps.auto_issues.tasks import close_stale_issues


class ScoringFactorTests(SimpleTestCase):
    def test_severity_table_glitchtip_critical(self):
        self.assertEqual(
            scoring.severity_factor("glitchtip", "critical"), 1.0
        )

    def test_severity_unknown_combo_falls_back_to_zero(self):
        self.assertEqual(scoring.severity_factor("???", "high"), 0.0)
        self.assertEqual(scoring.severity_factor("glitchtip", "???"), 0.0)

    def test_recency_decays_exponentially(self):
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        # 0 days ago → 1.0
        self.assertAlmostEqual(scoring.recency_factor(now, now=now), 1.0)
        # 7 days ago (= tau) → 1/e ≈ 0.368
        seven = now - timedelta(days=7)
        self.assertAlmostEqual(
            scoring.recency_factor(seven, now=now), 1 / 2.718281828, places=2
        )
        # 30 days ago → ~0.014
        thirty = now - timedelta(days=30)
        self.assertLess(scoring.recency_factor(thirty, now=now), 0.05)

    def test_blast_factor_clamped_to_one(self):
        self.assertEqual(scoring.blast_factor(50.0, max_observed=10.0), 1.0)
        self.assertEqual(scoring.blast_factor(5.0, max_observed=10.0), 0.5)
        self.assertEqual(scoring.blast_factor(5.0, max_observed=0.0), 0.0)

    def test_cost_inv_logarithmic(self):
        # 1-file fix → ≈ 1 / (1 + ln(2)) ≈ 0.59
        self.assertAlmostEqual(scoring.cost_inv_factor(1), 0.591, places=2)
        # 50-file fix → ≈ 1 / (1 + ln(51)) ≈ 0.20
        self.assertLess(scoring.cost_inv_factor(50), 0.30)
        # 0-file → 1.0 (no penalty)
        self.assertEqual(scoring.cost_inv_factor(0), 1.0)


class RegressionFactorTests(TestCase):
    def test_no_prior_resolved_row_returns_zero(self):
        last_seen = dj_timezone.now()
        self.assertEqual(
            scoring.regression_factor(fingerprint="never-seen", last_seen=last_seen),
            0.0,
        )

    def test_fresh_recurrence_after_resolution_returns_one(self):
        # Pre-seed a resolved row.
        AutoIssue.objects.create(
            source="glitchtip",
            external_id="gt-old",
            fingerprint="shared-fp",
            title="Old bug",
            severity="high",
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=dj_timezone.now() - timedelta(days=2),
            resolved_by="claude",
        )
        # The new candidate's last_seen is AFTER the resolution → regression.
        self.assertEqual(
            scoring.regression_factor(
                fingerprint="shared-fp",
                last_seen=dj_timezone.now(),
            ),
            1.0,
        )

    def test_stale_recurrence_before_resolution_returns_zero(self):
        AutoIssue.objects.create(
            source="glitchtip",
            external_id="gt-old",
            fingerprint="shared-fp",
            title="Old bug",
            severity="high",
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=dj_timezone.now(),
            resolved_by="claude",
        )
        # Last seen BEFORE resolution = same instance, not a regression.
        self.assertEqual(
            scoring.regression_factor(
                fingerprint="shared-fp",
                last_seen=dj_timezone.now() - timedelta(days=5),
            ),
            0.0,
        )


class GlitchtipPickerTests(TestCase):
    def test_empty_mirror_returns_zero_promoted(self):
        result = pick_glitchtip_issues()
        self.assertEqual(result, {"status": "ok", "fetched": 0, "promoted": 0})
        self.assertEqual(AutoIssue.objects.count(), 0)

    def test_promotes_top_glitchtip_rows(self):
        ErrorLog.objects.create(
            source=ErrorLog.SOURCE_GLITCHTIP,
            glitchtip_issue_id="gt-1",
            fingerprint="fp-1",
            error_message="Boom",
            severity="high",
            occurrence_count=10,
            acknowledged=False,
        )
        result = pick_glitchtip_issues(limit=5)
        self.assertEqual(result["fetched"], 1)
        self.assertEqual(result["promoted"], 1)
        self.assertEqual(AutoIssue.objects.count(), 1)
        row = AutoIssue.objects.first()
        self.assertEqual(row.source, "glitchtip")
        self.assertEqual(row.external_id, "gt-1")
        self.assertGreater(row.priority_score, 0.0)

    def test_idempotent_upsert_does_not_create_duplicates(self):
        ErrorLog.objects.create(
            source=ErrorLog.SOURCE_GLITCHTIP,
            glitchtip_issue_id="gt-1",
            fingerprint="fp-1",
            error_message="Boom",
            severity="high",
            occurrence_count=10,
            acknowledged=False,
        )
        pick_glitchtip_issues()
        pick_glitchtip_issues()
        self.assertEqual(
            AutoIssue.objects.filter(source="glitchtip", external_id="gt-1").count(),
            1,
        )


class PyroscopeFlamegraphParserTests(SimpleTestCase):
    """Pure-function tests on the diff response parser. No live HTTP."""

    def test_extract_function_totals_from_flamebearer(self):
        side = {
            "flamebearer": {
                "names": ["root", "func_a", "func_b"],
                "levels": [
                    [0, 100, 0, 0],   # root, total=100, self=0
                    [0, 60, 60, 1, 60, 40, 40, 2],  # func_a self=60, func_b self=40
                ],
            }
        }
        totals = _extract_function_totals(side)
        self.assertEqual(totals.get("func_a"), 60.0)
        self.assertEqual(totals.get("func_b"), 40.0)

    def test_compare_sides_flags_2x_regression_above_5pct(self):
        left = {"hot_func": 1_000_000_000, "cold": 100}
        # right side: hot doubled to 2.5x → regression. Total=2.5e9.
        right = {"hot_func": 2_500_000_000, "cold": 100}
        cands = _compare_sides(left, right)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].function_name, "hot_func")

    def test_compare_sides_skips_under_5pct_share(self):
        left = {"hot": 1, "noisy": 100}
        # right total = 200, noisy = 200/202 → 99% share, hot is 1% share. The
        # hot ratio is huge but it's only 0.5 % of total — should be skipped.
        right = {"hot": 200, "noisy": 100_000_000}
        cands = _compare_sides(left, right)
        names = [c.function_name for c in cands]
        self.assertNotIn("hot", names)

    def test_compare_sides_skips_brand_new_function(self):
        # left has 0 ns; right has 1ms. left < min threshold → skip.
        left = {"new_func": 0}
        right = {"new_func": 1_000_000_000}  # 1 second — high share.
        cands = _compare_sides(left, right)
        self.assertEqual(cands, [])

    def test_stable_fingerprint_is_deterministic(self):
        a = _stable_fingerprint("foo.bar", "/app/foo.py")
        b = _stable_fingerprint("foo.bar", "/app/foo.py")
        c = _stable_fingerprint("foo.bar", "/app/different.py")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class PyroscopePickerTopLevelTests(TestCase):
    @mock.patch.dict("os.environ", {"PYROSCOPE_SERVER_ADDRESS": ""})
    def test_no_server_address_skips_cleanly(self):
        result = pick_pyroscope_regressions(server="")
        self.assertEqual(result["status"], "skipped")

    @mock.patch("apps.auto_issues.services.pyroscope_picker._query_pyroscope_diff")
    def test_no_regressions_returns_zero_promoted(self, mock_diff):
        mock_diff.return_value = {"left": {}, "right": {}}
        result = pick_pyroscope_regressions(server="http://test:4040")
        self.assertEqual(result["regressions_found"], 0)
        self.assertEqual(result["promoted"], 0)


class CloseStaleIssuesTaskTests(TestCase):
    def test_closes_idle_low_score_rows(self):
        # Stale + low score → should close.
        old = AutoIssue.objects.create(
            source="agent",
            external_id="stale-1",
            fingerprint="x",
            title="Stale low-priority",
            severity="low",
            status=AutoIssue.STATUS_OPEN,
            priority_score=0.1,
        )
        AutoIssue.objects.filter(pk=old.pk).update(
            last_seen=dj_timezone.now() - timedelta(days=45)
        )
        # Recent → should NOT close.
        AutoIssue.objects.create(
            source="agent",
            external_id="recent-1",
            fingerprint="y",
            title="Recent",
            severity="low",
            status=AutoIssue.STATUS_OPEN,
            priority_score=0.1,
        )
        # High-score idle → should NOT close.
        old_high = AutoIssue.objects.create(
            source="agent",
            external_id="stale-high-1",
            fingerprint="z",
            title="Stale but high-priority",
            severity="critical",
            status=AutoIssue.STATUS_OPEN,
            priority_score=0.9,
        )
        AutoIssue.objects.filter(pk=old_high.pk).update(
            last_seen=dj_timezone.now() - timedelta(days=45)
        )

        result = close_stale_issues()
        self.assertEqual(result, {"status": "ok", "closed": 1})
        old.refresh_from_db()
        self.assertEqual(old.status, AutoIssue.STATUS_DEFERRED)
        self.assertEqual(old.resolved_by, "auto-stale")
