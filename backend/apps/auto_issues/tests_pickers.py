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

import requests
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
    _gather_regressions,
    _query_pyroscope_render,
    _query_pyroscope_diff,
    _score_regressions,
    _select_hotspots,
    _severity_for,
    _split_profiler_tooling_hotspots,
    _stable_fingerprint,
    _upsert_pyroscope_row,
    pick_pyroscope_hotspots,
    pick_pyroscope_regressions,
)
from apps.auto_issues.tasks import close_stale_issues, pick_daily_glitchtip_issues


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
    def setUp(self):
        ErrorLog.objects.filter(source=ErrorLog.SOURCE_GLITCHTIP).delete()
        AutoIssue.objects.filter(source=AutoIssue.SOURCE_GLITCHTIP).delete()

    def test_empty_mirror_returns_zero_promoted(self):
        result = pick_glitchtip_issues()
        self.assertEqual(result, {"status": "ok", "fetched": 0, "promoted": 0})
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_GLITCHTIP).count(),
            0,
        )

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
        rows = AutoIssue.objects.filter(source=AutoIssue.SOURCE_GLITCHTIP)
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertIsNotNone(row)
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


class GlitchtipTaskTests(SimpleTestCase):
    @mock.patch("apps.auto_issues.services.glitchtip_picker.pick_glitchtip_issues")
    @mock.patch("apps.audit.tasks.sync_glitchtip_issues")
    def test_daily_task_syncs_mirror_before_picking(
        self,
        mock_sync,
        mock_pick,
    ):
        calls = []
        mock_sync.side_effect = lambda: calls.append("sync") or {"status": "ok"}
        mock_pick.side_effect = lambda: calls.append("pick") or {
            "status": "ok",
            "promoted": 1,
        }

        result = pick_daily_glitchtip_issues()

        self.assertEqual(calls, ["sync", "pick"])
        self.assertEqual(result["glitchtip_sync"]["status"], "ok")
        self.assertEqual(result["glitchtip_picker"]["promoted"], 1)


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

    def test_extract_function_totals_skips_malformed_nodes(self):
        side = {
            "flamebearer": {
                "names": ["root", "valid"],
                "levels": [[0, 100], [0, 10, "bad", 1, 0, 20, 20, 1]],
            }
        }
        self.assertEqual(_extract_function_totals(side), {"valid": 20.0})

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

    def test_compare_sides_skips_growth_below_ratio_threshold(self):
        left = {"steady": 1_000_000_000}
        right = {"steady": 1_500_000_000}
        self.assertEqual(_compare_sides(left, right), [])

    def test_compare_sides_extracts_file_hint(self):
        left = {"apps/pipeline/scoring.py:20 score": 1_000_000_000}
        right = {"apps/pipeline/scoring.py:20 score": 3_000_000_000}
        cands = _compare_sides(left, right)
        self.assertEqual(cands[0].file_hint, "apps/pipeline/scoring.py")

    def test_severity_for_regression_ratio(self):
        low = PyroscopeCandidate("fn", "", 10.0, 11.0, 11.0)
        medium = PyroscopeCandidate("fn", "", 10.0, 25.0, 25.0)
        high = PyroscopeCandidate("fn", "", 10.0, 60.0, 60.0)
        self.assertEqual(_severity_for(low), AutoIssue.SEVERITY_LOW)
        self.assertEqual(_severity_for(medium), AutoIssue.SEVERITY_MEDIUM)
        self.assertEqual(_severity_for(high), AutoIssue.SEVERITY_HIGH)

    def test_stable_fingerprint_is_deterministic(self):
        a = _stable_fingerprint("foo.bar", "/app/foo.py")
        b = _stable_fingerprint("foo.bar", "/app/foo.py")
        c = _stable_fingerprint("foo.bar", "/app/different.py")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class PyroscopePickerTopLevelTests(SimpleTestCase):
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

    @mock.patch("apps.auto_issues.services.pyroscope_picker.requests.get")
    def test_diff_request_uses_left_and_right_queries(self, mock_get):
        response = mock.Mock()
        response.json.return_value = {"flamebearer": {"names": [], "levels": []}}
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        _query_pyroscope_diff(
            "http://pyroscope:4040",
            "xf-linker-backend",
            until=1_779_098_400,
        )

        params = mock_get.call_args.kwargs["params"]
        self.assertIn("leftQuery", params)
        self.assertIn("rightQuery", params)
        self.assertNotIn("query", params)
        self.assertEqual(params["leftQuery"], params["rightQuery"])

    @mock.patch("apps.auto_issues.services.pyroscope_picker.requests.get")
    def test_render_request_keeps_single_query_field(self, mock_get):
        response = mock.Mock()
        response.json.return_value = {"flamebearer": {"names": [], "levels": []}}
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        _query_pyroscope_render(
            "http://pyroscope:4040",
            "xf-linker-backend",
            until=1_779_098_400,
            span_seconds=3600,
        )

        params = mock_get.call_args.kwargs["params"]
        self.assertIn("query", params)
        self.assertNotIn("leftQuery", params)
        self.assertNotIn("rightQuery", params)

    @mock.patch("apps.auto_issues.services.pyroscope_picker.requests.get")
    def test_diff_request_failure_returns_empty_dict(self, mock_get):
        mock_get.side_effect = requests.RequestException("boom")
        result = _query_pyroscope_diff(
            "http://pyroscope:4040",
            "xf-linker-backend",
            until=1_779_098_400,
        )
        self.assertEqual(result, {})

    @mock.patch("apps.auto_issues.services.pyroscope_picker._query_pyroscope_diff")
    def test_gather_regressions_skips_empty_diff(self, mock_diff):
        mock_diff.side_effect = [
            {},
            {
                "left": {"flamebearer": {"names": ["root"], "levels": []}},
                "right": {"flamebearer": {"names": ["root"], "levels": []}},
            },
        ]
        self.assertEqual(
            _gather_regressions("http://pyroscope:4040", ("a", "b")),
            [],
        )


class PyroscopeRegressionUpsertTests(TestCase):
    def setUp(self):
        AutoIssue.objects.filter(source=AutoIssue.SOURCE_PYROSCOPE).delete()

    def test_upsert_pyroscope_row_creates_autoissue(self):
        candidate = PyroscopeCandidate(
            function_name="apps/pipeline/scoring.py:20 score",
            file_hint="apps/pipeline/scoring.py",
            left_self_ns=1_000_000_000,
            right_self_ns=3_000_000_000,
            right_total_ns=6_000_000_000,
        )

        outcome = _upsert_pyroscope_row(0.75, candidate, dj_timezone.now())

        self.assertEqual(outcome, "created")
        row = AutoIssue.objects.get(source=AutoIssue.SOURCE_PYROSCOPE)
        self.assertIn("regressed 3.0x", row.title)
        self.assertEqual(row.affected_files, ["apps/pipeline/scoring.py"])

    def test_score_regressions_sorts_descending(self):
        low = PyroscopeCandidate("low", "", 1_000_000_000, 2_100_000_000, 10)
        high = PyroscopeCandidate("high", "", 1_000_000_000, 5_500_000_000, 10)
        scored = _score_regressions([low, high])
        self.assertEqual(scored[0][1].function_name, "high")

    @mock.patch("apps.auto_issues.services.pyroscope_picker._gather_regressions")
    def test_pick_pyroscope_regressions_promotes_candidates(self, mock_gather):
        mock_gather.return_value = [
            PyroscopeCandidate("hot", "", 1_000_000_000, 3_000_000_000, 3_000_000_000)
        ]

        result = pick_pyroscope_regressions(
            server="http://pyroscope:4040",
            applications=("xf-linker-backend",),
            limit=1,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["regressions_found"], 1)
        self.assertEqual(result["promoted"], 1)
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_PYROSCOPE).count(),
            1,
        )


class CloseStaleIssuesTaskTests(TestCase):
    def test_closes_idle_low_score_rows(self):
        AutoIssue.objects.filter(
            status__in=(AutoIssue.STATUS_OPEN, AutoIssue.STATUS_PICKED)
        ).update(priority_score=1.0)
        prefix = f"close-stale-{id(self)}"
        # Stale + low score → should close.
        old = AutoIssue.objects.create(
            source="agent",
            external_id=f"{prefix}-low",
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
            external_id=f"{prefix}-recent",
            fingerprint="y",
            title="Recent",
            severity="low",
            status=AutoIssue.STATUS_OPEN,
            priority_score=0.1,
        )
        # High-score idle → should NOT close.
        old_high = AutoIssue.objects.create(
            source="agent",
            external_id=f"{prefix}-high",
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

    def test_split_profiler_tooling_hotspots_keeps_app_findings(self):
        cands = [
            PyroscopeCandidate(
                function_name="Scheduler.make_sampler.<locals>._sample_stack",
                file_hint="",
                left_self_ns=0.0,
                right_self_ns=80.0,
                right_total_ns=100.0,
            ),
            PyroscopeCandidate(
                function_name="apps.pipeline.services.score_matches",
                file_hint="apps/pipeline/services.py",
                left_self_ns=0.0,
                right_self_ns=20.0,
                right_total_ns=100.0,
            ),
        ]

        app_cands, tooling_cands = _split_profiler_tooling_hotspots(cands)

        self.assertEqual([c.function_name for c in app_cands], [
            "apps.pipeline.services.score_matches",
        ])
        self.assertEqual([c.function_name for c in tooling_cands], [
            "Scheduler.make_sampler.<locals>._sample_stack",
        ])


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

    @mock.patch(
        "apps.auto_issues.services.pyroscope_picker._query_pyroscope_render"
    )
    def test_pick_pyroscope_hotspots_groups_profiler_tooling(self, mock_render):
        mock_render.return_value = {
            "flamebearer": {
                "names": [
                    "root",
                    "Scheduler.make_sampler.<locals>._sample_stack",
                    "sleep",
                    "encode_metrics",
                ],
                "levels": [
                    [0, 300, 0, 0],
                    [0, 100, 100, 1, 0, 100, 100, 2, 0, 100, 100, 3],
                ],
            },
        }

        result = pick_pyroscope_hotspots(
            server="http://pyroscope:4040",
            applications=("xf-linker-backend",),
            limit=5,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["app_hotspots_found"], 0)
        self.assertEqual(result["profiler_tooling_found"], 3)
        self.assertEqual(result["profiler_tooling_promoted"], 1)
        rows = AutoIssue.objects.filter(
            source=AutoIssue.SOURCE_PYROSCOPE,
            title="Pyroscope: profiler-tooling overhead is above threshold",
        )
        self.assertEqual(rows.count(), 1)
        row = rows.get()
        self.assertIn("profiler-tooling", row.title)
        self.assertEqual(row.category.key, "tooling")
        self.assertNotIn("burning", row.title.lower())
