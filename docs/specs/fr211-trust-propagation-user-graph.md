# FR-211 - Trust Propagation on User Graph

## Overview
Trust on a forum is partly inherited: if Alice trusts Bob and Bob trusts Carol, Alice probably has some trust in Carol. Guha et al. (2004) decomposed trust propagation into a small set of "atomic" graph operations — direct propagation, co-citation, transpose, and trust coupling — and showed that combinations of these recover the trust judgments humans actually make on Epinions data with up to 88% accuracy. This signal builds a positive-trust graph among forum users (likes, follows, mod-actions) and a separate distrust graph (downvotes, blocks, mod-removals), then runs Guha-style propagation to produce a per-user trust score. Used as an additive author-trust boost.

## Academic source
**Guha, R.; Kumar, R.; Raghavan, P.; Tomkins, A. (2004).** "Propagation of Trust and Distrust." *Proceedings of the 13th International World Wide Web Conference (WWW 2004)*, pp. 403-412. DOI: `10.1145/988672.988727`. The four atomic propagations in §3 — direct propagation, co-citation, transpose, trust coupling — and the combined operator with one-step distrust in §4 form the basis for this signal.

## Formula
Let `T ∈ ℝⁿˣⁿ` be the row-normalised trust matrix and `D ∈ ℝⁿˣⁿ` be the distrust matrix. Define the four atomic operators (Guha et al. §3):

```
direct prop.    : T · T
co-citation     : T · Tᵀ
transpose       : Tᵀ · T
trust coupling  : Tᵀ · Tᵀ
```

Combined trust propagation operator (Eq. 6):
```
C_B = α₁·T  +  α₂·T·Tᵀ  +  α₃·Tᵀ·T  +  α₄·Tᵀ·Tᵀ                 Σ α_i = 1
```

Iterated trust score after `k` steps from a seed-set `s ∈ {0,1}ⁿ`:
```
P_k = (C_B)^k · s
```

One-step distrust (the only safe distrust mode per Guha §5.4):
```
F = P_k − γ · D · P_k        γ = 0.5  (paper §5.4)
```

Final per-user score:
```
trust(u) = max(0, F[u]) / max(F)            ∈ [0, 1]
trust_boost(u) = trust(u)
```

Default mixing weights from paper Table 4: `α = (0.4, 0.4, 0.1, 0.1)`, `k = 4` propagation steps.

## Starting weight preset
```python
"trust_propagation.enabled": "true",
"trust_propagation.ranking_weight": "0.0",
"trust_propagation.alpha_direct": "0.40",
"trust_propagation.alpha_cocitation": "0.40",
"trust_propagation.alpha_transpose": "0.10",
"trust_propagation.alpha_coupling": "0.10",
"trust_propagation.k_steps": "4",
"trust_propagation.gamma_distrust": "0.50",
"trust_propagation.seed_size": "32",
```

## C++ implementation
- File: `backend/extensions/trust_propagation.cpp`
- Entry: `void propagate_trust(const SparseMatrix& T, const SparseMatrix& D, const double* seed, int n, double a1, double a2, double a3, double a4, int k_steps, double gamma, double* out_trust);`
- Complexity: `O(k · |E_T| + k · |E_D|)` per propagation step; matrix multiplications fused via SpMV
- Thread-safety: SpMV parallelised via OpenMP
- Memory: CSR storage for both `T` and `D`, double-buffered iteration vector
- Builds against pybind11; reuses CSR adapter from FR-006

## Python fallback
`backend/apps/pipeline/services/trust_propagation.py::propagate_trust(...)` — uses `scipy.sparse` SpMV.

## Benchmark plan
| Users / Edges | C++ target | Python target |
|---|---|---|
| 1 K / 10 K | < 50 ms | < 500 ms |
| 10 K / 100 K | < 500 ms | < 5 s |
| 100 K / 2 M | < 5 s | < 60 s |

## Diagnostics
- Per-user raw `F[u]` and normalised `trust(u)`
- Step-by-step L1 norm of `P_k` (convergence trace)
- Distrust contribution magnitude
- Seed-set size and selection method
- Mixing weights (`α` vector) at run time
- C++ vs Python badge

## Edge cases & neutral fallback
- Empty seed set → all `trust = 0`, flag `no_seeds`
- Disconnected component without seed → `trust = 0` for all nodes in that component
- All-zero distrust matrix → `F = P_k` (no penalty)
- Mixing weights don't sum to `1` → re-normalise at config load, flag `weights_renormalised`
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 100` users AND `≥ 500` trust edges AND `≥ 5` seeds before the score is trusted; below this returns neutral `0.0`.

## Budget
Disk: <2 MB (CSR snapshots)  ·  RAM: <300 MB at 100 K users × 2 M edges (CSR + work vectors)

## Scope boundary vs existing signals
FR-211 does NOT overlap with FR-118 TrustRank (page-level forward propagation from a seed set; FR-211 is *user-level* and combines four atomic operators). It is also distinct from FR-119 AntiTrustRank (which propagates only distrust *backwards*) and FR-212 EigenTrust (which uses a fixed-point definition with pre-trusted peers, not iterated atomic operators). FR-208 mod endorsement uses *direct* mod actions only — FR-211 propagates beyond the mod set.

## Test plan bullets
- unit tests: 3-node chain with seed at one end → trust decays geometrically
- parity test: C++ vs Python `trust` within `1e-5`
- distrust test: adding distrust edge from `u` to `v` strictly lowers `trust(v)`
- atomic operator test: each of the 4 individual operators (`α = δ_i`) produces the expected pattern (e.g. transpose puts trust on the *targets* not the sources of trust edges)
- integration test: ranking unchanged when `ranking_weight = 0.0`
- weights re-normalisation test: passing `α = (1, 1, 1, 1)` yields the same ranking as `α = (0.25, 0.25, 0.25, 0.25)`
