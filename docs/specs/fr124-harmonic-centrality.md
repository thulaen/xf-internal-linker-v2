# FR-124 — Harmonic Centrality

## Overview
Closeness centrality (mean reciprocal distance to every other node) breaks on disconnected graphs because unreachable pairs give infinite distance. Harmonic centrality fixes this by summing reciprocals directly: unreachable nodes contribute zero. On a forum link graph this matters because graphs are routinely disconnected (categories that don't cross-link). Harmonic centrality cleanly surfaces destinations that are *globally close* to many other pages — strong "everyone references this" candidates. Complements FR-012 click distance because click distance is a single host-destination pair metric, while harmonic centrality is the destination's average closeness to *all* pages.

## Academic source
**Marchiori, M., & Latora, V. (2000).** "Harmony in the small-world." *Physica A: Statistical Mechanics and its Applications*, 285(3-4), 539-546. DOI: `10.1016/S0378-4371(00)00311-3`.

(Independently rediscovered and named "harmonic centrality" by Boldi & Vigna (2014). "Axioms for centrality." *Internet Mathematics*, 10(3-4), 222-262. DOI: `10.1080/15427951.2013.865686`.)

## Formula
From Marchiori & Latora (2000), Eq. 4 (the "efficiency" of a network), specialised to per-node centrality:

```
C_H(v) = (1 / (n - 1)) · Σ_{u ≠ v}  1 / d(u, v)             (harmonic centrality)

Where:
    d(u, v)   = shortest-path distance from u to v in the directed graph
                (= ∞ if no path exists, in which case 1/∞ ≡ 0 by convention)
    n         = total number of nodes
    C_H(v)    ∈ [0, 1] after normalisation by (n-1)
```

For weighted graphs `d(u, v)` is the weighted shortest path (Dijkstra). For unweighted, it is the BFS hop count. The 1/(n-1) normalisation factor makes scores comparable across graphs of different sizes.

Boldi & Vigna (2014) Theorem 1 proves harmonic centrality satisfies the four "centrality axioms" (size, density, score-monotonicity, rank-monotonicity) that closeness violates on disconnected graphs.

## Starting weight preset
```python
"harmonic_centrality.enabled": "true",
"harmonic_centrality.ranking_weight": "0.0",
"harmonic_centrality.weighted": "false",
"harmonic_centrality.bfs_depth_cap": "8",
```

## C++ implementation
- File: `backend/extensions/harmonic_centrality.cpp`
- Entry: `std::vector<float> harmonic_centrality(const int* edges_src, const int* edges_dst, int n_edges, int n_nodes, int weighted, int depth_cap)`
- Complexity: O(|V| · (|V| + |E|)) for full all-pairs BFS; we cap BFS at `depth_cap = 8` to make it O(|V| · |E_within_8_hops|) — typical forum diameters are 4-6 so this is exact for most pairs
- Thread-safety: per-source BFS is independent; OpenMP parallel over source nodes
- SIMD: not directly applicable (BFS is branch-heavy); compensate with bitset frontier representation for cache locality
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/harmonic_centrality.py::compute_harmonic_centrality` using `networkx.harmonic_centrality(G, distance=None)` for unweighted, `distance='weight'` for weighted.

## Benchmark plan
| Graph size | C++ target | Python target |
|---|---|---|
| small (1K nodes, 8K edges) | <30 ms | <300 ms |
| medium (10K nodes, 100K edges) | <800 ms | <12 s |
| large (100K nodes, 1.5M edges) | <30 s (parallel 16 cores) | <30 min |

## Diagnostics
- Raw harmonic centrality value in suggestion detail UI (`harmonic_diagnostics.harmonic_score`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `reachable_node_count` (how many nodes are within `depth_cap` of destination), `mean_path_length`, `depth_cap_used`, `unreachable_pair_count`

## Edge cases & neutral fallback
- Isolated node (no in-edges) → all `d(u, v) = ∞` → C_H = 0 → mapped to neutral 0.5 with flag `neutral_isolated_node`
- Disconnected graph → harmonic centrality handles it naturally (unreachable contribute 0); no special case needed
- BFS depth cap exceeded → contribution set to 0 (matches the "unreachable" convention); flag if cap was binding for >50% of source nodes
- No NaN/Inf risk; guard divisor `n-1 = 0` for trivial 1-node graphs

## Minimum-data threshold
Graph must have ≥ 10 nodes and the destination must be reachable from ≥ 5 source nodes within `depth_cap` hops; otherwise neutral 0.5.

## Budget
Disk: <2 MB  ·  RAM: <100 MB for a 100K-node graph (CSR adjacency + per-thread BFS frontier bitsets in 128-bit blocks)

## Scope boundary vs existing signals
- **FR-012 click distance**: click distance is the single host-destination pair shortest-path; harmonic centrality is the destination's average shortest-path to all sources. One per-pair, the other per-node aggregate.
- **FR-006 weighted PageRank**: PageRank is a random-walk stationary distribution; harmonic centrality is shortest-path-based. Disagree on graphs with many short cycles.
- **FR-116/117 HITS**: spectral; harmonic is geometric (path-based).
- **FR-122 Katz**: Katz counts all walks (attenuated); harmonic counts only shortest paths reciprocated. Katz can be inflated by long walks; harmonic cannot.

## Test plan bullets
- correctness test: 4-node path graph → analytical harmonic scores match formula exactly (within 1e-6)
- disconnected-graph test: two-component graph (5 + 5 nodes) → harmonic centrality computes per-component without infinity errors (closeness would crash here)
- depth-cap test: 12-hop chain with `depth_cap = 8` → expected score truncates correctly
- parity test: C++ vs `networkx.harmonic_centrality` within 1e-5 (and exact match when both use uncapped BFS)
- no-crash on adversarial input: self-loops, complete graph K_n, star graph, all-isolated nodes
- integration test: `ranking_weight = 0.0` leaves ordering unchanged
- determinism: identical edge list → identical scores
