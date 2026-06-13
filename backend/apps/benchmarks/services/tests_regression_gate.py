"""Tests for the diff-scoped performance-regression decision engine.

The scoring + file-mapping logic is pure (SimpleTestCase, no DB); the
evaluate()/AutoIssue paths seed BenchmarkRun/BenchmarkResult rows.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.benchmarks.models import BenchmarkResult, BenchmarkRun
from apps.benchmarks.services import regression_gate as rg


class ClassifyTests(SimpleTestCase):
    def test_clear_regression_blocks(self) -> None:
        kind, sev, conf, delta, base = rg.classify(150.0, [100.0] * 6)
        self.assertEqual(kind, "regression")
        self.assertGreater(delta, 0.4)
        self.assertGreater(conf, 0.5)

    def test_within_noise_is_ok(self) -> None:
        kind, *_ = rg.classify(103.0, [100.0, 101.0, 99.0, 100.0, 102.0])
        self.assertEqual(kind, "ok")

    def test_improvement_detected(self) -> None:
        kind, *_ = rg.classify(70.0, [100.0] * 6)
        self.assertEqual(kind, "improvement")

    def test_too_few_samples_is_ambiguous_warning(self) -> None:
        # Conservative: not enough history to judge -> warning (caller blocks).
        kind, sev, conf, *_ = rg.classify(100.0, [100.0])
        self.assertEqual(kind, "warning")
        self.assertLess(conf, 0.5)

    def test_severity_scales_with_delta(self) -> None:
        self.assertEqual(rg._severity_for_delta(0.6), "critical")
        self.assertEqual(rg._severity_for_delta(0.3), "high")
        self.assertEqual(rg._severity_for_delta(0.15), "medium")
        self.assertEqual(rg._severity_for_delta(0.05), "low")


class ImpactedFunctionsTests(SimpleTestCase):
    KNOWN = [("texttok", "tokenize"), ("pagerank", "pagerank_iter"), ("scoring", "score")]

    def test_maps_rust_kernel_dir_to_its_functions(self) -> None:
        hits = rg.impacted_functions(["rust/extensions/texttok/src/lib.rs"], self.KNOWN)
        self.assertIn(("texttok", "tokenize"), hits)
        self.assertNotIn(("pagerank", "pagerank_iter"), hits)

    def test_maps_python_bench_file_stem(self) -> None:
        hits = rg.impacted_functions(["backend/benchmarks/test_bench_scoring.py"], self.KNOWN)
        self.assertIn(("scoring", "score"), hits)

    def test_unrelated_file_maps_to_nothing(self) -> None:
        hits = rg.impacted_functions(["docs/README.md"], self.KNOWN)
        self.assertEqual(hits, set())


class EvaluateTests(TestCase):
    def _run(self, function_name="tokenize", extension="texttok", n_baseline=6, latest_ns=100):
        # Oldest..newest runs; latest gets latest_ns, the rest are the baseline.
        for i in range(n_baseline + 1):
            run = BenchmarkRun.objects.create(status="completed")
            BenchmarkRun.objects.filter(pk=run.pk).update(
                started_at=timezone.now() - timezone.timedelta(days=(n_baseline - i))
            )
            mean = latest_ns if i == n_baseline else 100
            BenchmarkResult.objects.create(
                run=run, language="rust", extension=extension,
                function_name=function_name, input_size="medium",
                mean_ns=mean, median_ns=mean,
            )

    def test_no_impacted_benchmark_passes(self) -> None:
        self._run()
        verdict = rg.evaluate(["docs/README.md"])
        self.assertEqual(verdict.decision, "pass")
        self.assertEqual(verdict.issues, [])

    def test_regression_in_impacted_function_blocks(self) -> None:
        self._run(latest_ns=160)  # 60% slower than the 100ns baseline
        verdict = rg.evaluate(["rust/extensions/texttok/src/lib.rs"])
        self.assertEqual(verdict.decision, "block")
        self.assertTrue(any(i.issue_type == "regression" for i in verdict.issues))
        self.assertEqual(verdict.as_dict()["summary"]["regressions_found"], 1)

    def test_stable_impacted_function_passes(self) -> None:
        self._run(latest_ns=101)  # within noise
        verdict = rg.evaluate(["rust/extensions/texttok/src/lib.rs"])
        self.assertEqual(verdict.decision, "pass")

    def test_thin_history_blocks_conservatively(self) -> None:
        self._run(n_baseline=1, latest_ns=100)  # only 1 baseline sample
        verdict = rg.evaluate(["rust/extensions/texttok/src/lib.rs"])
        self.assertEqual(verdict.decision, "block")
        self.assertTrue(any(i.issue_type == "warning" for i in verdict.issues))

    def test_verdict_json_shape(self) -> None:
        self._run(latest_ns=160)
        d = rg.evaluate(["rust/extensions/texttok/src/lib.rs"]).as_dict()
        self.assertEqual(set(d), {"decision", "scope", "issues", "summary"})
        self.assertEqual(set(d["scope"]), {"files_analyzed", "reason_for_scope"})
        issue = d["issues"][0]
        for key in ("issue_type", "severity", "affected_file", "metric",
                    "baseline_value", "current_value", "delta", "confidence",
                    "explanation", "recommendation"):
            self.assertIn(key, issue)


class AutoIssueEmissionTests(TestCase):
    def test_regression_files_a_deduped_autoissue(self) -> None:
        from apps.auto_issues.models import AutoIssue

        verdict = rg.Verdict(
            decision="block", files_analyzed=["x"], reason_for_scope="t",
            issues=[rg.Issue("regression", "high", "texttok.tokenize[medium]",
                             "latency_ns", 100.0, 160.0, 0.6, 0.8, "e", "r")],
        )
        n = rg.file_regression_autoissues(verdict, "abc123def456")
        self.assertEqual(n, 1)
        row = AutoIssue.objects.filter(title__startswith="[perf_regression]").first()
        self.assertIsNotNone(row)
        self.assertEqual(row.affected_files, ["texttok.tokenize[medium]"])
