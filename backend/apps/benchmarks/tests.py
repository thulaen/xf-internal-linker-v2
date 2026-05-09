"""Tests for the benchmarks app."""

import stat
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import BenchmarkResult, BenchmarkRun
from .services.reporter import generate_report
from .services.runner import _discover_cpp_benchmark_executables
from .tasks import _detect_storm_skip


class StormGuardTests(TestCase):
    """ISS-102: prevent storm of `run_all_benchmarks` invocations.

    Backstory: 2026-05-08 saw 5 BenchmarkRun rows created in a 67-second
    window from an unknown caller. The storm guard refuses to dispatch
    a fresh run when another started in the last 60 s.
    """

    _self = SimpleNamespace(request=SimpleNamespace(id="t1", origin="testbot"))

    def test_no_recent_runs_does_not_skip(self):
        self.assertFalse(_detect_storm_skip(self._self, "scheduled"))

    def test_run_more_than_60s_ago_does_not_skip(self):
        old = BenchmarkRun.objects.create(trigger="scheduled")
        BenchmarkRun.objects.filter(pk=old.pk).update(
            started_at=timezone.now() - timedelta(seconds=120)
        )
        self.assertFalse(_detect_storm_skip(self._self, "scheduled"))

    def test_run_in_last_60s_skips(self):
        BenchmarkRun.objects.create(trigger="scheduled")
        # `started_at` defaults to auto_now_add → very recent.
        self.assertTrue(_detect_storm_skip(self._self, "scheduled"))

    def test_run_in_last_60s_with_manual_trigger_still_skips(self):
        # The guard does not look at trigger type — caller decides whether
        # to bypass via run_id (see run_all_benchmarks). The function
        # itself returns True for any recent run.
        BenchmarkRun.objects.create(trigger="manual")
        self.assertTrue(_detect_storm_skip(self._self, "scheduled"))


class DiscoverCppBenchmarkExecutablesTests(SimpleTestCase):
    """Bug fix 2026-05-09: Docker-on-Windows bind mounts mark every file
    as executable, so the old `executable-bit` probe accepted MSVC
    by-products like ``.exp`` and ``.lib`` and tried to exec them.

    The runner now uses a positive allow-list (`.exe` or no extension)
    plus an explicit deny-list of compilation by-products.
    """

    def test_filters_out_msvc_byproducts_even_when_exec_bit_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            build = Path(tmp)
            # Layout that mimics what `python setup.py build_ext` leaves on
            # a Windows host bind-mounted into Linux: every file gets +x.
            files = {
                "bench_l2norm.exe": True,        # valid Windows binary
                "bench_l2norm.exp": True,        # MSVC export — NOT runnable
                "bench_l2norm.lib": True,        # MSVC import lib — NOT runnable
                "bench_l2norm.obj": True,        # MSVC object — NOT runnable
                "bench_l2norm.pdb": True,        # MSVC debug — NOT runnable
                "bench_l2norm.cpp": True,        # source — NOT runnable
                "bench_simsearch": True,         # valid Linux binary
                "bench_helper.dll": True,        # shared lib — NOT a bench
                "not_a_bench.exe": True,         # wrong prefix
            }
            for name, executable in files.items():
                p = build / name
                p.write_bytes(b"")
                if executable:
                    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            found = {p.name for p in _discover_cpp_benchmark_executables(build)}

        self.assertEqual(
            found,
            {"bench_l2norm.exe", "bench_simsearch"},
            msg=f"Expected only .exe + bare-name binaries, got {sorted(found)}",
        )

    def test_no_results_when_only_byproducts_present(self):
        """Earlier bug: every benchmark run silently produced 0 results
        because the runner tried to exec .exp/.lib files and they all
        failed. Discovery should now return [] so the caller can warn
        loudly instead of running a no-op."""
        with tempfile.TemporaryDirectory() as tmp:
            build = Path(tmp)
            for name in ("bench_a.exp", "bench_b.lib", "bench_c.obj", "bench_d.pdb"):
                (build / name).write_bytes(b"")
            self.assertEqual(_discover_cpp_benchmark_executables(build), [])


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
