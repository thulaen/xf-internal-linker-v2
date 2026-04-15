# FR-205 - Co-Authorship Graph PageRank

## Overview
In a forum, two authors "co-author" a thread when they both contribute substantive posts to the same discussion. Authors who co-author with many other respected authors are themselves more likely to be respected — this is the same intuition that gives PageRank its power on hyperlink graphs. This signal builds an undirected weighted co-authorship graph (edge weight = number of co-authored threads) and runs PageRank to produce a per-author authority score. Used as an additive author-trust boost.

## Academic source
**Liu, Xiaoming; Bollen, Johan; Nelson, Michael L.; Van de Sompel, Herbert (2005).** "Co-authorship Networks in the Digital Library Research Community." *Information Processing & Management*, vol. 41, no. 6, pp. 1462-1480. DOI: `10.1016/j.ipm.2005.03.024`. The weighted co-authorship-graph construction in §3 and the PageRank-on-co-authorship analysis in §4 form the basis for this signal. Underlying PageRank algorithm: Page, Brin, Motwani, Winograd (1999), Stanford TR.

## Formula
Build undirected graph `G = (V, E, w)` where `V = authors` and edge weight:
```
w(u, v) = |{ thread t : u ∈ contrib(t) ∧ v ∈ contrib(t) ∧ depth(post_u) ≥ d_min ∧ depth(post_v) ≥ d_min }|
```
with `d_min = 1` (substantive contribution threshold). Symmetric: `w(u,v) = w(v,u)`.

Weighted random-walk transition matrix:
```
P[u, v] = w(u, v) / Σ_{v'}  w(u, v')
```

PageRank iteration (Liu et al. Eq. 3, with damping `α = 0.85`):
```
PR_{t+1}(u) = (1 − α) / |V|  +  α · Σ_{v ∈ N(u)}  PR_t(v) · P[v, u]
```
Iterate until `||PR_{t+1} − PR_t||_1 < ε = 10⁻⁶` (typically `≤ 80` iterations).

Final additive boost (rank-normalised):
```
ca_pr_boost(u) = rank(PR(u)) / |V|        ∈ [0, 1], higher = more central
```

## Starting weight preset
```python
"co_authorship_pr.enabled": "true",
"co_authorship_pr.ranking_weight": "0.0",
"co_authorship_pr.damping": "0.85",
"co_authorship_pr.tolerance": "1e-6",
"co_authorship_pr.max_iters": "100",
"co_authorship_pr.min_post_depth": "1",
"co_authorship_pr.rebuild_cadence_hours": "24",
```

## C++ implementation
- File: `backend/extensions/co_authorship_pagerank.cpp`
- Entry: `void weighted_pagerank(const int* csr_offsets, const int* csr_targets, const double* csr_weights, int n, double damping, double tol, int max_iters, double* out_pr);`
- Complexity: `O((|V| + |E|) · iters)`; `iters ≈ 80` typical
- Thread-safety: per-iteration read-only, write to fresh buffer; double-buffered swap
- SIMD: `_mm256_fmadd_pd` for the weighted accumulation step
- Builds against pybind11; reuses CSR adapter from FR-006

## Python fallback
`backend/apps/pipeline/services/co_authorship_pagerank.py::weighted_pagerank(...)` — uses `scipy.sparse` CSR + power iteration.

## Benchmark plan
| Authors / Edges | C++ target | Python target |
|---|---|---|
| 1 K / 10 K | < 50 ms | < 500 ms |
| 10 K / 100 K | < 500 ms | < 8 s |
| 100 K / 2 M | < 8 s | < 5 min |

## Diagnostics
- Per-author raw `PR(u)` and rank-normalised `ca_pr_boost(u)`
- Number of iterations to convergence
- L1 residual at convergence
- Top-10 most-central authors
- C++ vs Python badge

## Edge cases & neutral fallback
- Author with no co-authors → `PR(u) = (1 − α)/|V|` (uniform baseline), neutral
- Disconnected component → PageRank computed within component, then re-normalised
- Single-author forum → `ca_pr_boost = 0.5` for the only author
- Power iteration didn't converge in `max_iters` → use last iterate, flag `did_not_converge`
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 10` authors AND `≥ 50` co-authorship edges before the score is trusted; below this returns neutral `0.5`.

## Budget
Disk: <2 MB (CSR snapshot)  ·  RAM: <120 MB at 100 K authors × 2 M edges

## Scope boundary vs existing signals
FR-205 does NOT overlap with FR-006 weighted link graph (which is on *pages*, not authors) or FR-211 trust propagation (which uses signed trust/distrust, not raw co-occurrence). It is also distinct from FR-204 author H-index (productivity-based, ignores graph context).

## Test plan bullets
- unit tests: 3-author triangle (all equal `PR`), star graph (centre has highest `PR`)
- parity test: C++ vs Python `PR` within `1e-5` (L_∞)
- damping sweep: `α ∈ {0.70, 0.85, 0.95}` produces monotone-on-rank ordering
- integration test: ranking unchanged when `ranking_weight = 0.0`
- determinism test: same graph + same damping → identical `PR` across runs
- convergence test: L1 residual decreases monotonically across iterations on a connected graph
