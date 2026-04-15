# FR-200 - Sybil Attack Detector (SybilGuard)

## Overview
A Sybil attack is when a single attacker creates many fake user accounts that link to one another to fake reputation, votes, or trust. Honest accounts form a "fast-mixing" social sub-graph; Sybil accounts attach to it through a thin "attack edge" set, so a random walk that starts at a verified user and walks for `O(√n · log n)` steps will be very unlikely to leave the honest region. SybilGuard exploits this: nodes that exhibit *abnormally long mixing time* under random walks are flagged as Sybil. Used as a multiplicative trust penalty on author candidates.

## Academic source
**Yu, Haifeng; Gibbons, Phillip B.; Kaminsky, Michael; Xiao, Feng (2008).** "SybilGuard: Defending Against Sybil Attacks via Social Networks." *IEEE/ACM Transactions on Networking*, vol. 16, no. 3, pp. 576-589. The conference version: *Proceedings of the 2006 ACM SIGCOMM Conference*, DOI: `10.1145/1159913.1159945`. The bounded-length random-walk and route-intersection test in §4 are the basis for this signal.

## Formula
Given an undirected user graph `G = (V, E)` with `n = |V|`, define the random-walk transition matrix:
```
P[u, v] = 1 / deg(u)    if (u,v) ∈ E    else 0
```

For each node `u`, perform `r` independent random walks of length `w = ⌈√(n) · log n⌉` (paper §4.1). The `i`-th walk visits route `R_i(u) = (u, x_1, x_2, …, x_w)`.

A candidate `u` is verified by an honest seed `s` iff `∃ i, j` such that `R_i(s) ∩ R_j(u) ≠ ∅`. The mixing time signal:
```
mix(u) = average length of intersection prefix between R(u) and R(s)
sybil_score(u) = max(0, 1 − mix(u) / mix_baseline)
```

Where `mix_baseline` is the median `mix(u)` over verified honest seeds. A simpler operational form (paper Eq. 7):
```
sybil_score(u) = 1 − Pr[ R_w(u) reaches honest seed set H in ≤ w steps ]
```

Empirical estimator from `r` Monte-Carlo walks:
```
ŝ(u) = 1 − ( |{ i : R_i(u) ∩ H ≠ ∅ }| / r )
```

## Starting weight preset
```python
"sybil.enabled": "true",
"sybil.ranking_weight": "0.0",
"sybil.walk_count_r": "256",
"sybil.walk_length_factor": "1.0",     # multiplied into ⌈√n · log n⌉
"sybil.honest_seed_count": "32",
"sybil.threshold": "0.50",
```

## C++ implementation
- File: `backend/extensions/sybil_guard.cpp`
- Entry: `void random_walks(const int* csr_offsets, const int* csr_targets, int n_nodes, int r, int w, const int* honest_seeds, int n_seeds, double* out_score);`
- Complexity: `O(n · r · w)` — embarrassingly parallel over nodes and walks
- Thread-safety: per-node walks parallelised via OpenMP, RNG state per thread (PCG32)
- Memory: CSR adjacency only, `O(|V| + |E|)`
- Builds against pybind11; reuses graph adapter from FR-006

## Python fallback
`backend/apps/pipeline/services/sybil_guard.py::random_walks(...)` — uses `numpy` for the transition step, `networkx` for adjacency.

## Benchmark plan
| Nodes | C++ target | Python target |
|---|---|---|
| 1 K | < 100 ms | < 5 s |
| 10 K | < 1 s | < 60 s |
| 100 K | < 15 s | < 30 min |

## Diagnostics
- Raw `ŝ(u)` per node
- Walk length `w` actually used
- Number of honest seeds reached per node
- Honest seed set size and selection method
- C++ vs Python badge

## Edge cases & neutral fallback
- Disconnected component → all nodes in component get `ŝ = 1.0`, flag `disconnected`
- Honest seed set empty → neutral `0.0`, flag `no_seeds`
- Node with degree 0 → `1.0`, flag `isolated`
- Random walk stuck in self-loop → re-roll up to 3 times then flag `walk_stuck`
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 100` nodes AND `≥ 10` honest seeds before the score is trusted; below this returns neutral `0.0`.

## Budget
Disk: <1 MB  ·  RAM: <500 MB at 100 K nodes (CSR + walk buffers)

## Scope boundary vs existing signals
FR-200 does NOT overlap with FR-118 TrustRank or FR-211 trust propagation — those propagate scalar trust along *edges*. FR-200 detects *topological* anomaly via random-walk mixing. It is also distinct from FR-201 AstroTurf detection (which uses temporal/textual features, not graph mixing).

## Test plan bullets
- unit tests: clique of honest nodes (all `ŝ ≈ 0`), Sybil cluster attached via single edge (all `ŝ ≈ 1`)
- parity test: C++ vs Python `ŝ` within `±0.05` (Monte Carlo variance)
- regression test: legitimate sub-communities (e.g. niche topic forums) must not be flagged en masse
- integration test: ranking unchanged when `ranking_weight = 0.0`
- determinism test: fixed seed + fixed PCG32 → identical `ŝ` across runs
- scaling test: 100 K nodes within 15 s in C++ on 8 cores
