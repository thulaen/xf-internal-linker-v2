# FR-125 — LeaderRank

## Overview
PageRank's biggest weakness is dangling nodes (pages with no outbound links) — they leak probability mass and force the algorithm to teleport to compensate. The teleport vector is a hyperparameter that needs tuning. LeaderRank fixes this by adding one *ground node* connected bidirectionally to every other node, eliminating the need for damping and teleport entirely. The result is parameter-free and Lü et al. (2011) showed it outperforms PageRank in robustness to noisy and incomplete networks. On a forum, where many leaf threads are dangling-out, LeaderRank gives a cleaner authority score than tuned PageRank. Complements FR-006 weighted PageRank because LeaderRank requires zero parameter tuning and is provably more robust to graph perturbations.

## Academic source
**Lü, L., Zhang, Y.-C., Yeung, C. H., & Zhou, T. (2011).** "Leaders in social networks, the delicious case." *PLoS ONE*, 6(6), e21202. DOI: `10.1371/journal.pone.0021202`.

## Formula
From Lü et al. (2011), Eqs. 1-3:

```
Construction:
    Add ground node g to graph G, producing G' = (V ∪ {g}, E ∪ E_g)
    where E_g = { (g, v) and (v, g) : v ∈ V }   (bidirectional links to all)

Iteration on G' (standard random walk, no damping, no teleport):
    s_{t+1}(i) = Σ_{j : j → i in G'}  s_t(j) / k_out(j)            (Eq. 1)

Initialisation: s_0(i) = 1 for all nodes including g.

Convergence to unique stationary distribution s* (guaranteed because G' is strongly connected by construction).

Final score (Eq. 3, redistribute ground node's mass uniformly):
    LR(i) = s*(i) + s*(g) / N

Where:
    k_out(j) = out-degree of j in G' (always ≥ 1 because of ground-node edge)
    N        = |V|, the original node count (excludes ground node)
```

The ground node `g` ensures every node has at least one outbound edge, so dangling nodes vanish naturally.

## Starting weight preset
```python
"leaderrank.enabled": "true",
"leaderrank.ranking_weight": "0.0",
"leaderrank.max_iterations": "100",
"leaderrank.convergence_tolerance": "1e-7",
```

(Note: no damping factor because LeaderRank is parameter-free by design.)

## C++ implementation
- File: `backend/extensions/leaderrank.cpp`
- Entry: `std::vector<float> leaderrank(const int* edges_src, const int* edges_dst, int n_edges, int n_nodes, int max_iter, float tol)`
- Complexity: O(k · (|E| + |V|)) per iteration — `|E|` for the original edges, `|V|` for the ground-node edges (which can be implemented implicitly as a "broadcast" step rather than n^2 stored edges)
- Thread-safety: stateless; SIMD-friendly SpMV plus a single ground-node redistribution step per iteration
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/leaderrank.py::compute_leaderrank` — implemented manually as `networkx.pagerank` with `alpha=1.0` is mathematically incorrect for LeaderRank (it ignores the ground node). We construct the augmented graph and run `networkx.pagerank(G_augmented, alpha=1.0, max_iter=...)`, then redistribute as in Eq. 3.

## Benchmark plan
| Graph size | C++ target | Python target |
|---|---|---|
| small (1K nodes, 8K edges) | <8 ms | <60 ms |
| medium (10K nodes, 100K edges) | <100 ms | <1 s |
| large (100K nodes, 1.5M edges) | <2 s | <25 s |

## Diagnostics
- Raw LeaderRank value in suggestion detail UI (`leaderrank_diagnostics.leaderrank_score`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `convergence_iterations`, `ground_node_mass` (the `s*(g)` value before redistribution — should be small; if large, the graph is mostly dangling), `dangling_node_count`, `final_l1_delta`

## Edge cases & neutral fallback
- Single-node graph → only the ground node and one real node → trivial fixed point; map to neutral 0.5
- Convergence failure → fallback 0.5 (rare because G' is guaranteed strongly connected)
- All-dangling graph (no original edges at all) → ground node gets all mass; redistribution makes every node equal; map to neutral 0.5 with flag `neutral_no_real_edges`
- NaN/Inf clamping each iteration

## Minimum-data threshold
Graph must have ≥ 10 nodes and ≥ 1 real edge (excluding ground-node edges); otherwise neutral 0.5.

## Budget
Disk: <2 MB  ·  RAM: <80 MB for a 100K-node graph (sparse adjacency + score vector + ground-node accumulator in float32)

## Scope boundary vs existing signals
- **FR-006 weighted PageRank**: PageRank requires damping factor `α` (typically 0.85) which is a tuning parameter; LeaderRank is parameter-free. PageRank teleports uniformly; LeaderRank's ground node is bidirectional which propagates information differently.
- **FR-116/117 HITS**: HITS computes hub/authority pair via mutually-reinforcing eigenvectors; LeaderRank computes a single authority-like score. Different mathematical objects.
- **FR-118 TrustRank**: TrustRank biases toward seeds; LeaderRank has no seed concept.
- **FR-122 Katz**: Katz needs `α < 1/λ_max` (tuning); LeaderRank needs no parameter.

## Test plan bullets
- correctness test: paper's Figure 1 toy graph (4 nodes) → LeaderRank scores match Lü et al. Table 1 within 1e-4
- parameter-free test: doubling all edge weights uniformly leaves ranking order unchanged (no parameter to retune)
- robustness test: removing 10% of edges at random changes LeaderRank ranking by Spearman ρ ≥ 0.95 (paper's Figure 4 robustness curve)
- parity test: C++ vs Python implementation within 1e-5
- no-crash on adversarial input: all-dangling graph, single-edge graph, complete graph K_n, self-loops
- integration test: `ranking_weight = 0.0` leaves ordering unchanged
- determinism: identical edge list → identical scores
