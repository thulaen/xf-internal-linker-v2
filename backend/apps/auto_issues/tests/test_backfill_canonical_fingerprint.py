"""Tests for manage.py backfill_canonical_fingerprint (S3776 fix helper)."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue


class BuildSourceObservationHelperTests(TestCase):
    """Tests for _build_source_observation extracted from handle() (S3776 fix)."""

    def _make_row(self, **kwargs) -> AutoIssue:
        defaults = {
            "source": AutoIssue.SOURCE_AGENT,
            "external_id": "bcf-test",
            "fingerprint": "bcf-test",
            "title": "BCF test",
            "severity": AutoIssue.SEVERITY_LOW,
            "status": AutoIssue.STATUS_OPEN,
        }
        defaults.update(kwargs)
        return AutoIssue.objects.create(**defaults)

    def test_build_source_observation_includes_all_keys(self):
        from apps.auto_issues.management.commands.backfill_canonical_fingerprint import (
            _build_source_observation,
        )
        row = self._make_row(first_seen=timezone.now(), last_seen=timezone.now())
        obs = _build_source_observation(row)
        self.assertIn("source", obs)
        self.assertIn("external_id", obs)
        self.assertIn("first_seen", obs)
        self.assertIn("last_seen", obs)
        self.assertIn("occurrence_count", obs)

    def test_build_source_observation_timestamps_are_iso8601(self):
        from apps.auto_issues.management.commands.backfill_canonical_fingerprint import (
            _build_source_observation,
        )
        ts = timezone.now()
        row = self._make_row(first_seen=ts, last_seen=ts)
        obs = _build_source_observation(row)
        self.assertRegex(obs["first_seen"], r"\d{4}-\d{2}-\d{2}T")
        self.assertRegex(obs["last_seen"], r"\d{4}-\d{2}-\d{2}T")

    def test_build_source_observation_none_timestamps_return_empty_string(self):
        from unittest.mock import MagicMock
        from apps.auto_issues.management.commands.backfill_canonical_fingerprint import (
            _build_source_observation,
        )
        row = MagicMock()
        row.source = "agent"
        row.external_id = "x"
        row.first_seen = None
        row.last_seen = None
        row.occurrence_count = 1
        obs = _build_source_observation(row)
        self.assertEqual(obs["first_seen"], "")
        self.assertEqual(obs["last_seen"], "")
