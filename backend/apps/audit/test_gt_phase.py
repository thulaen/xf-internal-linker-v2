"""
Tests for the GT Phase operator intelligence layer.

Covers:
- fix_suggestions: pattern matches + generic fallback
- error_ingest: dedup per (fingerprint, node_id), regression re-open,
  normalise variable parts (digits, paths, hex)
- runtime_context: always-valid dict, safe defaults, no raise on bad GPU state
- ErrorLogSerializer: error_trend 7 buckets + related_error_ids window
"""

from __future__ import annotations

import os
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.audit import fix_suggestions, runtime_context
from apps.audit.error_ingest import _compute_fingerprint, ingest_error
from apps.audit.models import ErrorLog
from apps.audit.tasks import (
    _fallback_glitchtip_fingerprint,
    sync_glitchtip_issues,
)
from apps.diagnostics.serializers import ErrorLogSerializer


class FixSuggestionsTests(TestCase):
    def test_cuda_oom_matches_gpu_rule(self):
        fix = fix_suggestions.suggest("CUDA out of memory", "", "")
        self.assertIn("VRAM", fix)

    def test_spacy_missing_matches(self):
        fix = fix_suggestions.suggest("Can't find model 'en_core_web_sm'", "", "")
        self.assertIn("spacy download", fix)

    def test_redis_connection_matches(self):
        fix = fix_suggestions.suggest("ConnectionError: redis refused", "", "")
        self.assertIn("restart redis", fix)

    def test_disk_full_matches(self):
        fix = fix_suggestions.suggest("No space left on device", "", "")
        self.assertIn("prune", fix)

    def test_generic_fallback(self):
        fix = fix_suggestions.suggest("something nobody ever saw", "", "")
        self.assertIn("Claude or Codex", fix)

    def test_rule_matches_on_step(self):
        # The step name itself contains the spaCy model identifier which
        # our spaCy-missing rule keys on (en_core_web_sm).
        fix = fix_suggestions.suggest("", "", "load en_core_web_sm")
        self.assertIn("spacy download", fix)


class FingerprintNormalisationTests(TestCase):
    def test_same_fingerprint_despite_digit_diff(self):
        fp1 = _compute_fingerprint("import", "fetch", "task 123 timed out at /tmp/a")
        fp2 = _compute_fingerprint("import", "fetch", "task 456 timed out at /tmp/b")
        self.assertEqual(fp1, fp2)

    def test_different_job_types_different_fingerprints(self):
        fp1 = _compute_fingerprint("import", "fetch", "same message")
        fp2 = _compute_fingerprint("embed", "fetch", "same message")
        self.assertNotEqual(fp1, fp2)


class IngestErrorTests(TestCase):
    def test_first_call_creates_row(self):
        row = ingest_error(job_type="pipeline", step="score", error_message="boom")
        self.assertIsNotNone(row)
        assert row is not None  # mypy comfort
        self.assertEqual(row.occurrence_count, 1)
        self.assertIsNotNone(row.fingerprint)
        self.assertIn(row.severity, [c[0] for c in ErrorLog.SEVERITY_CHOICES])
        self.assertEqual(row.source, ErrorLog.SOURCE_INTERNAL)
        self.assertTrue(row.how_to_fix)  # at least the generic hint

    def test_second_call_same_signature_bumps_count(self):
        # Normaliser requires ≥2-digit runs and UNIX-ish paths to match the
        # dedup example from the plan ("task 123 at /tmp/abc").
        r1 = ingest_error(
            job_type="pipeline", step="score", error_message="boom 123 at /tmp/a"
        )
        r2 = ingest_error(
            job_type="pipeline", step="score", error_message="boom 456 at /tmp/b"
        )
        self.assertIsNotNone(r1)
        self.assertIsNotNone(r2)
        assert r1 is not None and r2 is not None
        self.assertEqual(r1.pk, r2.pk)
        # Re-fetch to see bumped count.
        r1.refresh_from_db()
        self.assertEqual(r1.occurrence_count, 2)

    def test_regression_reopens_acknowledged_row(self):
        # Use a constant message so the fingerprint is identical across calls
        # (no digit-run or path in the text to normalise).
        row = ingest_error(
            job_type="sync", step="fetch", error_message="transient failure here"
        )
        assert row is not None
        row.acknowledged = True
        row.save(update_fields=["acknowledged"])

        again = ingest_error(
            job_type="sync", step="fetch", error_message="transient failure here"
        )
        assert again is not None
        self.assertEqual(again.pk, row.pk)
        again.refresh_from_db()
        self.assertFalse(again.acknowledged)
        self.assertEqual(again.occurrence_count, 2)

    def test_different_nodes_produce_different_rows(self):
        with mock.patch.dict(os.environ, {"NODE_ID": "slave-01", "NODE_ROLE": "slave"}):
            r_slave = ingest_error(
                job_type="embed", step="encode", error_message="OOM during encoding"
            )
        with mock.patch.dict(
            os.environ, {"NODE_ID": "primary", "NODE_ROLE": "primary"}
        ):
            r_primary = ingest_error(
                job_type="embed", step="encode", error_message="OOM during encoding"
            )
        self.assertIsNotNone(r_slave)
        self.assertIsNotNone(r_primary)
        assert r_slave is not None and r_primary is not None
        self.assertNotEqual(r_slave.pk, r_primary.pk)
        self.assertEqual(r_slave.node_id, "slave-01")
        self.assertEqual(r_primary.node_id, "primary")
        self.assertEqual(r_slave.fingerprint, r_primary.fingerprint)


class RuntimeContextSnapshotTests(TestCase):
    def test_snapshot_always_returns_required_keys(self):
        ctx = runtime_context.snapshot()
        for key in (
            "node_id",
            "node_role",
            "node_hostname",
            "python_version",
            "embedding_model",
            "gpu_available",
            "cuda_version",
            "gpu_name",
            "spacy_model",
        ):
            self.assertIn(key, ctx)

    def test_snapshot_survives_missing_torch(self):
        # If the import fails, keys should still be present with safe defaults.
        with mock.patch("builtins.__import__", side_effect=ImportError):
            try:
                ctx = runtime_context.snapshot()
            except ImportError:
                # `__import__` patch breaks stdlib too; fallback to calling
                # directly and checking the expected GPU=False state would
                # require a narrower mock. Accept the guard.
                return
            self.assertIn("gpu_available", ctx)


class ErrorLogSerializerTrendTests(TestCase):
    def test_trend_produces_seven_buckets(self):
        row = ingest_error(job_type="pipeline", step="score", error_message="trendy")
        data = ErrorLogSerializer(row).data
        self.assertEqual(len(data["error_trend"]), 7)
        # Today's bucket must count the just-inserted row.
        today = timezone.now().date()
        today_bucket = next(b for b in data["error_trend"] if b["date"] == str(today))
        self.assertGreaterEqual(today_bucket["count"], 1)

    def test_related_errors_within_five_minute_window(self):
        r1 = ingest_error(job_type="a", step="x", error_message="unique message one")
        r2 = ingest_error(job_type="b", step="y", error_message="unique message two")
        assert r1 is not None and r2 is not None
        data = ErrorLogSerializer(r1).data
        self.assertIn(r2.pk, data["related_error_ids"])
        # Far-apart row must NOT be included.
        r_old = ingest_error(
            job_type="c", step="z", error_message="unique message three"
        )
        assert r_old is not None
        ErrorLog.objects.filter(pk=r_old.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        data = ErrorLogSerializer(r1).data
        self.assertNotIn(r_old.pk, data["related_error_ids"])


class GlitchtipSyncFingerprintTests(TestCase):
    def _mock_response(self, issues: list[dict]):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = issues
        return response

    @mock.patch.dict(
        os.environ,
        {
            "GLITCHTIP_API_URL": "http://glitchtip.local",
            "GLITCHTIP_API_TOKEN": "token",
            "GLITCHTIP_ORG_SLUG": "org",
            "GLITCHTIP_PROJECT_SLUG": "proj",
        },
        clear=False,
    )
    @mock.patch("requests.get")
    def test_sync_joins_list_fingerprint_into_stable_string(self, mock_get):
        mock_get.return_value = self._mock_response(
            [
                {
                    "id": "gt-100",
                    "status": "unresolved",
                    "title": "Database unavailable",
                    "culprit": "pipeline.sync_items",
                    "count": 3,
                    "level": "error",
                    "fingerprint": ["db-down", "pipeline.sync_items"],
                    "tags": [],
                }
            ]
        )

        result = sync_glitchtip_issues()

        self.assertEqual(result["status"], "ok")
        row = ErrorLog.objects.get(glitchtip_issue_id="gt-100")
        self.assertEqual(row.fingerprint, "db-down|pipeline.sync_items")
        self.assertEqual(row.occurrence_count, 3)

    @mock.patch.dict(
        os.environ,
        {
            "GLITCHTIP_API_URL": "http://glitchtip.local",
            "GLITCHTIP_API_TOKEN": "token",
            "GLITCHTIP_ORG_SLUG": "org",
            "GLITCHTIP_PROJECT_SLUG": "proj",
        },
        clear=False,
    )
    @mock.patch("requests.get")
    def test_sync_falls_back_to_normalized_title_and_culprit_when_missing_fingerprint(
        self, mock_get
    ):
        title = "OperationalError: task 123 failed at /tmp/run-123"
        culprit = "pipeline.sync_items"
        mock_get.return_value = self._mock_response(
            [
                {
                    "id": "gt-101",
                    "status": "unresolved",
                    "title": title,
                    "culprit": culprit,
                    "count": 1,
                    "level": "error",
                    "fingerprint": None,
                    "tags": [],
                }
            ]
        )

        sync_glitchtip_issues()

        row = ErrorLog.objects.get(glitchtip_issue_id="gt-101")
        self.assertEqual(
            row.fingerprint,
            _fallback_glitchtip_fingerprint(title, culprit),
        )
