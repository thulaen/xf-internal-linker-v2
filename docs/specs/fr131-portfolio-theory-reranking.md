# FR-131 — Portfolio Theory Reranking

## Overview
Markowitz's modern portfolio theory (1952 Nobel-winning) treats expected return and variance as the two objectives an investor balances when picking a stock portfolio. Wang & Zhu (2009) ported this exactly to information retrieval: a result list is a portfolio, each document's relevance is its expected return, document-document correlation is the covariance, and the operator picks a slate to maximise the *mean-variance utility* `E[R] − b · Var[R]` where `b` is the risk aversion coefficient. Negative diversification is captured because correlated (similar) documents add to the variance penalty. On a forum this gives a principled, statistically-grounded diversification with a single risk-aversion knob that maps to a familiar finance concept. Complements FR-129 because DPP optimises log-volume (a multiplicative geometric measure) while portfolio theory optimises a quadratic mean-variance trade-off (an additive statistical measure).

## Academic source
**Wang, J., & Zhu, J. (2009).** "Portfolio Theory of Information Retrieval." *Proceedings of the 32nd International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2009)*, Boston, MA, pages 115-122. DOI: `10.1145/1571941.1571963`.

(Foundational mean-variance theory: **Markowitz, H. (1952).** "Portfolio Selection." *The Journal of Finance*, 7(1), 77-91. DOI: `10.1111/j.1540-6261.1952.tb01525.x`.)

## Formula
From Wang & Zhu (2009), Eqs. 3-4 (mean-variance objective) and Eq. 8 (greedy selection):

```
Portfolio expected return (Eq. 3):
    E[R(S)] = Σ_{i ∈ S}  w_i · μ_i

Portfolio variance (Eq. 4):
    Var[R(S)] = Σ_{i ∈ S} Σ_{j ∈ S}  w_i · w_j · σ_i · σ_j · ρ_{ij}

Mean-variance objective (Eq. 5):
    O(S) = E[R(S)] - b · Var[R(S)]

Greedy selection at position k+1 given slate S (Eq. 8):
    d* = argmax_{d ∉ S}  μ_d - b · ( σ_d² + 2 · Σ_{j ∈ S}  σ_d · σ_j · ρ_{dj} )

Where:
    μ_i        = expected relevance score of document i (e.g. predicted NDCG contribution)
    σ_i        = standard deviation of i's relevance estimate (uncertainty)
    ρ_{ij}     ∈ [-1, 1], correlation between i and j (typically cosine similarity rescaled)
    w_i        = position weight (paper Eq. 6: w_i = 1/log_2(1 + position_i),
                 the DCG discount; for unranked candidates use w_i = 1)
    b ∈ ℝ_{≥0} = risk aversion coefficient (paper experiments use b ∈ [0, 5])
    S          = current selected slate
```

The greedy algorithm of Eq. 8 is the marginal version of the mean-variance objective and is exact when `w_i = 1` (no position weighting); for position-weighted slates it is heuristic but performs well in the paper's experiments (Table 3).

## Starting weight preset
```python
"portfolio.enabled": "true",
"portfolio.ranking_weight": "0.0",
"portfolio.risk_aversion_b": "1.0",
"portfolio.uncertainty_source": "ranking_score_std",
"portfolio.correlation_source": "embedding_cosine",
"portfolio.target_slate_size": "10",
```

## C++ implementation
- File: `backend/extensions/portfolio.cpp`
- Entry: `std::vector<int> portfolio_pick(const float* mu, const float* sigma, const float* rho_matrix, int n_candidates, int target_k, float b)`
- Complexity: O(K · n) per pick for the marginal-variance update term; total O(K² · n) — for K=10, n=500 = 25,000 ops
- Thread-safety: stateless; SIMD over the `Σ ρ_{dj} · σ_j` accumulator using AVX2
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/portfolio.py::portfolio_pick` — NumPy implementation; the per-pick marginal-variance vector is one matrix-vector product, fully vectorised.

## Benchmark plan
| Candidates | Slate K | C++ target | Python target |
|---|---|---|---|
| small (50) | 5 | <0.05 ms | <0.5 ms |
| medium (500) | 10 | <0.5 ms | <8 ms |
| large (5000) | 20 | <15 ms | <200 ms |

## Diagnostics
- Per-position mean-variance breakdown in suggestion detail UI (`portfolio_diagnostics.pick_log`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `expected_return_per_pick`, `marginal_variance_per_pick`, `cumulative_portfolio_variance`, `cumulative_portfolio_return`, `risk_aversion_b_used`, `sharpe_ratio_at_k` (= return / √variance)

## Edge cases & neutral fallback
- All correlations zero (independent docs) → variance penalty additive only via own σ², portfolio reduces to top-K by `μ_i - b · σ_i²`
- Zero uncertainty (σ_i = 0 for all i) → variance term vanishes, ranking degenerates to top-K by `μ`; flag
- `b = 0` → ranking degenerates to relevance-only (no diversification); flag and short-circuit
- Negative correlations → handled naturally (they actually *reduce* portfolio variance, encouraging contrarian picks)
- NaN/Inf in matrix → clamp; flag

## Minimum-data threshold
n ≥ 2K AND at least one σ_i > 0; otherwise skip.

## Budget
Disk: <1 MB  ·  RAM: <60 MB at n=5000 (correlation matrix in float32 = 100 MB → use upper triangle, ~50 MB; plus μ, σ vectors)

## Scope boundary vs existing signals
- **FR-129 DPP**: DPP optimises log-determinant (geometric volume); portfolio optimises mean-variance (statistical second moment). Different mathematical objectives; DPP cannot natively express uncertainty σ_i, portfolio can.
- **FR-126/127/128**: aspect-based; portfolio is correlation-matrix-based, no aspect taxonomy needed.
- **FR-130 submodular coverage**: submodular framework gives `(1-1/e)` approximation; portfolio greedy is exact for unweighted slates and heuristic for weighted (no formal bound).
- **FR-015 final-slate diversity reranking**: MMR-style, no statistical interpretation; portfolio has explicit risk-aversion coefficient.

## Test plan bullets
- correctness test: paper's Section 5.2 toy example (3 docs, known μ, σ, ρ, b=1) → greedy picks match Eq. 8 trace within 1e-6
- variance-monotonicity test: cumulative portfolio variance is non-decreasing per pick when all correlations are positive
- diversification-test: synthetic data with high pairwise correlation → portfolio picks highly differ from relevance-only top-K (Spearman ρ < 0.5 between the two rankings)
- b-sweep test: b=0 produces relevance-only ordering; b → ∞ minimises variance (picks the most independent set)
- parity test: C++ vs Python within 1e-6
- no-crash on adversarial input: zero σ, all-correlated (ρ=1), all-anti-correlated (ρ=-1), NaN inputs
- integration test: `ranking_weight = 0.0` leaves ranking unchanged
- determinism: tie-breaking by lower index → identical slate across runs
