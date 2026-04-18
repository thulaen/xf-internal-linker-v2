# FR-197 - Link-Farm Ring Detector

## Overview
A link farm is a tightly knit set of pages or sites that exchange reciprocal links to inflate each other's PageRank. In a forum graph the same pattern shows up as small clusters of threads or user pages that all link to each other and to almost nothing else. This signal finds strongly connected components (SCCs) in the *reciprocal* link sub-graph and scores each node by the size and density of the SCC it belongs to. Used as a bounded penalty component so candidates inside a detected ring fall in rank.

## Academic source
**Gyöngyi, Zoltán and Garcia-Molina, Hector (2005).** "Link Spam Alliances." *Proceedings of the 31st International Conference on Very Large Data Bases (VLDB 2005)*, pp. 517-528. Companion paper presented at AIRWeb 2005: "Web Spam Taxonomy", Stanford TR 2004-25. The SCC-based ring detection algorithm and reciprocity density metric used here are from §4 of the VLDB paper.

## Formula
Let `G = (V, E)` be the directed link graph among forum entities. Define the reciprocal sub-graph:
```
G_recip = (V, E_recip)        E_recip = { (u,v) : (u,v) ∈ E ∧ (v,u) ∈ E }
```
Compute strongly connected components `SCC(G_recip) = {S₁, S₂, …, S_k}` via Tarjan's algorithm.

For each node `u ∈ S_i`:
```
ring_size(u)        = |S_i|
ring_density(u)     = |E ∩ (S_i × S_i)| / (|S_i| · (|S_i| − 1))
ring_outflow(u)     = |{ (a,b) ∈ E : a ∈ S_i ∧ b ∉ S_i }|
ring_score(u)       = ring_density(u) · log(1 + ring_size(u)) · 1 / (1 + ring_outflow(u) / |S_i|)
```

Penalty mapped to `[0, 1]`:
```
ring_penalty(u) = 1 − exp(−λ · ring_score(u)),    λ = 0.8 (paper §5.2)
```

## Starting weight preset
```python
"link_farm.enabled": "true",
"link_farm.ranking_weight": "0.03",
"link_farm.min_scc_size": "3",
"link_farm.density_threshold": "0.6",
"link_farm.lambda": "0.8",
```

## C++ implementation
- File: `backend/extensions/link_farm_ring.cpp`
- Entry: `void detect_rings(const int* edges_src, const int* edges_dst, int n_edges, int n_nodes, int* out_scc_id, double* out_density);`
- Complexity: `O(|V| + |E|)` Tarjan SCC
- Thread-safety: pure function on read-only edge arrays
- Memory: stack-based Tarjan to keep RAM bounded
- Builds against pybind11; reuses graph adapter from FR-006

## Python fallback
`backend/apps/pipeline/services/link_farm.py::detect_rings(...)` — wraps `networkx.strongly_connected_components` for ad-hoc analysis.

## Benchmark plan
| Edges | C++ target | Python target |
|---|---|---|
| 1 K | < 1 ms | < 25 ms |
| 10 K | < 8 ms | < 250 ms |
| 100 K | < 80 ms | < 4 s |

## Diagnostics
- SCC ID per node, `ring_size`, `ring_density`, `ring_outflow`
- Histogram of SCC sizes
- Top-10 detected rings by `ring_score`
- Whether the detector ran during last graph rebuild

## Edge cases & neutral fallback
- Empty graph → neutral `0.0`, flag `empty_graph`
- Single node with no edges → `0.0`, flag `isolated`
- SCC of size 1 (self-loop or trivial) → `0.0`
- Whole graph is one SCC (small dev corpus) → cap `ring_size` at `0.1 · |V|`, flag `over_clustered`
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
SCC must have `≥ 3` nodes before it counts; below this returns neutral `0.0`.

## Budget
Disk: <1 MB  ·  RAM: <40 MB at 1 M edges (Tarjan stack + SCC ID array)

## Scope boundary vs existing signals
FR-197 does NOT overlap with FR-118 TrustRank or FR-119 AntiTrustRank — those propagate trust along the full graph. FR-197 looks at *local* reciprocal sub-graph topology. It is also distinct from FR-006 weighted link graph (which produces edge weights, not ring labels).

## Test plan bullets
- unit tests: 2-node mutual link, 3-node triangle, 5-node clique, no rings
- parity test: SCC ID list matches `networkx` exactly
- regression test: legitimate cross-link clusters (e.g. category landing pages) must not be flagged
- integration test: ranking unchanged when `ranking_weight = 0.0`
- timing test: 100 K edges within 80 ms in C++
- adversarial test: nested SCCs (ring inside a ring) must report the smaller inner ring with higher density
