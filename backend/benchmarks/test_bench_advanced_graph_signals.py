"""Benchmarks for advanced graph signal precompute helpers."""

from __future__ import annotations

import pytest
import numpy as np

from apps.graph.services.graph_signal_job import (
    _compute_icpc_degrees,
    _compute_sbma_blocks,
    _compute_tosd_lambdas,
)
from apps.pipeline.services.advanced_graph_signals import (
    AdvancedGraphSignalsCaches,
    AdvancedGraphSignalsSettings,
    evaluate_advanced_graph_signals_batch,
)


def _icpc_inputs(size: int) -> tuple[list[tuple[int, int]], dict[int, int], dict[int, int]]:
    ids = list(range(size))
    id_to_idx = {node_id: node_id for node_id in ids}
    community_ids = {node_id: node_id // 50 for node_id in ids}
    edges = [
        (source_id, (source_id + offset) % size)
        for source_id in ids
        for offset in (1, 7, 13)
    ]
    return edges, id_to_idx, community_ids


@pytest.mark.benchmark(group="advanced-graph-icpc")
@pytest.mark.parametrize("size", [100, 1_000, 10_000])
def test_bench_icpc_degree_precompute(benchmark, size: int):
    edges, id_to_idx, community_ids = _icpc_inputs(size)

    local, global_ = benchmark(
        _compute_icpc_degrees,
        edges=edges,
        id_to_idx=id_to_idx,
        community_ids=community_ids,
        min_community_size=10,
    )

    assert len(global_) == size
    assert sum(global_.values()) == len(set(edges))
    assert sum(local.values()) > 0


@pytest.mark.benchmark(group="advanced-graph-sbma")
@pytest.mark.parametrize("size", [100, 1_000, 10_000])
def test_bench_sbma_block_precompute(benchmark, size: int):
    edges, id_to_idx, community_ids = _icpc_inputs(size)

    blocks, matrix = benchmark(
        _compute_sbma_blocks,
        edges=edges,
        id_to_idx=id_to_idx,
        community_ids=community_ids,
        num_blocks=20,
    )

    assert len(blocks) == size
    assert len(matrix) == 400
    assert matrix[(0, 0)] >= 0.0


@pytest.mark.benchmark(group="advanced-graph-tosd")
@pytest.mark.parametrize("size", [100, 1_000, 10_000])
def test_bench_tosd_lambda_precompute(benchmark, size: int):
    edges, id_to_idx, _community_ids = _icpc_inputs(size)

    lambdas = benchmark(
        _compute_tosd_lambdas,
        edges=edges,
        id_to_idx=id_to_idx,
    )

    assert len(lambdas) == size
    assert all(0.0 <= value <= 2.0 for value in lambdas.values())


class _RGSDBenchKernel:
    def evaluate_batch(self, spectral_scores, *_args):
        count = len(spectral_scores)
        zeros = np.zeros(count, dtype=np.float64)
        return {
            "score_tosd": zeros,
            "score_dstp": zeros,
            "score_icpc": zeros,
            "score_sbma": zeros,
            "score_rgsd": zeros,
            "score_csbr": zeros,
        }


def _rgsd_inputs(
    size: int,
) -> tuple[list[tuple[tuple[int, str], tuple[int, str]]], AdvancedGraphSignalsCaches]:
    pairs = [((idx, "thread"), (idx + size, "thread")) for idx in range(size)]
    node_to_index = {
        key: index
        for index, key in enumerate(key for pair in pairs for key in pair)
    }
    node_count = len(node_to_index)
    return pairs, AdvancedGraphSignalsCaches(
        node_to_index=node_to_index,
        spectral_scores=np.zeros(node_count, dtype=np.float64),
        transition_counts={},
        out_degrees=np.zeros(node_count, dtype=np.int32),
        local_degrees=np.zeros(node_count, dtype=np.int32),
        global_degrees=np.zeros(node_count, dtype=np.int32),
        block_probabilities={},
        flat_distances={},
        density_gradients=np.ones(node_count, dtype=np.float64),
        persona_matches={},
    )


@pytest.mark.benchmark(group="advanced-graph-rgsd")
@pytest.mark.parametrize("size", [100, 1_000, 10_000])
def test_bench_rgsd_semantic_distance_resolution(benchmark, monkeypatch, size: int):
    pairs, caches = _rgsd_inputs(size)
    settings = AdvancedGraphSignalsSettings()
    semantic_scores = [0.8] * size
    monkeypatch.setattr(
        "apps.pipeline.services.advanced_graph_signals.load_kernel",
        lambda *_args: _RGSDBenchKernel(),
    )

    evaluations = benchmark(
        evaluate_advanced_graph_signals_batch,
        pairs,
        caches,
        settings,
        [False] * size,
        semantic_scores=semantic_scores,
    )

    assert len(evaluations) == size
