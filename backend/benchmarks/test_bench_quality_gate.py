"""Benchmarks for the measure-twice quality gate (plan Part 9, FR-236).

Three input sizes exercise the gate at the three supported vector dimensions.
The provider passed to ``QualityGate`` is a stub that returns a deterministic
re-sample so the benchmark measures gate arithmetic only — not API latency.
"""

from __future__ import annotations

import numpy as np
import pytest


def _import_gate():
    from apps.pipeline.services.embedding_quality_gate import (
        GateDecision,
        QualityGate,
    )

    return GateDecision, QualityGate


class _StubProvider:
    """Deterministic in-memory provider for the stability re-sample step."""

    def __init__(self, dim: int) -> None:
        self._dim = dim
        rng = np.random.default_rng(0)
        self._vec = rng.standard_normal(dim).astype(np.float32)
        self._vec /= np.linalg.norm(self._vec)

    def embed_single(self, text: str) -> np.ndarray:
        return self._vec


def _inputs(dim: int):
    rng = np.random.default_rng(42)
    old = rng.standard_normal(dim).astype(np.float32)
    old /= np.linalg.norm(old)
    new = rng.standard_normal(dim).astype(np.float32)
    new /= np.linalg.norm(new)
    return old, new


@pytest.mark.parametrize("dim", [1024])
def test_bench_gate_small_dim(benchmark, dim):
    _, QualityGate = _import_gate()
    provider = _StubProvider(dim)
    old_vec, new_vec = _inputs(dim)
    gate = QualityGate(
        provider_ranking={
            "local:BAAI/bge-m3:1024": 0.7,
            "openai:text-embedding-3-small:1536": 0.8,
        },
        provider=provider,
    )
    benchmark(
        gate.evaluate,
        text="hello world",
        old_vec=old_vec,
        old_sig="local:BAAI/bge-m3:1024",
        new_vec=new_vec,
        new_sig="openai:text-embedding-3-small:1536",
    )


@pytest.mark.parametrize("dim", [1536])
def test_bench_gate_medium_dim(benchmark, dim):
    _, QualityGate = _import_gate()
    provider = _StubProvider(dim)
    old_vec, new_vec = _inputs(dim)
    gate = QualityGate(provider=provider)
    benchmark(
        gate.evaluate,
        text="hello world",
        old_vec=old_vec,
        old_sig="openai:text-embedding-3-small:1536",
        new_vec=new_vec,
        new_sig="openai:text-embedding-3-small:1536",
    )


@pytest.mark.parametrize("dim", [3072])
def test_bench_gate_large_dim(benchmark, dim):
    _, QualityGate = _import_gate()
    provider = _StubProvider(dim)
    old_vec, new_vec = _inputs(dim)
    gate = QualityGate(provider=provider)
    benchmark(
        gate.evaluate,
        text="hello world",
        old_vec=old_vec,
        old_sig="openai:text-embedding-3-large:3072",
        new_vec=new_vec,
        new_sig="openai:text-embedding-3-large:3072",
    )
