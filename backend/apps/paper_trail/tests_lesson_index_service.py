"""TDD tests for the Python service wrappers around extensions.lesson_index.

Red phase: these tests define the contract the services must satisfy.
Green phase: implementation in services/lesson_index.py.
Refactor: keep helpers DRY across the three sub-services.
"""

from __future__ import annotations

import importlib
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services import lesson_index as svc


class ExtensionAvailableTests(SimpleTestCase):
    def test_extension_importable(self) -> None:
        mod = importlib.import_module("extensions.lesson_index")
        self.assertTrue(hasattr(mod, "ScopedLessonIndex"))
        self.assertTrue(hasattr(mod, "PerfBaselineCache"))
        self.assertTrue(hasattr(mod, "CitationCache"))


class ScopedLookupServiceTests(SimpleTestCase):
    def setUp(self) -> None:
        svc.reset_all_for_tests()

    def test_add_and_find(self) -> None:
        svc.scoped_add("backend/apps/audit/error_ingest.py", autoissue_id=1,
                       lesson_hash=42, severity=2)
        hits = svc.scoped_find("backend/apps/audit", limit=5)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["autoissue_id"], 1)

    def test_returns_records_sorted_by_priority(self) -> None:
        svc.scoped_add("a/b/c", autoissue_id=1, lesson_hash=1, severity=1)
        svc.scoped_add("a/b/d", autoissue_id=2, lesson_hash=2, severity=3)
        hits = svc.scoped_find("a/b")
        self.assertEqual(hits[0]["autoissue_id"], 2)  # severity=3 first

    def test_empty_prefix_returns_empty_when_no_data(self) -> None:
        hits = svc.scoped_find("nonexistent/path")
        self.assertEqual(hits, [])


class PerfBaselineServiceTests(SimpleTestCase):
    def setUp(self) -> None:
        svc.reset_all_for_tests()

    def test_put_then_get(self) -> None:
        svc.perf_put("apps.pipeline.ranker.score",
                     p50_ns=1000, p95_ns=2000, p99_ns=4000,
                     mean_ns=1500, samples=100)
        rec = svc.perf_get("apps.pipeline.ranker.score")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["p50_ns"], 1000)

    def test_missing_returns_none(self) -> None:
        self.assertIsNone(svc.perf_get("nope.function"))

    def test_speedup_helper(self) -> None:
        svc.perf_put("fn", p50_ns=20000, p95_ns=30000, p99_ns=50000,
                     mean_ns=25000, samples=100)
        # New time 1000 ns vs baseline 20000 ns → 20x speedup.
        speedup = svc.compute_speedup("fn", new_p50_ns=1000)
        self.assertAlmostEqual(speedup, 20.0, places=2)

    def test_speedup_returns_none_when_no_baseline(self) -> None:
        self.assertIsNone(svc.compute_speedup("nope", new_p50_ns=100))


class CitationServiceTests(SimpleTestCase):
    def setUp(self) -> None:
        svc.reset_all_for_tests()

    def test_put_then_get(self) -> None:
        svc.cite_put("doi:10.1109/ICDE.2013.6544812", kind="d",
                     id_="10.1109/ICDE.2013.6544812",
                     title="The Adaptive Radix Tree",
                     authors="Leis, Kemper, Neumann",
                     year=2013,
                     url="https://doi.org/10.1109/ICDE.2013.6544812",
                     accessible=1)
        rec = svc.cite_get("doi:10.1109/ICDE.2013.6544812")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["year"], 2013)
        self.assertEqual(rec["kind"], "d")


class SnapshotPersistenceTests(SimpleTestCase):
    def setUp(self) -> None:
        svc.reset_all_for_tests()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_save_load_roundtrip(self) -> None:
        svc.scoped_add("a/b", autoissue_id=99, lesson_hash=1, severity=2)
        svc.save_all(self.root)
        svc.reset_all_for_tests()
        svc.load_all(self.root)
        hits = svc.scoped_find("a/b")
        self.assertEqual(hits[0]["autoissue_id"], 99)


class RebuildFromDBTests(TestCase):
    def setUp(self) -> None:
        svc.reset_all_for_tests()

    def test_rebuild_scoped_from_resolved_autoissues(self) -> None:
        # The rebuild path pulls every resolved PaperTrailEntry into the
        # ScopedLessonIndex (since they're the lessons agents have logged).
        PaperTrailEntry.objects.create(
            category=PaperTrailEntry.CATEGORY_OTHER,
            title="rebuild source",
            abstract=(
                "Given the rebuild_scoped_from_resolved_autoissues test "
                "needs a resolved row, "
                "When the test creates one, "
                "Then it passes BDD validation and shows up in scope queries."
            ),
            deferred_by="test",
            affected_files=["backend/apps/audit/x.py"],
            status=PaperTrailEntry.STATUS_RESOLVED,
            resolved_at=timezone.now(),
            resolution_lessons="Trap: x. Fix shape: y.",
            risk_on_inaction="Test only.",
            acceptance_criteria="Test passes.",
        )
        count = svc.rebuild_scoped_from_db()
        self.assertGreaterEqual(count, 1)
