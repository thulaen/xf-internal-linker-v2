"""Tests for `services.loki_picker`.

The picker has two pure-function pieces (normalize, fingerprint) we
unit-test directly, and two HTTP-touching pieces (hot_patterns,
warn_bursts) we mock so the test suite stays hermetic.

Added 2026-05-10 per plan
``does-adding-qodana-make-swift-wall.md`` Stream 4.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.loki_picker import (
    LokiCandidate,
    _gather_hot_patterns,
    _normalize_line,
    _stable_fingerprint,
    pick_loki_hot_patterns,
    pick_loki_warn_bursts,
)


class NormalizationTests(SimpleTestCase):
    """The fingerprint normalizer collapses volatile content so similar
    log lines share an identity."""

    def test_strips_iso_timestamp(self):
        line = "2026-05-10 08:48:21,488 ERROR something failed"
        out = _normalize_line(line)
        self.assertNotIn("2026-05-10", out)
        self.assertIn("ERROR something failed", out)

    def test_strips_pid_and_thread_id(self):
        line = "INFO 2026-05-10 08:48:21,488 registry 27365 135021798118144 ready"
        out = _normalize_line(line)
        # The 5+digit ints (PID, thread) get replaced.
        self.assertIn("<N>", out)
        self.assertNotIn("27365", out)
        self.assertNotIn("135021798118144", out)

    def test_strips_hex_address(self):
        line = "Segfault at 0x7f8a3b2c0 — RIP"
        out = _normalize_line(line)
        self.assertIn("<HEX>", out)
        self.assertNotIn("0x7f8a3b2c0", out)

    def test_strips_traceback_line_number(self):
        line = 'File "/app/foo.py", line 123, in handler'
        out = _normalize_line(line)
        self.assertIn("line <N>", out)
        self.assertNotIn("line 123", out)

    def test_strips_uuid(self):
        line = "request 12345678-1234-1234-1234-1234567890ab failed"
        out = _normalize_line(line)
        self.assertIn("<UUID>", out)
        self.assertNotIn("12345678", out)

    def test_two_similar_lines_share_fingerprint(self):
        a = "2026-05-10 08:48:21,488 ERROR conn closed at 0xdead"
        b = "2026-05-10 09:13:55,011 ERROR conn closed at 0xbeef"
        self.assertEqual(_normalize_line(a), _normalize_line(b))


class StableFingerprintTests(SimpleTestCase):
    def test_includes_prefix(self):
        fp = _stable_fingerprint("loki:hot", "ERROR conn closed")
        self.assertTrue(fp.startswith("loki:hot::"))

    def test_deterministic(self):
        a = _stable_fingerprint("loki:hot", "ERROR conn closed")
        b = _stable_fingerprint("loki:hot", "ERROR conn closed")
        self.assertEqual(a, b)

    def test_disjoint_prefixes_disjoint_fingerprints(self):
        # Same input, different prefix -> different fingerprint.
        a = _stable_fingerprint("loki:hot", "ERROR conn closed")
        b = _stable_fingerprint("loki:burst", "ERROR conn closed")
        self.assertNotEqual(a, b)


class LokiHotPatternIntegrationTests(TestCase):
    """End-to-end: mock Loki HTTP, assert AutoIssue rows materialize."""

    @mock.patch("apps.auto_issues.services.loki_picker._fetch_loki_lines")
    def test_pick_loki_hot_patterns_promotes_to_autoissue(self, mock_fetch):
        # 12 occurrences of one normalized pattern, container = backend.
        mock_fetch.return_value = [
            ("xf_linker_backend", f"ERROR 2026-05-10 0{i}:00:00,000 conn closed")
            for i in range(12)
        ]
        result = pick_loki_hot_patterns(limit=5)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["patterns_found"], 1)
        self.assertGreaterEqual(result["promoted"], 1)
        rows = AutoIssue.objects.filter(source=AutoIssue.SOURCE_LOKI)
        self.assertGreaterEqual(rows.count(), 1)
        self.assertTrue(any("hot_pattern" in r.title for r in rows))

    @mock.patch("apps.auto_issues.services.loki_picker._fetch_loki_lines")
    def test_below_threshold_does_not_promote(self, mock_fetch):
        # Only 2 occurrences -> below default threshold of 10.
        mock_fetch.return_value = [
            ("xf_linker_backend", "ERROR conn closed")
            for _ in range(2)
        ]
        result = pick_loki_hot_patterns(limit=5)
        self.assertEqual(result["patterns_found"], 0)
        self.assertEqual(result["promoted"], 0)
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_LOKI).count(), 0
        )

    @mock.patch("apps.auto_issues.services.loki_picker._fetch_loki_lines")
    def test_disjoint_normalized_patterns_each_count_separately(self, mock_fetch):
        # 12 of pattern A, 5 of pattern B -> only A promotes (default
        # threshold 10).
        mock_fetch.return_value = (
            [("c", "ERROR pattern A occurred") for _ in range(12)]
            + [("c", "WARN pattern B occurred") for _ in range(5)]
        )
        result = pick_loki_hot_patterns(limit=5)
        self.assertEqual(result["patterns_found"], 1)
        self.assertEqual(result["promoted"], 1)


class LokiWarnBurstIntegrationTests(TestCase):
    @mock.patch(
        "apps.auto_issues.services.loki_picker._container_count_over_time"
    )
    @mock.patch(
        "apps.auto_issues.services.loki_picker._list_active_containers"
    )
    def test_promotes_when_last_hour_exceeds_baseline(self, mock_list, mock_count):
        mock_list.return_value = ["xf_linker_backend"]
        # Stub: 1h returns 100, 24h returns 24*5 = 120 (avg 5/h)
        # ratio = 100/5 = 20x — well above default multiplier 3x.
        def side(api_url, *, container, range_s, **kw):
            return 100 if range_s == 3600 else 120
        mock_count.side_effect = side
        result = pick_loki_warn_bursts(limit=5)
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["promoted"], 1)
        self.assertEqual(
            AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_LOKI
            ).filter(title__icontains="warn_burst").count(),
            1,
        )

    @mock.patch(
        "apps.auto_issues.services.loki_picker._container_count_over_time"
    )
    @mock.patch(
        "apps.auto_issues.services.loki_picker._list_active_containers"
    )
    def test_no_promote_when_baseline_empty(self, mock_list, mock_count):
        mock_list.return_value = ["xf_linker_backend"]
        # Both queries return 0 — picker must no-op (no divide-by-zero).
        mock_count.return_value = 0
        result = pick_loki_warn_bursts(limit=5)
        self.assertEqual(result["bursts_found"], 0)
        self.assertEqual(result["promoted"], 0)


class LokiPickerScheduleTests(SimpleTestCase):
    def test_schedule_runs_every_30_minutes(self):
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        entry = CELERY_BEAT_SCHEDULE.get("auto-issues-loki-pick")
        self.assertIsNotNone(entry, "Loki picker schedule entry missing")
        cron = entry["schedule"]
        self.assertIn(15, cron.minute)
        self.assertIn(45, cron.minute)
        self.assertEqual(len(cron.hour), 13)

    def test_schedule_staggered_after_pyroscope(self):
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        pyro = CELERY_BEAT_SCHEDULE["auto-issues-pyroscope-pick"]["schedule"]
        loki = CELERY_BEAT_SCHEDULE["auto-issues-loki-pick"]["schedule"]
        for pyro_min in pyro.minute:
            self.assertIn(
                (pyro_min + 5) % 60, loki.minute,
                f"Loki should fire 5 min after Pyroscope at :{pyro_min:02d}",
            )
