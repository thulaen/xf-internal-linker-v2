"""Unit tests for the embedding quality gate (plan Part 9, FR-236).

Covers each decision branch with deterministic stub providers. No DB, no
AppSetting reads — the gate itself is stateless once constructed.
"""

from __future__ import annotations

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services.embedding_quality_gate import (
    GateDecision,
    QualityGate,
)


def _unit(vec: list[float]) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32)
    return arr / np.linalg.norm(arr)


class _StubProvider:
    """Returns a pre-set vector from embed_single; records call count."""

    def __init__(
        self, vector: np.ndarray, *, raise_exc: Exception | None = None
    ) -> None:
        self._vector = vector
        self._raise = raise_exc
        self.calls = 0

    def embed_single(self, text: str) -> np.ndarray:
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return self._vector


class GateBranchTests(SimpleTestCase):
    """One test per GateDecision path in evaluate()."""

    def test_gate0_accept_new_when_no_old_vector(self) -> None:
        gate = QualityGate()
        decision = gate.evaluate(
            text="hello",
            old_vec=None,
            old_sig="",
            new_vec=_unit([1.0, 0.0, 0.0]),
            new_sig="openai:text-embedding-3-small:1536",
        )
        self.assertEqual(decision.action, "ACCEPT_NEW")
        self.assertEqual(decision.reason, "first_embed")

    def test_gate1_reject_when_new_provider_ranks_lower(self) -> None:
        old_sig = "openai:text-embedding-3-large:3072"
        new_sig = "local:bge-m3:1024"
        ranking = {old_sig: 0.90, new_sig: 0.70}  # delta = -0.20, below -0.05 default
        gate = QualityGate(provider_ranking=ranking)
        decision = gate.evaluate(
            text="hello",
            old_vec=_unit([1.0, 0.0, 0.0]),
            old_sig=old_sig,
            new_vec=_unit([0.5, 0.5, 0.0]),
            new_sig=new_sig,
        )
        self.assertEqual(decision.action, "REJECT")
        self.assertEqual(decision.reason, "lower_quality_provider")
        self.assertLess(decision.score_delta, -0.05)

    def test_gate2_noop_when_vectors_effectively_identical(self) -> None:
        v = _unit([1.0, 0.0, 0.0])
        gate = QualityGate()
        decision = gate.evaluate(
            text="hello",
            old_vec=v,
            old_sig="local:bge-m3:1024",
            new_vec=v.copy(),
            new_sig="local:bge-m3:1024",
        )
        self.assertEqual(decision.action, "NOOP")
        self.assertEqual(decision.reason, "unchanged")
        self.assertGreater(decision.score_delta, 0.9999)

    def test_gate3_reject_when_resample_unstable(self) -> None:
        new_vec = _unit([1.0, 0.0, 0.0])
        sample2 = _unit([0.0, 1.0, 0.0])  # cos(new, sample2) = 0 << 0.99
        provider = _StubProvider(sample2)
        gate = QualityGate(provider=provider)
        decision = gate.evaluate(
            text="hello",
            old_vec=_unit([0.7, 0.7, 0.0]),
            old_sig="local:bge-m3:1024",
            new_vec=new_vec,
            new_sig="local:bge-m3:1024",
        )
        self.assertEqual(decision.action, "REJECT")
        self.assertEqual(decision.reason, "unstable_new_vector")
        self.assertEqual(provider.calls, 1)

    def test_gate_passes_all_gates_and_replaces(self) -> None:
        new_vec = _unit([0.6, 0.8, 0.0])
        sample2 = _unit([0.6, 0.8, 0.0])  # stable: cos = 1.0
        provider = _StubProvider(sample2)
        gate = QualityGate(provider=provider)
        decision = gate.evaluate(
            text="hello",
            old_vec=_unit([1.0, 0.0, 0.0]),
            old_sig="local:bge-m3:1024",
            new_vec=new_vec,
            new_sig="local:bge-m3:1024",
        )
        self.assertEqual(decision.action, "REPLACE")
        self.assertEqual(decision.reason, "passed_all_gates")
        self.assertEqual(provider.calls, 1)


class GateEdgeCaseTests(SimpleTestCase):
    """Behaviour under partial or degraded signals."""

    def test_replace_when_stability_sample_raises(self) -> None:
        provider = _StubProvider(
            np.zeros(3, dtype=np.float32),
            raise_exc=RuntimeError("provider down"),
        )
        gate = QualityGate(provider=provider)
        decision = gate.evaluate(
            text="hello",
            old_vec=_unit([1.0, 0.0, 0.0]),
            old_sig="local:bge-m3:1024",
            new_vec=_unit([0.6, 0.8, 0.0]),
            new_sig="local:bge-m3:1024",
        )
        self.assertEqual(decision.action, "REPLACE")
        self.assertEqual(decision.reason, "passed_without_stability_check")

    def test_reject_when_stability_sample_has_wrong_dimension(self) -> None:
        sample2 = _unit([1.0, 0.0, 0.0, 0.0])  # 4-dim vs 3-dim new_vec
        provider = _StubProvider(sample2)
        gate = QualityGate(provider=provider)
        decision = gate.evaluate(
            text="hello",
            old_vec=_unit([1.0, 0.0, 0.0]),
            old_sig="local:bge-m3:1024",
            new_vec=_unit([0.6, 0.8, 0.0]),
            new_sig="local:bge-m3:1024",
        )
        self.assertEqual(decision.action, "REJECT")
        self.assertEqual(decision.reason, "stability_dimension_mismatch")

    def test_replace_when_ranking_table_is_empty(self) -> None:
        new_vec = _unit([0.6, 0.8, 0.0])
        provider = _StubProvider(new_vec)
        gate = QualityGate(provider=provider)  # empty ranking → delta = 0.0
        decision = gate.evaluate(
            text="hello",
            old_vec=_unit([1.0, 0.0, 0.0]),
            old_sig="unknown_old",
            new_vec=new_vec,
            new_sig="unknown_new",
        )
        self.assertEqual(decision.action, "REPLACE")
        self.assertEqual(decision.score_delta, 0.0)

    def test_noop_threshold_is_strict_greater(self) -> None:
        v = _unit([1.0, 0.0, 0.0])
        gate = QualityGate(noop_cosine_threshold=0.9999)
        decision = gate.evaluate(
            text="hello",
            old_vec=v,
            old_sig="local:bge-m3:1024",
            new_vec=v.copy(),
            new_sig="local:bge-m3:1024",
        )
        self.assertEqual(decision.action, "NOOP")


class GateDecisionDataclassTests(SimpleTestCase):
    def test_decision_is_frozen_and_hashable(self) -> None:
        d = GateDecision("REPLACE", "passed_all_gates", 0.05)
        with self.assertRaises(Exception):
            d.action = "REJECT"  # type: ignore[misc]
        self.assertEqual(
            hash(d), hash(GateDecision("REPLACE", "passed_all_gates", 0.05))
        )
