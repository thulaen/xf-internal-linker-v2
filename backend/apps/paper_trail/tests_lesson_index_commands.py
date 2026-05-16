"""TDD tests for the 8 lesson_index-backed management commands."""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from apps.auto_issues.models import AutoIssue
from apps.paper_trail.services import lesson_index as svc


class RecordPerfBaselineTests(SimpleTestCase):
    def setUp(self) -> None:
        svc.reset_all_for_tests()

    def test_records_baseline(self) -> None:
        out = StringIO()
        call_command(
            "record_perf_baseline",
            "--function", "apps.x.y",
            "--p50-ns", "10000",
            "--p95-ns", "15000",
            "--p99-ns", "30000",
            "--samples", "100",
            stdout=out,
        )
        self.assertIn("PERF BASELINE RECORDED", out.getvalue())
        rec = svc.perf_get("apps.x.y")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["p50_ns"], 10000)


class VerifyPerfSpeedupTests(SimpleTestCase):
    def setUp(self) -> None:
        svc.reset_all_for_tests()
        svc.perf_put("apps.x.y", p50_ns=20000, p95_ns=30000, p99_ns=50000,
                     mean_ns=25000, samples=100)

    def test_20x_emits_proof_marker(self) -> None:
        out = StringIO()
        call_command(
            "verify_perf_speedup",
            "--function", "apps.x.y",
            "--new-p50-ns", "1000",
            stdout=out,
        )
        self.assertIn("PERFORMANCE PROOF", out.getvalue())
        self.assertIn("speedup=20.00x", out.getvalue())

    def test_below_20x_without_reason_fails(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "verify_perf_speedup",
                "--function", "apps.x.y",
                "--new-p50-ns", "15000",
                stdout=StringIO(),
            )

    def test_below_20x_with_reason_emits_exemption(self) -> None:
        out = StringIO()
        call_command(
            "verify_perf_speedup",
            "--function", "apps.x.y",
            "--new-p50-ns", "15000",
            "--iterations", "10",
            "--exemption-reason",
            "I/O bound — function makes a network call we cannot batch.",
            stdout=out,
        )
        self.assertIn("PERFORMANCE EXEMPTION", out.getvalue())


class LogPerformanceExemptionTests(TestCase):
    def test_creates_autoissue(self) -> None:
        out = StringIO()
        call_command(
            "log_performance_exemption",
            "--function", "apps.audit.error_ingest.ingest_error",
            "--reason",
            "External GlitchTip POST blocks on network round-trip.",
            "--best-achieved", "2.5",
            "--iterations", "10",
            stdout=out,
        )
        self.assertIn("PERF EXEMPTION LOGGED", out.getvalue())
        ai = AutoIssue.objects.filter(
            title__startswith="[perf_exemption]"
        ).first()
        self.assertIsNotNone(ai)

    def test_short_reason_rejected(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "log_performance_exemption",
                "--function", "apps.x.y",
                "--reason", "too short",
                "--best-achieved", "1.5",
                stdout=StringIO(),
            )


class CiteSpecTests(SimpleTestCase):
    def setUp(self) -> None:
        svc.reset_all_for_tests()

    def test_registers_citation(self) -> None:
        out = StringIO()
        call_command(
            "cite_spec",
            "--key", "doi:10.1109/ICDE.2013.6544812",
            "--kind", "doi",
            "--id", "10.1109/ICDE.2013.6544812",
            "--title", "The Adaptive Radix Tree",
            "--authors", "Leis, Kemper, Neumann",
            "--year", "2013",
            "--url", "https://doi.org/10.1109/ICDE.2013.6544812",
            "--feature-id", "lesson-index",
            stdout=out,
        )
        self.assertIn("SPEC CITED", out.getvalue())


class ReadScopedLessonsTests(SimpleTestCase):
    def setUp(self) -> None:
        svc.reset_all_for_tests()

    def test_empty_emits_marker_with_zero(self) -> None:
        out = StringIO()
        call_command(
            "read_scoped_lessons",
            "--area", "backend/apps/x",
            stdout=out,
        )
        self.assertIn("[SCOPED LESSONS READ: 0 lessons", out.getvalue())

    def test_finds_added_lessons(self) -> None:
        svc.scoped_add("backend/apps/x/y.py", autoissue_id=1, lesson_hash=42,
                       severity=2)
        out = StringIO()
        call_command(
            "read_scoped_lessons",
            "--area", "backend/apps/x",
            stdout=out,
        )
        self.assertIn("[SCOPED LESSONS READ: 1 lessons", out.getvalue())
