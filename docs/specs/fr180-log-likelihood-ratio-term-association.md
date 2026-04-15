# FR-180 — Log-Likelihood Ratio (Dunning LLR) for Term Association

## Overview
Dunning's log-likelihood ratio (G²) is the gold-standard collocation/association significance test. Unlike PMI/NPMI it is *count-aware*: rare pairs cannot achieve high LLR purely by coincidence. LLR follows a chi-squared distribution under the null hypothesis of independence, so values can be converted to p-values. For an internal-linker, LLR provides a statistically defensible "is this anchor genuinely associated with this destination?" filter that suppresses single-coincidence pairs PMI would over-rank. Complements `fr178-pointwise-mutual-information` and `fr179-normalized-pmi` by adding significance to effect-size measures.

## Academic source
Dunning, T. "Accurate methods for the statistics of surprise and coincidence." *Computational Linguistics*, 19(1), pp. 61–74, 1993. URL: https://aclanthology.org/J93-1003/. ACL Anthology citation: `J93-1003`. Cited >10,000 times; the canonical reference for likelihood-ratio statistics in NLP.

## Formula
From Dunning (1993), Section 3 — LLR for a 2×2 contingency table of co-occurrence is:

```
                 y     ¬y
              ┌─────┬─────┐
            x │ k₁₁ │ k₁₂ │ → n₁ = k₁₁ + k₁₂
              ├─────┼─────┤
           ¬x │ k₂₁ │ k₂₂ │ → n₂ = k₂₁ + k₂₂
              └─────┴─────┘

p   = (k₁₁ + k₂₁) / (n₁ + n₂)              (pooled probability)
p₁  = k₁₁ / n₁
p₂  = k₂₁ / n₂

L(p, k, n) = p^k · (1 − p)^(n − k)         (binomial likelihood)

−2 · log λ = 2 · [ log L(p₁, k₁₁, n₁)
                 + log L(p₂, k₂₁, n₂)
                 − log L(p,   k₁₁, n₁)
                 − log L(p,   k₂₁, n₂) ]
```

Equivalent compact form (Manning & Schütze 1999, Eq. 5.12):

```
−2 · log λ = 2 · Σ_{i,j} k_{ij} · log( k_{ij} / E_{ij} )
where E_{ij} = ( Σ_j k_{ij} · Σ_i k_{ij} ) / N
```

Asymptotically `−2·log λ ~ χ²_1` under independence; thresholds: 3.84 (p<0.05), 6.63 (p<0.01), 10.83 (p<0.001).

## Starting weight preset
```python
"llr.enabled": "true",
"llr.ranking_weight": "0.0",
"llr.significance_threshold": "10.83",
"llr.zero_count_handling": "skip_term",
```

## C++ implementation
- File: `backend/extensions/llr.cpp`
- Entry: `double llr(uint64_t k11, uint64_t k12, uint64_t k21, uint64_t k22)`
- Complexity: O(1) per contingency cell — 4 cells per pair
- Thread-safety: pure function; no shared state
- Builds via pybind11; uses `x · log(x/E)` with the convention `0·log 0 = 0` to avoid NaN

## Python fallback
`backend/apps/pipeline/services/llr.py::compute_llr` using vectorised NumPy with `np.where(k > 0, k * np.log(k / E), 0)`.

## Benchmark plan

| Size | pairs evaluated | C++ target | Python target |
|---|---|---|---|
| Small | 1,000 | 0.01 ms | 0.8 ms |
| Medium | 100,000 | 0.8 ms | 80 ms |
| Large | 10,000,000 | 60 ms | 7,000 ms |

## Diagnostics
- LLR value rendered as "LLR: 24.7 (p < 0.001)"
- Contingency table k₁₁/k₁₂/k₂₁/k₂₂ shown
- p-value derived from χ²_1 lookup
- C++/Python badge
- Debug fields: `expected_e11`, `e12`, `e21`, `e22`, `chi2_p_value`, `significance_pass`

## Edge cases & neutral fallback
- Cell `k_{ij} = 0` ⇒ that term in the sum contributes 0 (per `0·log 0 = 0` convention)
- Expected count `E_{ij} = 0` ⇒ undefined; neutral 0.5 with fallback flag
- All four counts equal ⇒ LLR = 0 (perfect independence)
- LLR is *one-sided in interpretation*: high LLR = strong association either positive or negative ⇒ pair the LLR with PMI sign for direction
- Negative LLR is impossible by construction; if observed, it is a numerical bug — assert and skip

## Minimum-data threshold
Need `Σk ≥ 25` (overall sample size) and at least one cell with `k ≥ 5` for the χ² approximation to be valid; otherwise neutral 0.5.

## Budget
Disk: shared with FR-178/FR-179 co-occurrence sketch · RAM: same lookup tables

## Scope boundary vs existing signals
LLR is the *significance test* in the association family; PMI/NPMI are *effect sizes*. They complement each other and should be reported together: NPMI for "how strong" and LLR for "how trustworthy". Distinct from `fr011-field-aware-relevance-scoring` (per-document scorer). Not a query-performance predictor.

## Test plan bullets
- Unit: perfectly independent table (`k₁₁ · k₂₂ = k₁₂ · k₂₁`) ⇒ LLR = 0
- Unit: strong association ⇒ LLR ≫ 10.83
- Parity: C++ vs Python within 1e-6 on 1,000 contingency tables
- Identity: LLR ≥ 0 always
- Edge: cell with `k = 0` does not crash (uses `0·log 0 = 0`)
- Edge: total `Σk < 25` returns 0.5 with low-power fallback
- Integration: p-value matches scipy.stats.chi2.sf within 1e-4
- Regression: top-50 ranking unchanged when weight = 0.0
