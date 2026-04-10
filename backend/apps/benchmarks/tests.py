"""Tests for the benchmarks app."""

from django.test import TestCase

from .models import BenchmarkResult, BenchmarkRun
from .services.reporter import generate_report


class BenchmarkRunModelTest(TestCase):
    def test_create_run(self):
        run = BenchmarkRun.objects.create(trigger="manual")
        self.assertEqual(run.status, "running")
        self.assertEqual(run.trigger, "manual")
        self.assertIsNone(run.finished_at)

    def test_run_str(self):
        run = BenchmarkRun.objects.create(trigger="scheduled")
        self.assertIn("scheduled", str(run))


class BenchmarkResultModelTest(TestCase):
    def test_create_result(self):
        run = BenchmarkRun.objects.create(trigger="manual")
        result = BenchmarkResult.objects.create(
            run=run,
            language="cpp",
            extension="l2norm",
            function_name="L2Norm1D",
            input_size="small",
            mean_ns=110,
            median_ns=109,
            items_per_second=1.17e9,
            status="fast",
        )
        self.assertEqual(result.language, "cpp")
        self.assertIn("l2norm", str(result))


class ReportGeneratorTest(TestCase):
    def test_generate_report_empty_run(self):
        run = BenchmarkRun.objects.create(trigger="manual", status="completed")
        report = generate_report(run)
        self.assertIn("BENCHMARK REPORT", report)
        self.assertIn("Total benchmarked: 0", report)

    def test_generate_report_with_results(self):
        run = BenchmarkRun.objects.create(trigger="manual", status="completed")
        BenchmarkResult.objects.create(
            run=run,
            language="cpp",
            extension="l2norm",
            function_name="L2NormBatch",
            input_size="medium",
            mean_ns=4_200_000,
            median_ns=4_100_000,
            status="fast",
        )
        BenchmarkResult.objects.create(
            run=run,
            language="python",
            extension="scoring",
            function_name="score_full_batch",
            input_size="large",
            mean_ns=890_000_000,
            median_ns=880_000_000,
            status="slow",
            threshold_ns=300_000_000,
        )
        report = generate_report(run)
        self.assertIn("SLOW FUNCTIONS", report)
        self.assertIn("scoring", report)
        self.assertIn("Total benchmarked: 2", report)
