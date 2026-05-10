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
    _select_hotspots,
    _stable_fingerprint,
    pick_pyroscope_hotspots,
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


class PickerScheduleCadenceTests(SimpleTestCase):
    """Pin the GlitchTip picker schedule so it cannot silently regress to
    once-daily.

    Why: the picker runs as part of the session-start ABSOLUTE rule.
    When the schedule was `crontab(hour=11, minute=0)` (once daily), 89
    unacknowledged GlitchTip errors sat un-promoted to AutoIssues until
    11:00 UTC, and any agent session before that hour saw a stale 0
    count. Bumping cadence to every 30 min during the active-laptop
    window (11-23 UTC) keeps the data fresh. See plan
    `does-adding-qodana-make-swift-wall.md` Stream 1.

    The picker is a pure DB job (~0.4 s per run) and idempotent via the
    `(source, external_id)` unique constraint — running 24× per active
    day is cheap and safe.
    """

    def test_glitchtip_picker_runs_at_least_every_30_minutes(self):
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        entry = CELERY_BEAT_SCHEDULE.get("auto-issues-glitchtip-pick")
        self.assertIsNotNone(entry, "GlitchTip picker schedule entry missing")
        cron = entry["schedule"]
        self.assertIn(
            5, cron.minute,
            "GlitchTip picker must fire at :05 (5 min after sync at :00)",
        )
        self.assertIn(
            35, cron.minute,
            "GlitchTip picker must fire at :35 (5 min after sync at :30)",
        )
        self.assertEqual(
            len(cron.hour), 13,
            "GlitchTip picker must run hours 11-23 inclusive (13 hours)",
        )

    def test_glitchtip_picker_staggered_after_sync(self):
        """Picker minutes must be 5 min after sync minutes so the mirror
        is populated before the picker reads it."""
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        sync = CELERY_BEAT_SCHEDULE["glitchtip-issue-sync"]["schedule"]
        picker = CELERY_BEAT_SCHEDULE["auto-issues-glitchtip-pick"]["schedule"]
        for sync_min in sync.minute:
            self.assertIn(
                (sync_min + 5) % 60, picker.minute,
                f"Picker should fire 5 min after sync at :{sync_min:02d}",
            )

    def test_pyroscope_picker_runs_every_30_minutes(self):
        """Pyroscope picker must run frequently enough that session-start
        sees fresh hotspots — same as GlitchTip. Stream 2 of plan
        does-adding-qodana-make-swift-wall.md."""
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        entry = CELERY_BEAT_SCHEDULE.get("auto-issues-pyroscope-pick")
        self.assertIsNotNone(entry, "Pyroscope picker schedule entry missing")
        cron = entry["schedule"]
        self.assertIn(10, cron.minute)
        self.assertIn(40, cron.minute)
        self.assertEqual(
            len(cron.hour), 13,
            "Pyroscope picker must run hours 11-23 inclusive",
        )

    def test_pyroscope_picker_staggered_after_glitchtip(self):
        """Pyroscope must fire 5 min after GlitchTip so the two pickers
        don't fight Postgres in the same instant."""
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        gt = CELERY_BEAT_SCHEDULE["auto-issues-glitchtip-pick"]["schedule"]
        pyro = CELERY_BEAT_SCHEDULE["auto-issues-pyroscope-pick"]["schedule"]
        for gt_min in gt.minute:
            self.assertIn(
                (gt_min + 5) % 60, pyro.minute,
                f"Pyroscope should fire 5 min after GT at :{gt_min:02d}",
            )


class PyroscopeHotspotDetectorTests(SimpleTestCase):
    """Tests for the same-day hotspot detector added 2026-05-10
    (plan does-adding-qodana-make-swift-wall.md Stream 2).

    Same-day hotspots fill the 7-day warmup gap of the week-over-week
    regression detector. We test the pure-function selector here; the
    integration with Pyroscope HTTP is tested via mock in
    ``PyroscopeHotspotIntegrationTests`` below.
    """

    def test_select_hotspots_filters_below_threshold(self):
        # 100 ns total. function_a is 60% (= hotspot at 5%), function_b is 3%
        # (= below threshold), function_c is 37%.
        totals = {"function_a": 60.0, "function_b": 3.0, "function_c": 37.0}
        cands = _select_hotspots(totals, threshold_pct=5.0)
        names = sorted(c.function_name for c in cands)
        self.assertEqual(names, ["function_a", "function_c"])

    def test_select_hotspots_returns_empty_when_all_below_threshold(self):
        # 1000 ns total spread across 100 functions evenly -> each is 1%.
        # At threshold 5% nothing should pass.
        totals = {f"fn_{i}": 10.0 for i in range(100)}
        cands = _select_hotspots(totals, threshold_pct=5.0)
        self.assertEqual(cands, [])

    def test_select_hotspots_extracts_file_hint_when_present(self):
        # Pyroscope sometimes encodes file paths as "module/file.py:lineno".
        totals = {"apps/audit/tasks.py:447 sync_glitchtip_issues": 80.0}
        cands = _select_hotspots(totals, threshold_pct=5.0)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].file_hint, "apps/audit/tasks.py")

    def test_select_hotspots_handles_zero_total(self):
        # Empty dict shouldn't divide-by-zero.
        cands = _select_hotspots({}, threshold_pct=5.0)
        self.assertEqual(cands, [])


class PyroscopeHotspotIntegrationTests(TestCase):
    """End-to-end test that mocks the Pyroscope HTTP API and asserts
    AutoIssue rows materialize with kind='hotspot'-style fingerprints
    (prefixed so they don't collide with regression rows)."""

    def test_pick_pyroscope_hotspots_skips_when_server_unset(self):
        with mock.patch.dict("os.environ", {"PYROSCOPE_SERVER_ADDRESS": ""}, clear=False):
            result = pick_pyroscope_hotspots(server="")
        self.assertEqual(result, {"status": "skipped", "reason": "missing_pyroscope_server"})

    @mock.patch(
        "apps.auto_issues.services.pyroscope_picker._query_pyroscope_render"
    )
    def test_pick_pyroscope_hotspots_promotes_to_autoissue(self, mock_render):
        # Stub a flamegraph where one function dominates (80% of total).
        mock_render.return_value = {
            "flamebearer": {
                "names": ["root", "hot_function", "cold_function"],
                "levels": [
                    [0, 100, 0, 0],
                    [0, 80, 80, 1, 0, 20, 20, 2],
                ],
            },
        }
        result = pick_pyroscope_hotspots(
            server="http://pyroscope:4040",
            applications=("xf-linker-backend",),
            limit=5,
        )
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["promoted"], 1)
        # AutoIssue row should be present with the hotspot prefix.
        rows = AutoIssue.objects.filter(source=AutoIssue.SOURCE_PYROSCOPE)
        self.assertGreaterEqual(rows.count(), 1)
        # Title should mention the percent share.
        self.assertTrue(any("burning" in r.title.lower() for r in rows))
