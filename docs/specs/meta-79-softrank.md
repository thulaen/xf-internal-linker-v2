# META-79 — SoftRank Listwise Loss

## Overview
**Category:** Listwise ranking loss (Gaussian-noise rank-distribution surrogate)
**Extension file:** `softrank.cpp`
**Replaces/improves:** META-77 LambdaLoss when an explicit, calibrated rank distribution is needed — SoftRank treats each score as a Gaussian random variable and computes Pr[item j ranks above item i] in closed form
**Expected speedup:** ≥5x over Python reference
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm
```
Input: scores s ∈ ℝ^n for one query, relevance labels y ∈ ℕ^n, noise std σ > 0
Output: SoftNDCG = E_{ŝ ~ N(s, σ²)}[NDCG(ŝ, y)]                                # Taylor 2008 §3

# 1. Rank distribution: Pr[item j is ranked above item i] under Gaussian noise
for each pair (i, j), i ≠ j:
    p_{ji} = Pr[ŝ_j > ŝ_i] = Φ((s_j − s_i) / (σ · sqrt(2)))                    # standard-normal CDF

# 2. Marginal rank distribution P_i(r) = Pr[π(i) = r], built via dynamic programming
# Each item independently above i contributes one to its rank with prob p_{ji}.
# Build P_i as a length-(n+1) PMF using the standard "Poisson-binomial" forward recursion:
P_i[0] = 1
for j ≠ i:
    P_i = (1 − p_{ji}) · P_i  +  p_{ji} · shift_right(P_i)                      # O(n) per j
# Final P_i[r] = Pr that item i is at rank r (1-indexed)

# 3. SoftNDCG = E[NDCG] under these independent rank distributions
gain(i)        = (2^{y_i} − 1) / IDCG
discount(r)    = 1 / log_2(1 + r)
SoftDCG        = Σ_i gain(i) · Σ_r P_i[r] · discount(r)
SoftNDCG       = SoftDCG                                                         # already normalised
loss           = 1 − SoftNDCG
```
- Time complexity: O(n³) for the n DP rolls × n update each
- Space complexity: O(n²) to hold all P_i; or O(n) if computed sequentially per-item
- Property: differentiable through Φ; recovers exact NDCG as σ → 0⁺

## Academic source
**Taylor, M., Guiver, J., Robertson, S., Minka, T. (2008).** "SoftRank: optimizing non-smooth rank metrics." *Proc. 1st ACM WSDM*, pp. 77-86. DOI: `10.1145/1341531.1341544`.

## C++ Interface (pybind11)
```cpp
void softrank(
    const float* scores, const int* labels, int n,
    float sigma,
    int truncation_k,                    // 0 = full, k > 0 = NDCG@k discount mask
    float* out_loss,
    float* out_grad_scores               // dLoss / dscores, length n
);
```

## Memory budget
- Runtime RAM: <12 MB (n ≤ 200, batch ≤ 16 queries via thread-local arena)
- Disk: <1 MB
- Allocation: thread-local arena holds the n × (n+1) P matrix; reused across the batch

## Performance target
- Python baseline: numpy + scipy.stats.norm CDF
- Target: ≥5x faster
- Benchmark: batch=8 × n ∈ {30, 100, 200}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in per-query kernel, NaN/Inf checks on scores and σ (σ ≤ 0 → ValueError), double accumulator for the DP P_i recursion (O(n²) FMAs per item — float drift compounds), `noexcept` destructors, no `std::function` in inner DP loop, Φ via `0.5 · erfcf(−z/sqrt(2))` (numerically stable for both tails), DP buffer `P_i` ping-pongs between two scratch vectors of size n+1 (no per-step allocation), SIMD DP-update kernel uses `_mm256_zeroupper()`, P_i normalisation Σ P_i[r] verified ≈ 1 (within 1e-5) at end of each item; failure raises ValueError.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_79.py` | Loss matches numpy reference within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥5x faster than numpy |
| 5 | Edge cases | n=1 (P_i = δ_1), σ=1e-3 (near-deterministic), σ=10 (heavy noise), all-equal scores pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Inline `erfcf`-based standard-normal CDF (no scipy dependency in C++)
- META-77 LambdaLoss (shares 2^y gain and IDCG helpers)

## Pipeline stage (non-conflict)
**Owns:** Gaussian rank-distribution listwise loss slot
**Alternative to:** META-76 ApproxNDCG, META-77 LambdaLoss, META-78 NeuralNDCG, META-80 Smooth-AP, META-81 listwise cross-entropy
**Coexists with:** META-29 bootstrap confidence (different role — uncertainty estimation), META-04 coordinate ascent

## Test plan
- All-equal scores + uniform labels: SoftNDCG = E[NDCG of random permutation]
- σ = 1e-3: SoftNDCG matches exact NDCG within 1e-3
- σ = 10: SoftNDCG ≈ E[NDCG of random permutation]
- n=1: loss = 1 − gain(1)·discount(1) / IDCG = 0
- Gradient finite-difference check: max |analytic − fd| ≤ 1e-3 (analytic via chain rule through Φ and DP)
