"""Tests for ``apps.core.services.cpp_fallback_warning`` (Phase 4.14).

These cases pin the watcher's emit-on-transition contract so the
specific bug shipped + caught in flight (123 spurious "persists"
events on the second tick after baseline) cannot regress.

The tests use ``@patch`` to inject a fixed list of fake extension
statuses + a controlled ``timezone.now()`` so the persists / recovery
windows are exercised deterministically — no sleeping, no real
extension imports.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone as _tz
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import AppSetting
from apps.core.services import cpp_fallback_warning as cfw


def _fake_status(
    module: str,
    runtime_path: str,
    *,
    label: str | None = None,
    critical: bool = False,
    fallback_reason: str = "",
) -> dict:
    """Build one fake _native_module_runtime_status() row."""
    return {
        "module": module,
        "label": label or f"{module} kernel",
        "critical": critical,
        "compiled": runtime_path == "cpp",
        "importable": runtime_path == "cpp",
        "callable_present": runtime_path == "cpp",
        "state": "healthy" if runtime_path == "cpp" else "degraded",
        "runtime_path": runtime_path,
        "fallback_active": runtime_path != "cpp",
        "fallback_reason": fallback_reason,
        "origin": "" if runtime_path != "cpp" else "/app/extensions/scoring.so",
    }


def _read_state(module: str) -> dict | None:
    """Helper: read the persisted JSON for *module* directly from AppSetting."""
    row = AppSetting.objects.filter(key=f"cpp_fallback.{module}.last_state").first()
    return json.loads(row.value) if row and row.value else None


class CheckAndEmitFallbackEventsTests(TestCase):
    """End-to-end transition / baseline / persists path coverage.

    Each test patches both the upstream native-status reader AND the
    ops_feed.emit so we measure the watcher's behaviour in isolation
    from real extension imports + the real Operations Feed table.
    """

    def setUp(self) -> None:
        # Wipe any state left by other tests so each method starts from
        # a clean slate. The watcher writes one row per extension via
        # update_or_create — leaking rows would make the "first observation"
        # branch silently take a different path.
        AppSetting.objects.filter(key__startswith="cpp_fallback.").delete()

    # ── Baseline: first observation never emits ─────────────────

    def test_first_observation_persists_baseline_silently(self) -> None:
        """A fresh extension should be persisted with no event emitted —
        operator doesn't need a notification just because the watcher
        started up."""
        statuses = [_fake_status("scoring", "python")]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            with patch.object(cfw, "_emit_event") as mock_emit:
                events = cfw.check_and_emit_fallback_events()
        self.assertEqual(events, [])
        self.assertEqual(mock_emit.call_count, 0)
        # State row was persisted.
        state = _read_state("scoring")
        self.assertIsNotNone(state)
        self.assertEqual(state["runtime_path"], "python")

    def test_no_change_after_baseline_does_not_emit(self) -> None:
        """The bug that motivated the test suite: round 2 with the same
        state used to emit one persists-event per extension. Now: zero."""
        statuses = [_fake_status("scoring", "python")]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            with patch.object(cfw, "_emit_event") as mock_emit:
                cfw.check_and_emit_fallback_events()  # baseline
                events = cfw.check_and_emit_fallback_events()  # no change
        self.assertEqual(events, [])
        self.assertEqual(mock_emit.call_count, 0)

    # ── cpp → python (fallback started) ─────────────────────────

    def test_cpp_to_python_emits_started_event(self) -> None:
        """Simulating the canonical bad-news case."""
        # Pre-seed the persisted state as cpp.
        AppSetting.objects.create(
            key="cpp_fallback.scoring.last_state",
            value=json.dumps(
                {
                    "runtime_path": "cpp",
                    "since_iso": "2026-05-04T17:00:00+00:00",
                }
            ),
        )
        statuses = [_fake_status("scoring", "python", critical=True)]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            with patch.object(cfw, "_emit_event") as mock_emit:
                events = cfw.check_and_emit_fallback_events()
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.event_type, "started")
        self.assertEqual(ev.runtime_path, "python")
        self.assertEqual(ev.severity, "high")  # critical=True → high
        self.assertIn("Python fallback", ev.plain_english)
        self.assertEqual(mock_emit.call_count, 1)
        # New baseline persisted.
        state = _read_state("scoring")
        self.assertEqual(state["runtime_path"], "python")

    def test_cpp_to_python_non_critical_uses_warning_severity(self) -> None:
        AppSetting.objects.create(
            key="cpp_fallback.feedrerank.last_state",
            value=json.dumps(
                {
                    "runtime_path": "cpp",
                    "since_iso": "2026-05-04T17:00:00+00:00",
                }
            ),
        )
        statuses = [_fake_status("feedrerank", "python", critical=False)]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            with patch.object(cfw, "_emit_event"):
                events = cfw.check_and_emit_fallback_events()
        self.assertEqual(events[0].severity, "warning")

    # ── python → cpp (recovered) ────────────────────────────────

    def test_python_to_cpp_emits_recovered_with_duration(self) -> None:
        """Recovery event should report the human-readable duration."""
        AppSetting.objects.create(
            key="cpp_fallback.simsearch.last_state",
            value=json.dumps(
                {
                    "runtime_path": "python",
                    "since_iso": "2025-01-01T00:00:00+00:00",
                }
            ),
        )
        statuses = [_fake_status("simsearch", "cpp")]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            with patch.object(cfw, "_emit_event"):
                events = cfw.check_and_emit_fallback_events()
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.event_type, "recovered")
        self.assertEqual(ev.runtime_path, "cpp")
        self.assertEqual(ev.severity, "info")
        # Duration text should include "after" + a unit suffix
        self.assertIn("after", ev.plain_english)
        self.assertGreater(ev.duration_seconds, 0)

    # ── persists branch (the bug-fix coverage) ──────────────────

    def test_persists_event_does_not_fire_on_fresh_fallback(self) -> None:
        """The fix: a fallback younger than the reminder interval gets
        ZERO persists events. (Prior to the fix, baseline + Round 2 would
        emit 1 persists per extension.)"""
        # Persisted state: was python 30 seconds ago — well under the
        # 1 h reminder interval.
        recent = (datetime.now(_tz.utc) - timedelta(seconds=30)).isoformat()
        AppSetting.objects.create(
            key="cpp_fallback.scoring.last_state",
            value=json.dumps({"runtime_path": "python", "since_iso": recent}),
        )
        statuses = [_fake_status("scoring", "python")]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            with patch.object(cfw, "_emit_event") as mock_emit:
                events = cfw.check_and_emit_fallback_events()
        self.assertEqual(events, [])
        self.assertEqual(mock_emit.call_count, 0)

    def test_persists_event_fires_when_fallback_older_than_interval(self) -> None:
        """A fallback older than the 1 h reminder interval should emit
        exactly one persists event per call."""
        long_ago = (
            datetime.now(_tz.utc)
            - timedelta(seconds=cfw._PERSIST_REMINDER_INTERVAL_SECONDS + 60)
        ).isoformat()
        AppSetting.objects.create(
            key="cpp_fallback.scoring.last_state",
            value=json.dumps({"runtime_path": "python", "since_iso": long_ago}),
        )
        statuses = [_fake_status("scoring", "python", critical=True)]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            with patch.object(cfw, "_emit_event"):
                events = cfw.check_and_emit_fallback_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "persists")
        self.assertEqual(events[0].severity, "high")

    def test_persists_event_does_not_double_fire(self) -> None:
        """Once we've warned, the 1 h cooldown should suppress the next call."""
        long_ago = (
            datetime.now(_tz.utc)
            - timedelta(seconds=cfw._PERSIST_REMINDER_INTERVAL_SECONDS + 60)
        ).isoformat()
        AppSetting.objects.create(
            key="cpp_fallback.scoring.last_state",
            value=json.dumps({"runtime_path": "python", "since_iso": long_ago}),
        )
        statuses = [_fake_status("scoring", "python")]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            with patch.object(cfw, "_emit_event"):
                cfw.check_and_emit_fallback_events()  # Round 1 emits persists
                events = cfw.check_and_emit_fallback_events()  # Round 2 must not
        self.assertEqual(events, [])

    # ── empty / defensive paths ─────────────────────────────────

    def test_empty_status_list_returns_empty(self) -> None:
        with patch.object(cfw, "_read_native_runtime_status", return_value=[]):
            self.assertEqual(cfw.check_and_emit_fallback_events(), [])

    def test_status_without_module_is_skipped(self) -> None:
        with patch.object(
            cfw, "_read_native_runtime_status", return_value=[{"module": ""}]
        ):
            self.assertEqual(cfw.check_and_emit_fallback_events(), [])


class GetCurrentFallbackStatusTests(TestCase):
    """The dashboard-chip API surface."""

    def setUp(self) -> None:
        AppSetting.objects.filter(key__startswith="cpp_fallback.").delete()

    def test_all_cpp_returns_zero_fallbacks(self) -> None:
        statuses = [_fake_status("scoring", "cpp"), _fake_status("simsearch", "cpp")]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            snap = cfw.get_current_fallback_status()
        self.assertEqual(snap.total_extensions, 2)
        self.assertEqual(snap.on_cpp, 2)
        self.assertEqual(snap.on_python_fallback, 0)
        self.assertEqual(snap.fallbacks, [])

    def test_some_python_returns_count_and_list(self) -> None:
        statuses = [
            _fake_status("scoring", "cpp"),
            _fake_status("simsearch", "python", critical=True),
        ]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            snap = cfw.get_current_fallback_status()
        self.assertEqual(snap.on_cpp, 1)
        self.assertEqual(snap.on_python_fallback, 1)
        self.assertEqual(len(snap.fallbacks), 1)
        self.assertEqual(snap.fallbacks[0]["module"], "simsearch")
        self.assertTrue(snap.fallbacks[0]["critical"])


class FormatDashboardBannerTests(TestCase):
    def setUp(self) -> None:
        AppSetting.objects.filter(key__startswith="cpp_fallback.").delete()

    def test_all_cpp_returns_empty_banner(self) -> None:
        statuses = [_fake_status("scoring", "cpp")]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            self.assertEqual(cfw.format_dashboard_banner(), "")

    def test_single_fallback_includes_label(self) -> None:
        statuses = [_fake_status("scoring", "python", label="Composite scoring")]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            banner = cfw.format_dashboard_banner()
        self.assertIn("Composite scoring", banner)
        self.assertIn("Python fallback", banner)

    def test_multiple_fallbacks_includes_count(self) -> None:
        statuses = [
            _fake_status("scoring", "python"),
            _fake_status("simsearch", "python"),
            _fake_status("pagerank", "cpp"),
        ]
        with patch.object(cfw, "_read_native_runtime_status", return_value=statuses):
            banner = cfw.format_dashboard_banner()
        self.assertIn("2 of 3", banner)


class FormatDurationTests(TestCase):
    """Helper micro-tests; pure function so SimpleTestCase would do but
    keep TestCase for consistency with the rest of the file."""

    def test_seconds(self) -> None:
        self.assertEqual(cfw._format_duration(0), "0s")
        self.assertEqual(cfw._format_duration(45), "45s")

    def test_minutes(self) -> None:
        self.assertEqual(cfw._format_duration(125), "2m 5s")

    def test_hours(self) -> None:
        self.assertEqual(cfw._format_duration(3661), "1h 1m")

    def test_days(self) -> None:
        self.assertEqual(cfw._format_duration(90061), "1d 1h")

    def test_negative_clamps_to_zero(self) -> None:
        # Defensive: a clock skew could feed a negative duration; output
        # should not contain "-1s" or similar nonsense.
        self.assertEqual(cfw._format_duration(-10), "0s")
