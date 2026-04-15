# FR-122 — Katz Centrality

## Overview
PageRank (FR-006) measures normalised steady-state mass; HITS measures hub/authority eigenvectors; Katz centrality counts *all* paths to a node, weighted by length so shorter paths matter more. On a forum this surfaces destinations that are reachable by many short paths — i.e. structurally well-embedded — even if they are not high-PageRank because they are not in a teleporting random walker's stationary distribution. Complements FR-006 because PageRank is a single damped Markov chain whereas Katz is a closed-form sum of all walk-counts. Particularly useful on directed acyclic forum link patterns where PageRank can saturate at low-information leaves.

## Academic source
**Katz, L. (1953).** "A New Status Index Derived from Sociometric Analysis." *Psychometrika*, 18(1), 39-43. DOI: `10.1007/BF02289026`.

## Formula
From Katz (1953), the centrality of node `i` is the attenuated sum of walks of all lengths ending at `i`:

```
C_Katz(i) = Σ_{k=1}^{∞} Σ_{j=1}^{n}  α^k · (A^k)_{j,i}             (Eq. 1)

Vector form:
    C = ((I - α·Aᵀ)^{-1} - I) · 𝟙

Equivalent power-iteration form (Bonacich, 1987):
    C_{t+1} = α · Aᵀ · C_t + β · 𝟙

Where:
    A         = directed adjacency matrix (A[j,i] = 1 if j → i)
    α         = attenuation factor, must satisfy α < 1/λ_max(A) for convergence
                (paper's "status index" parameter; for forum graphs α = 0.05 is safe)
    β         = exogenous bias, typically 1.0 (uniform)
    𝟙         = vector of ones, length n
    λ_max(A)  = spectral radius of A
```

Iterate until `‖C_{t+1} - C_t‖₂ < ε`. The convergence condition `α < 1/λ_max(A)` is necessary and sufficient.

## Starting weight preset
```python
"katz.enabled": "true",
"katz.ranking_weight": "0.0",
"katz.alpha": "0.05",
"katz.beta": "1.0",
"katz.max_iterations": "200",
"katz.convergence_tolerance": "1e-7",
```

## C++ implementation
- File: `backend/extensions/katz_centrality.cpp`
- Entry: `std::vector<float> katz_centrality(const int* edges_src, const int* edges_dst, int n_edges, int n_nodes, float alpha, float beta, int max_iter, float tol)`
- Complexity: O(k · |E|) per iteration via sparse SpMV; typical k = 100-150 for tol=1e-7
- Thread-safety: stateless; SIMD-friendly SpMV with float32 accumulators (Kahan summation for the dense β-bias add to keep parity with float64 reference)
- Pre-checks `α < 1/spectral_radius_estimate(A)` using power-iteration on `AᵀA`; if violated, abort with error
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/katz.py::compute_katz_centrality` using `networkx.katz_centrality(alpha=α, beta=β, max_iter=max_iter, tol=tol, normalized=True)`.

## Benchmark plan
| Graph size | C++ target | Python target |
|---|---|---|
| small (1K nodes, 8K edges) | <8 ms | <60 ms |
| medium (10K nodes, 100K edges) | <100 ms | <1 s |
| large (100K nodes, 1.5M edges) | <2 s | <25 s |

## Diagnostics
- Raw Katz value in suggestion detail UI (`katz_diagnostics.katz_score`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `convergence_iterations`, `alpha_used`, `spectral_radius_estimate`, `convergence_safety_margin` (= `1/λ_max - α`), `final_l2_delta`

## Edge cases & neutral fallback
- `α ≥ 1/λ_max(A)` (divergence risk) → fallback 0.5, flag `neutral_alpha_too_large`
- Disconnected graph → Katz computed per-component naturally (linear system solved on each component)
- Convergence failure → fallback 0.5, flag
- Self-loops: paper allows them; we keep them (they appear in `A^k` and contribute to walk counts)
- NaN/Inf clamping each iteration

## Minimum-data threshold
Graph must have ≥ 10 nodes and the destination must have ≥ 1 in-edge; otherwise neutral 0.5.

## Budget
Disk: <2 MB  ·  RAM: <80 MB for a 100K-node graph (sparse adjacency + score vector + power-iteration estimator workspace in float32)

## Scope boundary vs existing signals
- **FR-006 weighted PageRank**: PageRank uses damping + teleport; Katz uses pure attenuation with no teleport vector. Katz can grow unbounded if α is too large, PageRank cannot.
- **FR-116 HITS authority**: HITS is the dominant eigenvector of `AᵀA`; Katz is a power-series in `αAᵀ`. Different mathematical objects, different ranking outputs on the same graph.
- **FR-021 Pixie random walk**: Pixie is per-query short walks; Katz is a global walk-count centrality.
- **FR-125 LeaderRank**: LeaderRank adds a ground node to fix dangling-node issues; Katz handles them by structure (zero contribution).

## Test plan bullets
- convergence test: 4-node directed cycle → analytical Katz score `α/(1-α^4)` matches numerical within 1e-6
- spectral-radius test: synthetic graph with known λ_max — pre-check correctly rejects α = 1.5/λ_max
- parity test: C++ vs `networkx.katz_centrality` within 1e-5
- no-crash on adversarial input: self-loops, dangling-out nodes, isolated nodes, complete graph K_n
- integration test: `ranking_weight = 0.0` leaves ordering unchanged
- determinism: identical edge list → identical scores
