"""TDD tests for the Python dedup-service wrapper around papertrail_dedup."""

from __future__ import annotations

import importlib
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services import dedup as dedup_service
from apps.paper_trail.tests_helpers import valid_paper_trail_defaults


class DedupIndexAvailabilityTests(SimpleTestCase):
    """The C++ extension is available."""

    def test_extension_importable(self) -> None:
        mod = importlib.import_module("extensions.papertrail_dedup")
        self.assertTrue(hasattr(mod, "DedupIndex"))


class DedupServiceWrapperTests(SimpleTestCase):
    """The thin wrapper exposes a stable Python API."""

    def setUp(self) -> None:
        dedup_service.reset_index_for_tests()

    def test_add_entry_roundtrip(self) -> None:
        ok = dedup_service.add_entry(1, "First abstract about CVE upgrade.")
        self.assertTrue(ok)
        self.assertEqual(dedup_service.size(), 1)

    def test_find_similar_returns_added_entry(self) -> None:
        dedup_service.add_entry(7, "Deferred upgrade of Django to 5.2.14")
        hits = dedup_service.find_similar(
            "Deferred upgrade of Django to 5.2.14", threshold=0.85
        )
        self.assertEqual(hits[0][0], 7)

    def test_remove_entry_removes_from_index(self) -> None:
        dedup_service.add_entry(3, "Something to remove later")
        dedup_service.remove_entry(3)
        self.assertEqual(dedup_service.size(), 0)

    def test_has_duplicate_uses_threshold(self) -> None:
        dedup_service.add_entry(
            5, "Coverage gap for ranker scoring rule contract tests."
        )
        self.assertTrue(
            dedup_service.has_duplicate(
                "Coverage gap for ranker scoring rule contract tests.", threshold=0.85
            )
        )
        self.assertFalse(
            dedup_service.has_duplicate("Unrelated entry about GPU profiling.")
        )


class DedupSnapshotPersistenceTests(SimpleTestCase):
    def setUp(self) -> None:
        dedup_service.reset_index_for_tests()
        self._tmp = tempfile.TemporaryDirectory()
        self._path = Path(self._tmp.name) / "papertrail.idx"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_save_and_reload_preserves_entries(self) -> None:
        dedup_service.add_entry(11, "Persistence test abstract one")
        dedup_service.add_entry(22, "Persistence test abstract two")
        dedup_service.save_snapshot(self._path)

        dedup_service.reset_index_for_tests()
        self.assertEqual(dedup_service.size(), 0)

        dedup_service.load_snapshot(self._path)
        self.assertEqual(dedup_service.size(), 2)
        hits = dedup_service.find_similar(
            "Persistence test abstract one", threshold=0.85
        )
        self.assertTrue(any(h[0] == 11 for h in hits))


class DedupRebuildFromDBTests(TestCase):
    """The service can rebuild its index from open DB rows on cold start."""

    def setUp(self) -> None:
        dedup_service.reset_index_for_tests()

    def test_rebuild_from_db_populates_index(self) -> None:
        PaperTrailEntry.objects.create(
            **valid_paper_trail_defaults(
                category=PaperTrailEntry.CATEGORY_OTHER,
                title="Rebuild source A",
                abstract=(
                "Given the rebuild_from_db test needs row A, "
                "When the test creates it, "
                "Then the abstract is long enough for shingling."
            ),
            )
        )
        PaperTrailEntry.objects.create(
            **valid_paper_trail_defaults(
                category=PaperTrailEntry.CATEGORY_OTHER,
                title="Rebuild source B",
                abstract=(
                "Given the rebuild_from_db test needs row B, "
                "When the test creates it, "
                "Then the abstract is long enough for shingling work."
            ),
            )
        )
        dedup_service.rebuild_from_db()
        self.assertEqual(dedup_service.size(), 2)
