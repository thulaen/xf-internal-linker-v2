# FR-116 — HITS Authority Score

## Overview
Forum link graphs have two distinct page roles: hubs (lists, indexes, sticky guides that point at many topical pages) and authorities (the pages those hubs point to). Plain PageRank (FR-006) blurs these roles. HITS authority scoring identifies destination pages that many hub-like pages converge on, which is a strong "this is the page readers expect to see linked" signal for internal linking. Complements FR-006 weighted PageRank because PageRank measures global random-walk mass, while HITS authority measures mutual-reinforcement specifically on the query/topic-induced subgraph.

## Academic source
**Kleinberg, J. M. (1999).** "Authoritative sources in a hyperlinked environment." *Journal of the ACM*, 46(5), 604-632. DOI: `10.1145/324133.324140`.

## Formula
From Kleinberg (1999), the authority score `a(p)` and hub score `h(p)` are mutually defined and computed by alternating updates on the adjacency matrix `A` of the focused subgraph:

```
a(p)   = Σ_{q : q→p} h(q)             (Eq. I, sum of hub scores of in-linkers)
h(p)   = Σ_{q : p→q} a(q)             (Eq. O, sum of authority scores of out-targets)

In matrix form:
    a_{k+1} = Aᵀ · h_k
    h_{k+1} = A   · a_{k+1}

Normalisation per iteration:
    ‖a_{k+1}‖₂ = 1
    ‖h_{k+1}‖₂ = 1
```

Where `A` is the n×n adjacency of the topic-induced subgraph (`A[q,p] = 1` if there is a directed edge `q → p`), `a, h ∈ ℝⁿ`, initialised to the uniform vector `1/√n`. Iterate until `‖a_{k+1} - a_k‖₂ < ε`. Convergence to the principal eigenvector of `AᵀA` is guaranteed by the Perron-Frobenius theorem when the subgraph is connected.

## Starting weight preset
```python
"hits_authority.enabled": "true",
"hits_authority.ranking_weight": "0.0",
"hits_authority.subgraph_size": "200",
"hits_authority.max_iterations": "50",
"hits_authority.convergence_tolerance": "1e-6",
```

## C++ implementation
- File: `backend/extensions/hits_authority.cpp`
- Entry: `std::vector<float> hits_authority(const int* edges_src, const int* edges_dst, int n_edges, int n_nodes, int max_iter, float tol)`
- Complexity: O(k · |E|) per iteration where k iterations until convergence, |E| = subgraph edges; typically k ≤ 50 for forum graphs
- Thread-safety: stateless; SIMD-friendly sparse matvec via `Eigen::SparseMatrix<float>` row iteration with `_mm256_fmadd_ps` accumulator
- Builds via pybind11; releases GIL during power iteration

## Python fallback
`backend/apps/pipeline/services/hits_authority.py::compute_authority_scores` using `networkx.hits` with `max_iter=50, tol=1e-6, normalized=True`.

## Benchmark plan
| Subgraph size | C++ target | Python target |
|---|---|---|
| small (50 nodes, 200 edges) | <2 ms | <15 ms |
| medium (500 nodes, 4K edges) | <25 ms | <250 ms |
| large (5K nodes, 50K edges) | <300 ms | <4 s |

## Diagnostics
- Raw authority value in suggestion detail UI (`hits_authority_diagnostics.authority_score`)
- C++/Python badge
- Fallback flag (`used_fallback: bool`)
- Signal-specific fields: `convergence_iterations`, `subgraph_node_count`, `subgraph_edge_count`, `final_l2_delta`

## Edge cases & neutral fallback
- Empty subgraph (no in-edges to destination) → neutral 0.5, flag `neutral_isolated_node`
- Disconnected subgraph → run on connected component containing destination; if singleton, neutral 0.5
- Convergence failure (k = max_iter, delta > tol) → fallback 0.5, flag `neutral_convergence_failure`
- NaN / Inf clamp on each iteration; abort to fallback if non-finite detected
- Self-loops removed before iteration (Kleinberg's original method ignores them)

## Minimum-data threshold
≥ 10 nodes and ≥ 20 edges in the topic-induced subgraph before the signal goes live; otherwise return neutral 0.5.

## Budget
Disk: <2 MB (compiled .pyd plus Eigen headers)  ·  RAM: <50 MB for a 5K-node subgraph (sparse adjacency + two score vectors in float32)

## Scope boundary vs existing signals
- **FR-006 weighted PageRank**: PageRank computes a single global eigenvector on the full graph with damped random teleport; HITS computes two coupled vectors on a topic-focused subgraph and surfaces destinations that hubs agree on. A page can have low PageRank but high HITS authority (small site, but hub-converged).
- **FR-021 Pixie random walk**: Pixie performs short personalised walks from a query node; HITS authority is a global eigenvector property of the subgraph independent of walk length.
- **FR-012 click distance**: click distance is a single-pair structural metric; HITS authority is a graph-wide centrality.

## Test plan bullets
- convergence test: 4-node hub-authority bipartite toy graph → authority scores match Kleinberg (1999) Figure 1 within 1e-4
- parity test: C++ vs Python within 1e-4 on a 100-node random graph (NetworkX `gnp_random_graph(100, 0.05)`)
- no-crash on adversarial input: self-loops only, isolated nodes, multi-edges (parallel edges collapsed before iteration)
- integration test: ranking unchanged when `ranking_weight = 0.0`
- determinism: same edge list produces identical scores across runs (deterministic L2 normalisation, no random init)
