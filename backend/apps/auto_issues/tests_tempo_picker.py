"""Tests for `services.tempo_picker`.

Mirrors the loki/faro picker test structure — pure functions tested
directly, HTTP-touching pieces mocked. The Tempo TraceQL endpoint is
mocked via ``_tempo_search`` so tests stay hermetic.

Added 2026-05-11 per plan
``~/.claude/plans/objective-deploy-and-integrate-zany-bee.md`` Stream 6.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.tempo_picker import (
    TempoCandidate,
    _stable_fingerprint,
    pick_tempo_error_spans,
    pick_tempo_slow_spans,
)


def _trace(name: str, service: str, duration_ms: float = 0.0) -> dict:
    """Build a fake Tempo /api/search row."""
    return {
        "rootTraceName": name,
        "rootServiceName": service,
        "durationMs": duration_ms,
    }


class StableFingerprintTests(SimpleTestCase):
    def test_includes_prefix(self):
        fp = _stable_fingerprint("tempo:slow", "backend::sql_query")
        self.assertTrue(fp.startswith("tempo:slow::"))

    def test_deterministic(self):
        a = _stable_fingerprint("tempo:slow", "backend::sql_query")
        b = _stable_fingerprint("tempo:slow", "backend::sql_query")
        self.assertEqual(a, b)

    def test_disjoint_prefixes_disjoint_fingerprints(self):
        a = _stable_fingerprint("tempo:slow", "ref")
        b = _stable_fingerprint("tempo:err", "ref")
        self.assertNotEqual(a, b)

    def test_different_service_or_name_gets_different_fingerprint(self):
        a = _stable_fingerprint("tempo:slow", "backend::sql_query")
        b = _stable_fingerprint("tempo:slow", "frontend::sql_query")
        self.assertNotEqual(a, b)


class TempoSlowSpanIntegrationTests(TestCase):
    """End-to-end: mock Tempo TraceQL, assert AutoIssue rows materialize."""

    @mock.patch("apps.auto_issues.services.tempo_picker._tempo_search")
    def test_pick_slow_spans_promotes_to_autoissue(self, mock_search):
        # 3 slow traces for the same (span, service).
        mock_search.return_value = [
            _trace("GET /api/dashboard", "xf-linker-backend", 1500.0),
            _trace("GET /api/dashboard", "xf-linker-backend", 2400.0),
            _trace("GET /api/dashboard", "xf-linker-backend", 1100.0),
        ]
        result = pick_tempo_slow_spans(limit=5)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["slow_spans_found"], 1)
        self.assertGreaterEqual(result["promoted"], 1)
        rows = AutoIssue.objects.filter(
            source=AutoIssue.SOURCE_TEMPO,
            title__icontains="slow_span",
        )
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        # Peak duration captured.
        self.assertIn("2400", row.title)

    @mock.patch("apps.auto_issues.services.tempo_picker._tempo_search")
    def test_no_traces_no_ops(self, mock_search):
        mock_search.return_value = []
        result = pick_tempo_slow_spans(limit=5)
        self.assertEqual(result["slow_spans_found"], 0)
        self.assertEqual(result["promoted"], 0)
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_TEMPO).count(), 0
        )

    @mock.patch("apps.auto_issues.services.tempo_picker._tempo_search")
    def test_separate_span_names_count_separately(self, mock_search):
        mock_search.return_value = [
            _trace("GET /api/dashboard", "backend", 1500.0),
            _trace("GET /api/dashboard", "backend", 1600.0),
            _trace("POST /api/search", "backend", 2000.0),
        ]
        result = pick_tempo_slow_spans(limit=5)
        # Two distinct groups -> two candidates.
        self.assertEqual(result["slow_spans_found"], 2)
        self.assertEqual(
            AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_TEMPO,
                title__icontains="slow_span",
            ).count(),
            2,
        )

    @mock.patch("apps.auto_issues.services.tempo_picker._tempo_search")
    def test_very_slow_span_gets_high_severity(self, mock_search):
        # 8000 ms is well over the 5000 ms threshold for HIGH severity.
        mock_search.return_value = [
            _trace("GET /api/slow", "backend", 8000.0),
        ]
        pick_tempo_slow_spans(limit=5)
        row = AutoIssue.objects.get(
            source=AutoIssue.SOURCE_TEMPO,
            title__icontains="slow_span",
        )
        self.assertEqual(row.severity, AutoIssue.SEVERITY_HIGH)


class TempoErrorSpanIntegrationTests(TestCase):

    @mock.patch("apps.auto_issues.services.tempo_picker._tempo_search")
    def test_error_spans_promote_when_count_above_threshold(self, mock_search):
        # 5 error spans for one (name, service) — above default 3.
        mock_search.return_value = [
            _trace("POST /api/save", "backend", 0.0) for _ in range(5)
        ]
        result = pick_tempo_error_spans(limit=5)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["error_spans_found"], 1)
        self.assertGreaterEqual(result["promoted"], 1)
        self.assertEqual(
            AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_TEMPO,
                title__icontains="error_span",
            ).count(),
            1,
        )

    @mock.patch("apps.auto_issues.services.tempo_picker._tempo_search")
    def test_error_spans_below_threshold_skipped(self, mock_search):
        # Only 2 error spans — below default min_count of 3.
        mock_search.return_value = [
            _trace("POST /api/save", "backend", 0.0) for _ in range(2)
        ]
        result = pick_tempo_error_spans(limit=5)
        self.assertEqual(result["error_spans_found"], 0)
        self.assertEqual(result["promoted"], 0)

    @mock.patch("apps.auto_issues.services.tempo_picker._tempo_search")
    def test_many_error_spans_get_high_severity(self, mock_search):
        # 15 errors -> HIGH severity per the picker rule.
        mock_search.return_value = [
            _trace("POST /api/save", "backend", 0.0) for _ in range(15)
        ]
        pick_tempo_error_spans(limit=5)
        row = AutoIssue.objects.get(
            source=AutoIssue.SOURCE_TEMPO,
            title__icontains="error_span",
        )
        self.assertEqual(row.severity, AutoIssue.SEVERITY_HIGH)


class TempoPickerScheduleTests(SimpleTestCase):
    """Tempo picker fires at :25 and :55 — last in the picker chain."""

    def test_schedule_runs_every_30_minutes(self):
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        entry = CELERY_BEAT_SCHEDULE.get("auto-issues-tempo-pick")
        self.assertIsNotNone(entry, "Tempo picker schedule entry missing")
        cron = entry["schedule"]
        self.assertIn(25, cron.minute)
        self.assertIn(55, cron.minute)
        self.assertEqual(len(cron.hour), 13)

    def test_schedule_staggered_after_faro(self):
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        faro = CELERY_BEAT_SCHEDULE["auto-issues-faro-pick"]["schedule"]
        tempo = CELERY_BEAT_SCHEDULE["auto-issues-tempo-pick"]["schedule"]
        for faro_min in faro.minute:
            self.assertIn(
                (faro_min + 5) % 60, tempo.minute,
                f"Tempo should fire 5 min after Faro at :{faro_min:02d}",
            )
