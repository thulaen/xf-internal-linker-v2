"""Benchmarks for advanced graph signal precompute helpers."""

from __future__ import annotations

import pytest

from apps.graph.services.graph_signal_job import (
    _compute_icpc_degrees,
    _compute_sbma_blocks,
    _compute_tosd_lambdas,
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
