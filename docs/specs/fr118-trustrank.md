# FR-118 — TrustRank

## Overview
On a forum some pages are operator-curated and known-good (sticky guides, official FAQs, mod-vetted reviews). TrustRank propagates trust from a small hand-picked seed set through the link graph using a biased PageRank, then prefers destinations that inherit high trust mass. This protects internal linking from spammy or thin-content threads sneaking into top-ranked suggestions. Complements FR-006 weighted PageRank because PageRank is undirected w.r.t. quality (any well-linked page rises) while TrustRank explicitly biases toward operator-trusted seeds.

## Academic source
**Gyöngyi, Z., Garcia-Molina, H., & Pedersen, J. (2004).** "Combating Web Spam with TrustRank." *Proceedings of the 30th VLDB Conference*, Toronto, Canada, pages 576-587. (No DOI; VLDB proceedings paper.)

## Formula
From Gyöngyi et al. (2004), Eq. 5 (the biased PageRank propagation, with `T` the row-normalised transition matrix and `d` the seed-distribution vector):

```
t_{k+1} = α · T · t_k + (1 - α) · d                   (Eq. 5)

Where:
    t ∈ ℝⁿ      = trust score vector, initialised to t_0 = d
    T ∈ ℝⁿˣⁿ    = column-stochastic transition matrix (T[i,j] = 1/out_degree(j) if j→i)
    d ∈ ℝⁿ      = seed vector, d[i] = 1/|S| if i ∈ S (trusted seeds), else 0
    α ∈ (0,1)   = damping factor, paper default 0.85
    |S|         = number of trusted seed pages
```

Iterate until `‖t_{k+1} - t_k‖₁ < ε`. The seed selection step (Section 4 of the paper) uses inverse-PageRank to pick high-out-degree authoritative pages, but for our forum we substitute operator-curated seeds. Convergence is guaranteed for `α < 1` because the contraction factor of `α · T` is `α`.

## Starting weight preset
```python
"trustrank.enabled": "true",
"trustrank.ranking_weight": "0.0",
"trustrank.damping": "0.85",
"trustrank.max_iterations": "100",
"trustrank.convergence_tolerance": "1e-7",
"trustrank.seed_source": "operator_curated",
```

## C++ implementation
- File: `backend/extensions/trustrank.cpp`
- Entry: `std::vector<float> trustrank(const int* edges_src, const int* edges_dst, int n_edges, int n_nodes, const int* seed_ids, int n_seeds, float damping, int max_iter, float tol)`
- Complexity: O(k · |E|) per iteration with sparse SpMV; typical k = 50-80 for tol=1e-7
- Thread-safety: stateless; uses Eigen sparse SpMV with float32 accumulators (paper uses float64, but float32 with Kahan summation matches within 1e-5)
- Builds via pybind11; releases GIL during iteration

## Python fallback
`backend/apps/pipeline/services/trustrank.py::compute_trustrank` using `networkx.pagerank(personalization=seed_dict)` which is mathematically equivalent to TrustRank Eq. 5 with the personalisation vector set to the seed distribution.

## Benchmark plan
| Graph size | C++ target | Python target |
|---|---|---|
| small (1K nodes, 8K edges, 10 seeds) | <10 ms | <80 ms |
| medium (10K nodes, 100K edges, 50 seeds) | <120 ms | <1.2 s |
| large (100K nodes, 1.5M edges, 200 seeds) | <2.5 s | <30 s |

## Diagnostics
- Raw trust value in suggestion detail UI (`trustrank_diagnostics.trust_score`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `convergence_iterations`, `seed_count`, `seed_proximity_hops` (BFS distance from destination to nearest seed), `final_l1_delta`

## Edge cases & neutral fallback
- Zero seeds configured → neutral 0.5 for all destinations, flag `neutral_no_seeds`
- Destination unreachable from any seed → trust score is exactly `0`; map to neutral 0.5 with flag `neutral_unreachable_from_seeds`
- Convergence failure (max_iter exhausted) → fallback 0.5, flag
- Dangling node handling: redistribute their trust uniformly over all nodes (paper Section 3.2 footnote)
- NaN/Inf clamping

## Minimum-data threshold
≥ 1 trusted seed configured AND destination must be in the same connected component as at least one seed; otherwise neutral 0.5.

## Budget
Disk: <2 MB  ·  RAM: <80 MB for a 100K-node graph (sparse adjacency + trust + seed vectors in float32)

## Scope boundary vs existing signals
- **FR-006 weighted PageRank**: uniform teleport vector; surfaces well-linked pages regardless of trust. TrustRank teleports only to seeds, propagating curated trust.
- **FR-021 Pixie random walk**: Pixie is a per-query short walk; TrustRank is a global biased-PageRank fixed-point.
- **FR-012 click distance**: click distance ignores trust; TrustRank uses link structure plus a curated seed set.

## Test plan bullets
- convergence test: paper's Figure 4 toy graph (8 nodes, 2 trusted seeds) → trust scores match Gyöngyi et al. Table 1 within 1e-4
- parity test: C++ vs `networkx.pagerank(personalization=...)` within 1e-5
- seed-monotonicity test: doubling the number of seeds whose neighbours include destination D never decreases D's trust score
- no-crash on adversarial input: zero seeds, all-seeds, isolated seed (singleton component), self-loops
- integration test: `ranking_weight = 0.0` leaves ordering unchanged
- determinism: identical edge list and seed list → identical scores
