# FR-121 — SimRank

## Overview
On a forum, two threads are similar if they are linked-from by similar threads. SimRank captures this recursive intuition: similarity propagates along incoming links. For internal linking, SimRank gives a host-to-destination "structural twin" score that is independent of text — useful when text similarity (FR-002 semantic) is weak or noisy but the link graph clearly groups the two pages. Complements FR-021 Pixie random walk because Pixie measures personalised proximity (one-sided, host-rooted) while SimRank is symmetric and captures bilateral structural equivalence.

## Academic source
**Jeh, G., & Widom, J. (2002).** "SimRank: A Measure of Structural-Context Similarity." *Proceedings of the 8th ACM SIGKDD International Conference on Knowledge Discovery and Data Mining (KDD 2002)*, Edmonton, Alberta, pages 538-543. DOI: `10.1145/775047.775126`.

## Formula
From Jeh & Widom (2002), Eq. 3 (the recursive SimRank definition):

```
s(a, b) = 1                                          if a = b

s(a, b) = (C / (|I(a)| · |I(b)|)) ·
          Σ_{i=1}^{|I(a)|} Σ_{j=1}^{|I(b)|} s(I_i(a), I_j(b))      if a ≠ b
                                                              and |I(a)|·|I(b)| > 0

s(a, b) = 0                                          if |I(a)| = 0 or |I(b)| = 0

Where:
    I(x)        = set of in-neighbours of node x in the directed graph
    I_i(x)      = the i-th in-neighbour of x (under any fixed enumeration)
    C ∈ (0,1)   = decay factor, paper default C = 0.8
    s(a,b)      ∈ [0, 1] (proven in Theorem 4.1)
```

Solved iteratively (paper Algorithm 1):
```
s_0(a,b) = 1 if a=b else 0
s_{k+1}(a,b) = (C / (|I(a)|·|I(b)|)) · Σ Σ s_k(I_i(a), I_j(b))
```

Converges as k → ∞; paper's Theorem 4.2 shows monotone convergence within `O((1-C)^k)`. Practical iteration: k = 5 gives error < 5%.

## Starting weight preset
```python
"simrank.enabled": "true",
"simrank.ranking_weight": "0.0",
"simrank.decay_C": "0.8",
"simrank.max_iterations": "5",
"simrank.candidate_pair_cap": "10000",
```

## C++ implementation
- File: `backend/extensions/simrank.cpp`
- Entry: `std::vector<float> simrank_pairs(const int* edges_src, const int* edges_dst, int n_edges, int n_nodes, const int* query_pairs, int n_pairs, float C, int max_iter)` — computes only the requested (host, candidate) pairs not the full n×n matrix
- Complexity: O(k · |Q| · d̄²) where |Q| is the query-pair count, d̄ is the mean in-degree. Full-matrix SimRank is O(k·n²·d̄²) and infeasible for large graphs; we always restrict to candidate pairs.
- Thread-safety: stateless; per-pair computation is independent and parallelisable via OpenMP
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/simrank.py::compute_simrank_pairs` using `networkx.simrank_similarity` (which only supports node-pair queries via `source` and `target` kwargs).

## Benchmark plan
| Pairs queried | Graph size | C++ target | Python target |
|---|---|---|---|
| small (10 pairs) | 1K nodes | <5 ms | <80 ms |
| medium (200 pairs) | 10K nodes | <80 ms | <2 s |
| large (5K pairs) | 100K nodes | <2 s | <60 s |

## Diagnostics
- Raw SimRank value in suggestion detail UI (`simrank_diagnostics.simrank_score`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `iterations_used`, `host_in_degree`, `candidate_in_degree`, `shared_in_neighbour_count` (overlap of `I(host) ∩ I(candidate)` — useful sanity check)

## Edge cases & neutral fallback
- Either node has zero in-neighbours → s = 0 by definition → mapped to neutral 0.5 with flag `neutral_no_in_neighbours`
- Self-pair (host = candidate) → s = 1.0 by definition; map to score 0.5 (we never link a page to itself, so this is meaningless)
- Disconnected pair (no path of in-neighbours) → s converges to 0 → neutral 0.5
- NaN/Inf clamping each iteration

## Minimum-data threshold
Both host and candidate must each have ≥ 2 in-neighbours; otherwise neutral 0.5.

## Budget
Disk: <2 MB  ·  RAM: <100 MB for 5K query pairs on a 100K-node graph (in-neighbour CSR + per-pair score cache in float32)

## Scope boundary vs existing signals
- **FR-021 Pixie random walk**: Pixie is a per-host personalised walk producing one-sided proximity. SimRank is symmetric structural similarity. They can disagree: A may be "near" B via Pixie because A points at B, but B may not be SimRank-similar to A because B has very different in-neighbours.
- **FR-006 weighted PageRank**: PageRank is a per-node centrality, not a pair similarity.
- **FR-002 semantic similarity**: text-based; SimRank is text-agnostic, link-based.
- **FR-122 Katz centrality**: per-node walk-counting centrality, not a pair similarity.

## Test plan bullets
- convergence test: paper's Figure 1 toy graph (5 nodes including ProfA/ProfB pair) → SimRank scores match Jeh & Widom Section 4.4 example within 1e-4
- symmetry test: `s(a,b) = s(b,a)` for all pairs (paper Theorem 4.1)
- bound test: `0 ≤ s(a,b) ≤ 1` always
- parity test: C++ vs `networkx.simrank_similarity` within 1e-4
- no-crash on adversarial input: self-loops, dangling nodes (zero in-degree), parallel in-edges
- integration test: `ranking_weight = 0.0` leaves ordering unchanged
- determinism: identical edge list and pair list → identical scores
