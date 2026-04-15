# FR-212 - User EigenTrust

## Overview
EigenTrust is a global reputation algorithm originally designed for peer-to-peer file-sharing networks: each peer aggregates direct trust ratings of its neighbours, then those ratings are recursively combined into a system-wide score that is the principal eigenvector of the local-trust matrix. A small set of *pre-trusted peers* anchors the score, making the algorithm Sybil-resistant and convergent. We adapt EigenTrust to the forum user graph: pre-trusted set = mods + long-tenured high-H-index authors; local trust = positive interactions normalised per source. Used as an additive author-trust boost.

## Academic source
**Kamvar, Sepandar D.; Schlosser, Mario T.; Garcia-Molina, Hector (2003).** "The EigenTrust Algorithm for Reputation Management in P2P Networks." *Proceedings of the 12th International World Wide Web Conference (WWW 2003)*, pp. 640-651. DOI: `10.1145/775152.775242`. The fixed-point trust definition (Eq. 5), the pre-trusted-peer anchor (Eq. 8), and the basic algorithm in §5 are the basis for this signal.

## Formula
Define local trust matrix `C ∈ ℝⁿˣⁿ` with rows summing to 1 (Kamvar Eq. 4):
```
c_{ij} = max(s_{ij}, 0) / Σ_j max(s_{ij}, 0)               where s_{ij} = pos(i,j) − neg(i,j)
```
- `pos(i,j)` = positive interactions from `i` to `j` (likes, helpful marks, replies that get acknowledged)
- `neg(i,j)` = negative interactions (downvotes, reports)

Pre-trusted peer vector `p ∈ ℝⁿ` with `Σ p_i = 1`, supported on a set `P` of trusted seeds:
```
p_i = 1/|P| if i ∈ P  else  0
```

Fixed-point trust (Kamvar Eq. 8, the anchored EigenTrust):
```
t = (1 − a) · Cᵀ · t  +  a · p              a = 0.10
```

Solved by power iteration:
```
t_{k+1} = (1 − a) · Cᵀ · t_k  +  a · p
stop when ||t_{k+1} − t_k||_1 < ε = 10⁻⁶
```

Final additive boost (already in `[0, 1]` after normalisation `Σ t_i = 1`):
```
eigentrust_boost(u) = t[u] / max(t)
```

## Starting weight preset
```python
"eigentrust.enabled": "true",
"eigentrust.ranking_weight": "0.0",
"eigentrust.anchor_a": "0.10",
"eigentrust.tolerance": "1e-6",
"eigentrust.max_iters": "100",
"eigentrust.pretrusted_top_n_h_authors": "20",
"eigentrust.pretrusted_include_all_mods": "true",
"eigentrust.rebuild_cadence_hours": "24",
```

## C++ implementation
- File: `backend/extensions/user_eigentrust.cpp`
- Entry: `void compute_eigentrust(const SparseMatrix& C_transpose, const double* p_vec, int n, double a, double tol, int max_iters, double* out_trust);`
- Complexity: `O((|V| + |E|) · iters)`; `iters ≈ 80` typical
- Thread-safety: SpMV parallelised via OpenMP, double-buffered iterate
- SIMD: `_mm256_fmadd_pd` for the convex combination `(1 − a)·SpMV + a·p`
- Builds against pybind11; reuses CSR adapter from FR-006

## Python fallback
`backend/apps/pipeline/services/user_eigentrust.py::compute_eigentrust(...)` — uses `scipy.sparse` SpMV with explicit power iteration.

## Benchmark plan
| Users / Edges | C++ target | Python target |
|---|---|---|
| 1 K / 10 K | < 30 ms | < 300 ms |
| 10 K / 100 K | < 300 ms | < 4 s |
| 100 K / 2 M | < 4 s | < 90 s |

## Diagnostics
- Per-user raw `t[u]` and normalised `eigentrust_boost(u)`
- Number of iterations to convergence
- L1 residual at convergence
- Pre-trusted set size and membership
- Top-10 highest-EigenTrust users
- C++ vs Python badge

## Edge cases & neutral fallback
- Pre-trusted set empty → fall back to uniform `p = 1/|V|`, flag `no_pretrusted_set` (this approximates raw eigenvector centrality)
- Row of `C` is all zero (user has no positive interactions) → row replaced with `p` (Kamvar Eq. 7), flag `dangling_user`
- Disconnected component without pre-trusted peer → trust → `a · 0 = 0` over time
- Power iteration didn't converge in `max_iters` → use last iterate, flag `did_not_converge`
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 100` users AND `≥ 500` trust edges AND `≥ 1` pre-trusted peer before scores are trusted; below this returns neutral `0.0`.

## Budget
Disk: <2 MB (CSR snapshot + `p`)  ·  RAM: <250 MB at 100 K users × 2 M edges

## Scope boundary vs existing signals
FR-212 does NOT overlap with FR-211 trust propagation — FR-211 uses *iterated atomic operators* with possible distrust; FR-212 uses a *fixed-point* definition with pre-trusted anchors and is Sybil-resistant by construction. It is also distinct from FR-118 TrustRank (page-level, forward propagation from a single seed) and FR-205 co-authorship PageRank (no trust signal — pure co-occurrence).

## Test plan bullets
- unit tests: 3-node chain with `P = {1}` → `t_1 ≥ t_2 ≥ t_3`; uniform graph with all pre-trusted → uniform `t`
- parity test: C++ vs Python `t` within `1e-5` (L_∞)
- anchor weight sweep: `a ∈ {0.05, 0.10, 0.20}` produces monotone-on-rank ordering
- Sybil resistance test: adding a Sybil clique that all-vote each other but is not in `P` → Sybil scores stay near `0`
- integration test: ranking unchanged when `ranking_weight = 0.0`
- determinism test: same `C` + same `p` + same `a` → identical `t` across runs
