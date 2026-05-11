"""Tests for `services.faro_picker`.

Mirrors the loki_picker test structure — pure functions tested directly,
HTTP-touching pieces mocked. Faro events live in Loki streams labelled
``source="faro"`` so the picker queries the same Loki HTTP endpoint as
the loki picker; mocking ``_fetch_faro_lines`` keeps tests hermetic.

Added 2026-05-11 per plan
``~/.claude/plans/objective-deploy-and-integrate-zany-bee.md`` Stream 5.
"""

from __future__ import annotations

import json
from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.faro_picker import (
    FaroCandidate,
    _normalize_line,
    _stable_fingerprint,
    pick_faro_error_clusters,
    pick_faro_webvital_breaches,
)


def _faro_error_event(message: str, url: str = "/dashboard") -> str:
    return json.dumps({
        "type": "exception",
        "message": message,
        "url": url,
    })


def _faro_measurement(name: str, value: float, url: str = "/dashboard") -> str:
    return json.dumps({
        "type": "measurement",
        "name": name,
        "value": value,
        "url": url,
    })


class NormalizationTests(SimpleTestCase):
    """Faro picker reuses the loki picker's normalize regex set — confirm
    the wrapper picks them up."""

    def test_strips_iso_timestamp(self):
        out = _normalize_line("2026-05-10T08:48:21.488Z TypeError: foo")
        self.assertNotIn("2026-05-10", out)
        self.assertIn("TypeError: foo", out)

    def test_strips_uuid(self):
        out = _normalize_line(
            "request 12345678-1234-1234-1234-1234567890ab failed"
        )
        self.assertIn("<UUID>", out)
        self.assertNotIn("12345678-1234", out)

    def test_two_similar_errors_share_normalized_form(self):
        a = _normalize_line(
            "2026-05-10T08:00:00Z TypeError: cannot read 'foo' at line 12"
        )
        b = _normalize_line(
            "2026-05-10T09:30:00Z TypeError: cannot read 'foo' at line 12"
        )
        self.assertEqual(a, b)


class StableFingerprintTests(SimpleTestCase):
    def test_includes_prefix(self):
        fp = _stable_fingerprint("faro:err", "TypeError: x is undefined")
        self.assertTrue(fp.startswith("faro:err::"))

    def test_deterministic(self):
        a = _stable_fingerprint("faro:err", "TypeError: x is undefined")
        b = _stable_fingerprint("faro:err", "TypeError: x is undefined")
        self.assertEqual(a, b)

    def test_disjoint_prefixes_disjoint_fingerprints(self):
        a = _stable_fingerprint("faro:err", "ref")
        b = _stable_fingerprint("faro:webvital", "ref")
        self.assertNotEqual(a, b)


class FaroErrorClusterIntegrationTests(TestCase):
    """End-to-end: mock Loki HTTP, assert AutoIssue rows materialize."""

    @mock.patch("apps.auto_issues.services.faro_picker._fetch_faro_lines")
    def test_pick_faro_error_clusters_promotes_to_autoissue(self, mock_fetch):
        # 8 occurrences of one normalized message — above default min_count of 5.
        mock_fetch.return_value = [
            _faro_error_event("TypeError: cannot read 'foo'")
            for _ in range(8)
        ]
        result = pick_faro_error_clusters(limit=5)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["clusters_found"], 1)
        self.assertGreaterEqual(result["promoted"], 1)
        rows = AutoIssue.objects.filter(source=AutoIssue.SOURCE_FARO)
        self.assertGreaterEqual(rows.count(), 1)
        self.assertTrue(any("error_cluster" in r.title for r in rows))

    @mock.patch("apps.auto_issues.services.faro_picker._fetch_faro_lines")
    def test_below_threshold_does_not_promote(self, mock_fetch):
        # Only 2 occurrences — below default min_count of 5.
        mock_fetch.return_value = [
            _faro_error_event("TypeError: cannot read 'foo'")
            for _ in range(2)
        ]
        result = pick_faro_error_clusters(limit=5)
        self.assertEqual(result["clusters_found"], 0)
        self.assertEqual(result["promoted"], 0)
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_FARO).count(), 0
        )

    @mock.patch("apps.auto_issues.services.faro_picker._fetch_faro_lines")
    def test_non_json_lines_fall_back_to_raw_line(self, mock_fetch):
        # 6 plain-text error lines — fall back to using the raw line.
        mock_fetch.return_value = [
            "Uncaught ReferenceError: foo is not defined"
            for _ in range(6)
        ]
        result = pick_faro_error_clusters(limit=5)
        self.assertEqual(result["clusters_found"], 1)
        self.assertGreaterEqual(result["promoted"], 1)

    @mock.patch("apps.auto_issues.services.faro_picker._fetch_faro_lines")
    def test_no_data_no_ops(self, mock_fetch):
        mock_fetch.return_value = []
        result = pick_faro_error_clusters(limit=5)
        self.assertEqual(result["clusters_found"], 0)
        self.assertEqual(result["promoted"], 0)


class FaroWebVitalBreachIntegrationTests(TestCase):

    @mock.patch("apps.auto_issues.services.faro_picker._fetch_faro_lines")
    def test_lcp_breaches_promote_when_over_threshold(self, mock_fetch):
        # 12 LCP samples at 3000 ms on /dashboard — above default 2500 ms.
        mock_fetch.return_value = [
            _faro_measurement("largest_contentful_paint", 3000.0)
            for _ in range(12)
        ]
        result = pick_faro_webvital_breaches(limit=5)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["breaches_found"], 1)
        self.assertGreaterEqual(result["promoted"], 1)
        self.assertEqual(
            AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_FARO,
                title__icontains="webvital_breach",
            ).count(),
            1,
        )

    @mock.patch("apps.auto_issues.services.faro_picker._fetch_faro_lines")
    def test_below_lcp_threshold_does_not_promote(self, mock_fetch):
        # 12 LCP samples but all under 2500 ms — no breach.
        mock_fetch.return_value = [
            _faro_measurement("largest_contentful_paint", 1800.0)
            for _ in range(12)
        ]
        result = pick_faro_webvital_breaches(limit=5)
        self.assertEqual(result["breaches_found"], 0)
        self.assertEqual(result["promoted"], 0)

    @mock.patch("apps.auto_issues.services.faro_picker._fetch_faro_lines")
    def test_below_sample_count_does_not_promote(self, mock_fetch):
        # Only 5 LCP samples over threshold — below default 10 sessions.
        mock_fetch.return_value = [
            _faro_measurement("largest_contentful_paint", 3000.0)
            for _ in range(5)
        ]
        result = pick_faro_webvital_breaches(limit=5)
        self.assertEqual(result["breaches_found"], 0)

    @mock.patch("apps.auto_issues.services.faro_picker._fetch_faro_lines")
    def test_unknown_metric_name_ignored(self, mock_fetch):
        mock_fetch.return_value = [
            _faro_measurement("some_metric_we_dont_track", 9999.0)
            for _ in range(20)
        ]
        result = pick_faro_webvital_breaches(limit=5)
        self.assertEqual(result["breaches_found"], 0)

    @mock.patch("apps.auto_issues.services.faro_picker._fetch_faro_lines")
    def test_separate_routes_count_separately(self, mock_fetch):
        # 12 breaches on /a (promotes), 5 on /b (doesn't).
        mock_fetch.return_value = (
            [_faro_measurement("largest_contentful_paint", 3000.0, url="/a")
             for _ in range(12)]
            + [_faro_measurement("largest_contentful_paint", 3000.0, url="/b")
               for _ in range(5)]
        )
        result = pick_faro_webvital_breaches(limit=5)
        self.assertEqual(result["breaches_found"], 1)


class FaroPickerScheduleTests(SimpleTestCase):
    """The picker fires twice per hour at :20 and :50 within the active
    laptop window — staggered after pyroscope (:10/:40) and before loki
    (:15/:45 — wait, faro at :20 is AFTER loki at :15). Actually faro
    sits between pyroscope :10/:40 and loki :15/:45 — no, the plan says
    faro at :20/:50 (slots between pyroscope :10/:40 and loki :15/:45?
    No — :20 > :15. The plan's chain order ended up:
      glitchtip :05/:35
      pyroscope :10/:40
      loki      :15/:45
      faro      :20/:50
      tempo     :25/:55
    So faro fires AFTER loki, 5 min later. That's the correct stagger
    so the pickers don't fight Postgres."""

    def test_schedule_runs_every_30_minutes(self):
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        entry = CELERY_BEAT_SCHEDULE.get("auto-issues-faro-pick")
        self.assertIsNotNone(entry, "Faro picker schedule entry missing")
        cron = entry["schedule"]
        self.assertIn(20, cron.minute)
        self.assertIn(50, cron.minute)
        self.assertEqual(len(cron.hour), 13)

    def test_schedule_staggered_after_loki(self):
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        loki = CELERY_BEAT_SCHEDULE["auto-issues-loki-pick"]["schedule"]
        faro = CELERY_BEAT_SCHEDULE["auto-issues-faro-pick"]["schedule"]
        for loki_min in loki.minute:
            self.assertIn(
                (loki_min + 5) % 60, faro.minute,
                f"Faro should fire 5 min after Loki at :{loki_min:02d}",
            )
