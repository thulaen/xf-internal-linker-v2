"""TDD tests for migrate_handoff_deferrals command."""

from __future__ import annotations

import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services import dedup as dedup_service


_SAMPLE_HANDOFF = """# 2026-05-15 15:56 - Claude Opus 4.7 - Sample handoff

What I did:
Some work.

What has issues or errors:
This is a mid-session handoff. The commit gate is not met because 23 of the 30 picked AutoIssues remain unresolved.

1. **#252, #253 (pip-audit / safety)**: `pip-audit` surfaces 18 real known vulnerabilities in 8 packages — Django 5.2.13→5.2.14+, markdown 3.7→3.8.1, mcp 1.1.2→1.23.0. Upgrading these requires careful regression testing because pytest and Django are major-version moves. Multi-session.

2. **#210, #211, #212 (ruff sweeps)**: 147 violations total — 37 E701, 42 PT019, 68 N* naming. None are safely auto-fixable. Multi-session.

3. **#258, #259, #260 (infrastructure features)**: Each is a major feature — backup freshness monitoring + restore smoke test, NVIDIA GPU metrics for embedding workloads. Multi-session.

Verification:
All commands exit 0.

Tech-debt delta: -8.
---
"""


class MigrateHandoffTests(TestCase):
    def setUp(self) -> None:
        dedup_service.reset_index_for_tests()
        self._tmp = tempfile.TemporaryDirectory()
        self._handoff = Path(self._tmp.name) / "AGENT-HANDOFF.md"
        self._handoff.write_text(_SAMPLE_HANDOFF, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_dry_run_does_not_create(self) -> None:
        out = StringIO()
        call_command(
            "migrate_handoff_deferrals",
            "--handoff-path", str(self._handoff),
            "--dry-run",
            stdout=out,
        )
        self.assertEqual(PaperTrailEntry.objects.count(), 0)
        self.assertIn("DRY-RUN", out.getvalue())

    def test_creates_entries_for_three_items(self) -> None:
        out = StringIO()
        call_command(
            "migrate_handoff_deferrals",
            "--handoff-path", str(self._handoff),
            stdout=out,
        )
        # Three deferred items in the sample → three rows.
        self.assertEqual(PaperTrailEntry.objects.count(), 3)
        # Categories should be inferred via keyword heuristics.
        cats = sorted(
            PaperTrailEntry.objects.values_list("category", flat=True)
        )
        self.assertIn(PaperTrailEntry.CATEGORY_CVE_UPGRADE, cats)
        self.assertIn(PaperTrailEntry.CATEGORY_RUFF_SWEEP, cats)
        self.assertIn(PaperTrailEntry.CATEGORY_INFRASTRUCTURE, cats)

    def test_idempotent_via_dedup(self) -> None:
        call_command(
            "migrate_handoff_deferrals",
            "--handoff-path", str(self._handoff),
            stdout=StringIO(),
        )
        first_count = PaperTrailEntry.objects.count()
        out = StringIO()
        call_command(
            "migrate_handoff_deferrals",
            "--handoff-path", str(self._handoff),
            stdout=out,
        )
        self.assertEqual(PaperTrailEntry.objects.count(), first_count)
        self.assertIn("dedupe-skipped=", out.getvalue())

    def test_linked_autoissue_extracted(self) -> None:
        call_command(
            "migrate_handoff_deferrals",
            "--handoff-path", str(self._handoff),
            stdout=StringIO(),
        )
        autoissue_ids = sorted(
            PaperTrailEntry.objects.exclude(
                linked_autoissue_id__isnull=True
            ).values_list("linked_autoissue_id", flat=True)
        )
        self.assertIn(252, autoissue_ids)  # from item 1
        self.assertIn(210, autoissue_ids)  # from item 2
        self.assertIn(258, autoissue_ids)  # from item 3
