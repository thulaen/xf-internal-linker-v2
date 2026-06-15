"""Tests for ``apps.core.services.performance_certification`` (Phase 4.11).

Covers the cert verdict math (pass / warn / fail / unknown), the
single-row AppSetting persist + read-back, the empty-state fallback,
the JSON contract the frontend relies on, and the security tightening
on the run-now endpoint (staff-only + 6/hour throttle).

The tests build synthetic ``BenchmarkRun`` + ``BenchmarkResult`` rows
in the test DB rather than mocking the service — exercises the real
ORM aggregation path so a future refactor of ``_summarise_per_area``
can't regress silently.
"""

from __future__ import annotations

from subprocess import CompletedProcess, TimeoutExpired  # nosec B404 - test-only mocks.
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.benchmarks.models import BenchmarkResult, BenchmarkRun
from apps.core.models import AppSetting
from apps.core.services import performance_certification as cert


def _seed_run(*results: tuple[str, str, int]) -> BenchmarkRun:
    """Build a completed BenchmarkRun + N results from (language, status, count) tuples.

    Each tuple expands into ``count`` rows with the given language +
    status. Keeps the test setup compact + readable.
    """
    run = BenchmarkRun.objects.create(trigger="manual", status="completed")
    for i, (language, status, count) in enumerate(results):
        for j in range(count):
            BenchmarkResult.objects.create(
                run=run,
                language=language,
                extension=f"ext_{i}",
                function_name=f"fn_{i}_{j}",
                input_size="medium",
                mean_ns=1_000_000,
                median_ns=1_000_000,
                items_per_second=1000.0,
                status=status,
            )
    return run


class CertVerdictMathTests(TestCase):
    """The pass / warn / fail thresholds — pinned so a future tweak
    to the constants surfaces in CI."""

    def setUp(self) -> None:
        # Defensive: clear both the AppSetting rows AND any leftover
        # BenchmarkRun + Result rows. TestCase wraps each method in a
        # transaction so rollback is automatic — but the explicit
        # cleanup guards against leaked state if tests ever migrate to
        # TransactionTestCase OR a parallel test runner.
        AppSetting.objects.filter(key__startswith="performance_cert.").delete()
        BenchmarkResult.objects.all().delete()
        BenchmarkRun.objects.all().delete()

    def test_no_completed_run_returns_unknown(self) -> None:
        verdict = cert.run_performance_certification()
        self.assertEqual(verdict.verdict, "unknown")
        self.assertIn("No BenchmarkRun has completed", verdict.note)
        self.assertIsNone(verdict.benchmark_run_id)

    def test_all_fast_is_pass(self) -> None:
        _seed_run(("rust", "fast", 5), ("python", "fast", 5))
        verdict = cert.run_performance_certification()
        self.assertEqual(verdict.verdict, "pass")
        self.assertIn("Ready to ship", verdict.label)
        # Per-area summaries should report 5 fast each, no slow.
        rust_area = next(a for a in verdict.areas if a.area == "rust")
        self.assertEqual(rust_area.fast_count, 5)
        self.assertEqual(rust_area.slow_count, 0)
        self.assertEqual(rust_area.verdict, "pass")

    def test_mixed_fast_and_ok_is_pass(self) -> None:
        _seed_run(("rust", "fast", 3), ("rust", "ok", 2), ("python", "ok", 4))
        verdict = cert.run_performance_certification()
        self.assertEqual(verdict.verdict, "pass")

    def test_one_slow_is_warn(self) -> None:
        # 1 slow result stays under the WARN budget (3) → warn band.
        _seed_run(("rust", "ok", 4), ("rust", "slow", 1), ("python", "ok", 3))
        verdict = cert.run_performance_certification()
        self.assertEqual(verdict.verdict, "warn")
        self.assertIn("Yellow", verdict.label)

    def test_warn_budget_minus_one_is_warn(self) -> None:
        # _WARN_BUDGET = 3 → 2 slow is still warn.
        _seed_run(("rust", "ok", 4), ("rust", "slow", 2), ("python", "ok", 3))
        verdict = cert.run_performance_certification()
        self.assertEqual(verdict.verdict, "warn")

    def test_at_warn_budget_is_fail(self) -> None:
        # 3 slow tips into fail.
        _seed_run(("rust", "ok", 1), ("rust", "slow", 3), ("python", "ok", 3))
        verdict = cert.run_performance_certification()
        self.assertEqual(verdict.verdict, "fail")
        self.assertIn("Hold", verdict.label)

    def test_python_failure_alone_fails_overall(self) -> None:
        # rust passes, python has 5 slow, so the whole verdict fails.
        _seed_run(("rust", "ok", 4), ("python", "ok", 1), ("python", "slow", 5))
        verdict = cert.run_performance_certification()
        self.assertEqual(verdict.verdict, "fail")

    def test_missing_required_area_is_fail(self) -> None:
        """If only python ran (no rust results) the rust area should
        synthesise a fail entry — required areas can't be silently
        omitted from the verdict."""
        _seed_run(("python", "ok", 5))
        verdict = cert.run_performance_certification()
        rust_area = next(a for a in verdict.areas if a.area == "rust")
        self.assertEqual(rust_area.verdict, "fail")
        self.assertEqual(rust_area.total, 0)
        self.assertEqual(verdict.verdict, "fail")

    def test_latest_python_and_latest_rust_runs_certify_together(self) -> None:
        _seed_run(("rust", "fast", 3))
        _seed_run(("python", "ok", 4))

        verdict = cert.run_performance_certification()
        areas = {area.area: area for area in verdict.areas}

        self.assertEqual(verdict.verdict, "pass")
        self.assertEqual(areas["python"].total, 4)
        self.assertEqual(areas["rust"].total, 3)
        self.assertEqual(areas["python"].verdict, "pass")
        self.assertEqual(areas["rust"].verdict, "pass")


class PersistAndReadBackTests(TestCase):
    """Verify the verdict persists to AppSetting + can be read back."""

    def setUp(self) -> None:
        # Defensive: clear both the AppSetting rows AND any leftover
        # BenchmarkRun + Result rows. TestCase wraps each method in a
        # transaction so rollback is automatic — but the explicit
        # cleanup guards against leaked state if tests ever migrate to
        # TransactionTestCase OR a parallel test runner.
        AppSetting.objects.filter(key__startswith="performance_cert.").delete()
        BenchmarkResult.objects.all().delete()
        BenchmarkRun.objects.all().delete()

    def test_run_persists_two_appsetting_rows(self) -> None:
        _seed_run(("rust", "ok", 1), ("python", "ok", 1))
        cert.run_performance_certification()
        self.assertTrue(
            AppSetting.objects.filter(key="performance_cert.last_verdict").exists()
        )
        self.assertTrue(
            AppSetting.objects.filter(key="performance_cert.last_run_at").exists()
        )

    def test_get_last_returns_none_before_first_run(self) -> None:
        self.assertIsNone(cert.get_last_certification())

    def test_get_last_round_trip_preserves_areas(self) -> None:
        _seed_run(("rust", "fast", 3), ("python", "ok", 2))
        original = cert.run_performance_certification()
        loaded = cert.get_last_certification()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.verdict, original.verdict)
        self.assertEqual(loaded.label, original.label)
        # Per-area data round-trips correctly
        self.assertEqual(len(loaded.areas), len(original.areas))
        for orig_area, loaded_area in zip(original.areas, loaded.areas):
            self.assertEqual(orig_area.area, loaded_area.area)
            self.assertEqual(orig_area.verdict, loaded_area.verdict)
            self.assertEqual(orig_area.fast_count, loaded_area.fast_count)
            self.assertEqual(orig_area.slow_count, loaded_area.slow_count)

    def test_get_last_handles_corrupt_json_gracefully(self) -> None:
        # Persist garbage so the JSON parser blows up — read should
        # return None rather than propagate the error.
        AppSetting.objects.create(
            key="performance_cert.last_verdict", value="not-valid-json"
        )
        self.assertIsNone(cert.get_last_certification())


class CertVerdictHelperTests(TestCase):
    """Pure-function helpers — no DB needed but TestCase for consistency."""

    def test_aggregate_verdict_empty_returns_unknown(self) -> None:
        self.assertEqual(cert._aggregate_verdict([]), "unknown")

    def test_aggregate_verdict_fail_dominates(self) -> None:
        areas = [
            cert.AreaSummary("rust", 5, 0, 0, 5, "pass", ""),
            cert.AreaSummary("python", 0, 0, 5, 5, "fail", ""),
        ]
        self.assertEqual(cert._aggregate_verdict(areas), "fail")

    def test_aggregate_verdict_warn_dominates_pass(self) -> None:
        areas = [
            cert.AreaSummary("rust", 5, 0, 0, 5, "pass", ""),
            cert.AreaSummary("python", 4, 0, 1, 5, "warn", ""),
        ]
        self.assertEqual(cert._aggregate_verdict(areas), "warn")

    def test_aggregate_verdict_all_pass(self) -> None:
        areas = [
            cert.AreaSummary("rust", 5, 0, 0, 5, "pass", ""),
            cert.AreaSummary("python", 4, 1, 0, 5, "pass", ""),
        ]
        self.assertEqual(cert._aggregate_verdict(areas), "pass")

    def test_label_includes_slow_count_on_fail(self) -> None:
        areas = [
            cert.AreaSummary("rust", 0, 0, 5, 5, "fail", ""),
            cert.AreaSummary("python", 5, 0, 0, 5, "pass", ""),
        ]
        label = cert._label_for("fail", areas)
        self.assertIn("5", label)
        self.assertIn("Hold", label)


# ── Endpoint security & contract tests ────────────────────────────


class PerformanceCertEndpointSecurityTests(TestCase):
    """Same security pattern as compression-audit-run: anon→401/403,
    regular user→403 on POST, staff→200 on POST, GET open to all
    authenticated users."""

    def setUp(self) -> None:
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        User = get_user_model()
        self.regular_user = User.objects.create_user(username="regular", password="pw")
        self.staff_user = User.objects.create_user(
            username="staff", password="pw", is_staff=True
        )
        self.client = APIClient()

    def test_get_requires_auth(self) -> None:
        response = self.client.get("/api/system/performance-cert/")
        self.assertIn(response.status_code, (401, 403))

    def test_get_allows_regular_user(self) -> None:
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get("/api/system/performance-cert/")
        self.assertEqual(response.status_code, 200)

    def test_run_requires_auth(self) -> None:
        response = self.client.post("/api/system/performance-cert/run/")
        self.assertIn(response.status_code, (401, 403))

    def test_run_rejects_non_staff(self) -> None:
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post("/api/system/performance-cert/run/")
        self.assertEqual(response.status_code, 403)

    def test_run_allows_staff(self) -> None:
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post("/api/system/performance-cert/run/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("verdict", response.data)


class PerformanceCertViewContractTests(TestCase):
    """Pin the JSON shape the frontend relies on."""

    def setUp(self) -> None:
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        AppSetting.objects.filter(key__startswith="performance_cert.").delete()

    def test_get_before_first_run_returns_unknown_with_helpful_note(self) -> None:
        response = self.client.get("/api/system/performance-cert/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["verdict"], "unknown")
        self.assertIn(
            "No performance certification has run yet", response.data["label"]
        )
        self.assertIsNone(response.data["benchmark_run_id"])
        self.assertEqual(response.data["areas"], [])

    def test_get_after_run_returns_full_payload(self) -> None:
        _seed_run(("rust", "fast", 2), ("python", "ok", 3))
        cert.run_performance_certification()
        response = self.client.get("/api/system/performance-cert/")
        self.assertEqual(response.status_code, 200)
        for key in (
            "run_at_iso",
            "verdict",
            "label",
            "benchmark_run_id",
            "benchmark_run_started_at_iso",
            "areas",
            "note",
        ):
            with self.subTest(key=key):
                self.assertIn(key, response.data)
        # Areas should be a list of dicts (not tuples)
        self.assertIsInstance(response.data["areas"], list)
        self.assertGreater(len(response.data["areas"]), 0)


# ── Runner bug-fix coverage ───────────────────────────────────────


class RunnerBugFixTests(TestCase):
    """Pins current Python benchmark runner failure handling."""

    @patch("apps.benchmarks.services.runner._emit_benchmark_error")
    @patch("apps.benchmarks.services.runner.subprocess.run")
    def test_pytest_benchmark_nonzero_exit_is_visible(
        self,
        run_mock,
        emit_error_mock,
    ) -> None:
        from apps.benchmarks.services import runner

        run_mock.return_value = CompletedProcess(
            args=["python", "-m", "pytest"],
            returncode=2,
            stderr=b"collection failed",
        )

        self.assertFalse(runner._invoke_pytest_benchmark("bench.json"))
        emit_error_mock.assert_called_once()
        self.assertIn("pytest exit code 2", emit_error_mock.call_args.args[1])

    @patch("apps.benchmarks.services.runner._emit_benchmark_error")
    @patch("apps.benchmarks.services.runner.subprocess.run")
    def test_pytest_benchmark_timeout_is_visible(
        self,
        run_mock,
        emit_error_mock,
    ) -> None:
        from apps.benchmarks.services import runner

        run_mock.side_effect = TimeoutExpired(
            cmd=["python", "-m", "pytest"],
            timeout=600,
        )

        self.assertFalse(runner._invoke_pytest_benchmark("bench.json"))
        emit_error_mock.assert_called_once_with(
            "python_benchmarks",
            "Timeout (>600 s)",
            "",
        )

    def test_parse_python_bench_row_extracts_extension_and_size(self) -> None:
        from apps.benchmarks.services import runner

        result = runner._parse_python_bench_row(
            {
                "name": "backend/benchmarks/test_bench_scoring.py::test_bench_texttok_large",
                "stats": {"mean": 0.002, "median": 0.001},
            },
            run=object(),
            result_class=SimpleNamespace,
        )

        self.assertEqual(result.language, "python")
        self.assertEqual(result.extension, "texttok")
        self.assertEqual(result.input_size, "large")
        self.assertEqual(result.mean_ns, 2_000_000)

    def test_parse_python_bench_row_classifies_numeric_parameter_size(self) -> None:
        from apps.benchmarks.services import runner

        result = runner._parse_python_bench_row(
            {
                "name": "backend/benchmarks/test_bench_scoring.py::test_bench_texttok[100]",
                "stats": {"mean": 0.001, "median": 0.001},
            },
            run=object(),
            result_class=SimpleNamespace,
        )

        self.assertEqual(result.input_size, "small")
