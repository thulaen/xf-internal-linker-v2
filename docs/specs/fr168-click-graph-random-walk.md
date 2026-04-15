# FR-168 — Click-Graph Random Walk (Click-PageRank)

## Overview
Build a bipartite query→document graph weighted by click counts; run a biased random walk (PageRank with restart) to propagate relevance from frequently-clicked (q,d) pairs to similar nearby pairs. Surfaces destinations that share click neighbourhoods with high-relevance ones — handles long-tail query rewriting for free. Complements `fr025-session-cooccurrence-collaborative-filtering-behavioral-hubs` because that signal uses session-level co-occurrence while this signal uses query-doc click bipartite structure.

## Academic source
Full citation: **Craswell, N. & Szummer, M. (2007).** "Random Walks on the Click Graph." *Proceedings of the 30th ACM SIGIR Conference on Research and Development in Information Retrieval*, pp. 239-246. DOI: `10.1145/1277741.1277810`.

## Formula
Craswell & Szummer (2007), Equation 1 (transition matrix) and Equation 4 (random-walk relevance):

```
T_{q→d} = w_{q,d} / Σ_{d'} w_{q,d'}      (normalised forward transition)
T_{d→q} = w_{q,d} / Σ_{q'} w_{q',d}      (normalised backward transition)

p_{t+1} = (1 − ε) · T · p_t  +  ε · p_0   (restart prior)

R(q, d) = lim_{t→∞} p_t(d)            (stationary distribution given query q seed)

where
  w_{q,d} = click count for (q, d)
  ε       = restart probability (typical 0.15)
  p_0     = restart distribution (uniform over query node)
```

Number of walk steps t typically 4-6; per Craswell & Szummer §3 longer walks add little signal but cost more CPU.

## Starting weight preset
```python
"click_walk.enabled": "true",
"click_walk.ranking_weight": "0.0",
"click_walk.restart_prob": "0.15",
"click_walk.walk_steps": "5",
```

## C++ implementation
- File: `backend/extensions/click_graph_walk.cpp`
- Entry: `std::vector<float> click_walk_relevance(const SparseClickGraph& g, uint32_t seed_query, int steps, double restart_prob)`
- Complexity: O(steps · |E|) where |E| = nonzero click edges; sparse CSR storage
- Thread-safety: graph is const-shared; walk vector is per-call
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/click_walk.py::compute_click_walk` using `scipy.sparse.csr_matrix` and `@` operator.

## Benchmark plan

| Size | Edges | C++ target | Python target |
|---|---|---|---|
| Small | 10k | 1 ms | 50 ms |
| Medium | 1M | 80 ms | 2 s |
| Large | 100M | 8 s | 3 min |

## Diagnostics
- Per-(q,d) walk-rank shown in suggestion detail
- Top-10 graph neighbours of query in debug payload
- C++/Python badge
- Fallback flag
- Debug fields: `walk_steps_used`, `convergence_delta`

## Edge cases & neutral fallback
- Query with no clicks → seed cannot enter graph → fallback neutral 0.5
- Disconnected graph component → walk stays in component (correct)
- Self-loops removed during graph construction
- Zero-weight edges pruned

## Minimum-data threshold
Query must have at least 5 distinct clicked documents before walk seed is published.

## Budget
Disk: 100 MB sparse CSR  ·  RAM: 500 MB during walk for largest graph tier

## Scope boundary vs existing signals
Distinct from `fr025-session-cooccurrence-collaborative-filtering-behavioral-hubs` (session-bipartite) and `fr033-internal-pagerank-heatmap` (link-graph PageRank, not click-graph). This is the only signal that propagates relevance through click-derived edges.

## Test plan bullets
- Unit: 2-node graph (q→d) with weight 1 returns p(d) ≈ 1
- Unit: 4-node line graph distributes mass per Craswell & Szummer §4 example
- Parity: C++ vs Python within 1e-5 (FP rounding from sparse mat-vec)
- Edge: empty graph returns empty result
- Edge: query absent from graph returns fallback flag
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
