"""Tests for the paper-trail safe-prune service."""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import TestCase
from django.utils import timezone

from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services import safe_prune


class SafePruneTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_resolved(self, *, affected_files: list[str]) -> PaperTrailEntry:
        entry = PaperTrailEntry.objects.create(
            category=PaperTrailEntry.CATEGORY_OTHER,
            title="resolved entry for safe prune",
            abstract=(
                "Given the safe-prune tests need a resolved entry, "
                "When _make_resolved() constructs one, "
                "Then it passes BDD validation."
            ),
            deferred_by="test",
            affected_files=affected_files,
            risk_on_inaction="Test only.",
            acceptance_criteria="Test passes.",
        )
        entry.status = PaperTrailEntry.STATUS_RESOLVED
        entry.resolved_at = timezone.now()
        entry.resolution_lessons = "Trap: x. Fix shape: y."
        entry.save()
        return entry

    def test_returns_empty_when_no_resolved_entries(self) -> None:
        out = safe_prune.paper_trail_eligible_dirs(self.root)
        self.assertEqual(out, [])

    def test_skips_non_whitelisted_prefixes(self) -> None:
        self._make_resolved(affected_files=["backend/apps/audit/error_ingest.py"])
        bogus = self.root / "random-junk"
        bogus.mkdir()
        (bogus / "fake.txt").write_text("backend/apps/audit/error_ingest.py")
        eligible = safe_prune.paper_trail_eligible_dirs(self.root)
        self.assertEqual(eligible, [])

    def test_includes_whitelisted_dir_with_matching_path(self) -> None:
        self._make_resolved(affected_files=["backend/apps/audit/error_ingest.py"])
        mutmut_dir = self.root / "mutmut-debug-abc"
        mutmut_dir.mkdir()
        (mutmut_dir / "report.txt").write_text(
            "ran mutmut on backend/apps/audit/error_ingest.py"
        )
        eligible = safe_prune.paper_trail_eligible_dirs(self.root)
        self.assertEqual(eligible, [mutmut_dir.resolve()])

    def test_protected_names_never_returned(self) -> None:
        self._make_resolved(affected_files=["backend/apps/audit/error_ingest.py"])
        # Pretend `pgdata` got accidentally placed under the prune root.
        pgdata = self.root / "pgdata"
        pgdata.mkdir()
        (pgdata / "file.txt").write_text("backend/apps/audit/error_ingest.py")
        eligible = safe_prune.paper_trail_eligible_dirs(self.root)
        self.assertEqual(eligible, [])

    def test_refuses_root_filesystem(self) -> None:
        # Even if a logged path matches, never operate on '/'.
        self._make_resolved(affected_files=["anything"])
        self.assertEqual(safe_prune.paper_trail_eligible_dirs(Path("/")), [])
