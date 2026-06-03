"""Exact-value tests for the per-endpoint rate throttles.

Each throttle is a thin DRF ``UserRateThrottle`` subclass whose only
contract is its ``scope`` name and ``rate`` string. A wrong scope means
two endpoints silently share one counter; a wrong rate means the limit
is looser or tighter than the docstring promises. These assert the
exact pair for every throttle so a mutation to either string fails.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from rest_framework.throttling import UserRateThrottle

from apps.api import throttles


class ThrottleScopeAndRateTests(SimpleTestCase):
    """Lock the exact (scope, rate) pair of every throttle class."""

    def test_when_graph_rebuild_then_scope_and_rate_exact(self) -> None:
        self.assertEqual(throttles.GraphRebuildThrottle.scope, "graph_rebuild")
        self.assertEqual(throttles.GraphRebuildThrottle.rate, "6/hour")

    def test_when_weight_recalc_then_scope_and_rate_exact(self) -> None:
        self.assertEqual(throttles.WeightRecalcThrottle.scope, "weight_recalc")
        self.assertEqual(throttles.WeightRecalcThrottle.rate, "12/hour")

    def test_when_cooccurrence_then_scope_and_rate_exact(self) -> None:
        self.assertEqual(
            throttles.CoOccurrenceComputeThrottle.scope, "cooccurrence_compute"
        )
        self.assertEqual(throttles.CoOccurrenceComputeThrottle.rate, "6/hour")

    def test_when_import_trigger_then_scope_and_rate_exact(self) -> None:
        self.assertEqual(throttles.ImportTriggerThrottle.scope, "import_trigger")
        self.assertEqual(throttles.ImportTriggerThrottle.rate, "2/minute")

    def test_when_ml_embed_then_scope_and_rate_exact(self) -> None:
        self.assertEqual(throttles.MLEmbedThrottle.scope, "ml_embed")
        self.assertEqual(throttles.MLEmbedThrottle.rate, "5/minute")

    def test_when_challenger_eval_then_scope_and_rate_exact(self) -> None:
        self.assertEqual(throttles.ChallengerEvalThrottle.scope, "challenger_eval")
        self.assertEqual(throttles.ChallengerEvalThrottle.rate, "1/minute")

    def test_when_settings_write_then_scope_and_rate_exact(self) -> None:
        self.assertEqual(throttles.SettingsWriteThrottle.scope, "settings_write")
        self.assertEqual(throttles.SettingsWriteThrottle.rate, "10/minute")

    def test_when_compression_audit_then_scope_and_rate_exact(self) -> None:
        self.assertEqual(
            throttles.CompressionAuditRunThrottle.scope, "compression_audit_run"
        )
        self.assertEqual(throttles.CompressionAuditRunThrottle.rate, "3/hour")

    def test_when_benchmark_run_then_scope_and_rate_exact(self) -> None:
        self.assertEqual(
            throttles.BenchmarkRunTriggerThrottle.scope, "benchmark_run_trigger"
        )
        self.assertEqual(throttles.BenchmarkRunTriggerThrottle.rate, "2/hour")

    def test_when_performance_cert_then_scope_and_rate_exact(self) -> None:
        self.assertEqual(
            throttles.PerformanceCertRunThrottle.scope, "performance_cert_run"
        )
        self.assertEqual(throttles.PerformanceCertRunThrottle.rate, "6/hour")


class ThrottleStructureTests(SimpleTestCase):
    """Structural guarantees shared by every throttle in the module."""

    _ALL = (
        throttles.GraphRebuildThrottle,
        throttles.WeightRecalcThrottle,
        throttles.CoOccurrenceComputeThrottle,
        throttles.ImportTriggerThrottle,
        throttles.MLEmbedThrottle,
        throttles.ChallengerEvalThrottle,
        throttles.SettingsWriteThrottle,
        throttles.CompressionAuditRunThrottle,
        throttles.BenchmarkRunTriggerThrottle,
        throttles.PerformanceCertRunThrottle,
    )

    def test_when_each_throttle_then_subclasses_user_rate_throttle(self) -> None:
        for cls in self._ALL:
            with self.subTest(cls=cls.__name__):
                self.assertTrue(issubclass(cls, UserRateThrottle))

    def test_when_all_throttles_then_scopes_are_unique(self) -> None:
        scopes = [cls.scope for cls in self._ALL]
        self.assertEqual(len(scopes), len(set(scopes)))

    def test_when_all_throttles_then_exactly_ten_classes(self) -> None:
        self.assertEqual(len(self._ALL), 10)
