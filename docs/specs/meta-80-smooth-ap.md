# META-80 — Smooth-AP Listwise Loss

## Overview
**Category:** Listwise ranking loss (smoothed Average Precision via sigmoid-relaxed indicators)
**Extension file:** `smooth_ap.cpp`
**Replaces/improves:** META-76/77/78 NDCG-surrogates when the operating metric is **Average Precision** (binary relevance, e.g. retrieval / re-ranking) rather than graded NDCG; Smooth-AP optimises AP directly with a single batchwise tempered sigmoid
**Expected speedup:** ≥6x over PyTorch reference (`pytorch-metric-learning.losses.SmoothAP`)
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm
```
Input: scores s ∈ ℝ^n for one query, binary labels y ∈ {0,1}^n, sigmoid sharpness τ > 0
       P = {i : y_i = 1}, N = {i : y_i = 0}
Output: Smooth-AP ∈ [0, 1] (loss = 1 − Smooth-AP)

# Standard AP for one query (binary case):
#   AP = (1/|P|) · Σ_{i ∈ P}  precision@rank(i)
#      = (1/|P|) · Σ_{i ∈ P}  (1 + |{j ∈ P, j ≠ i: s_j > s_i}|) / (1 + |{j ≠ i: s_j > s_i}|)
#
# Smooth-AP (Brown et al. 2020 §3): replace 1[s_j > s_i] with σ((s_j − s_i)/τ)
for each i ∈ P:                                                                 # Brown 2020 eq. (4)
    rank_pos_smooth(i) = 1 + Σ_{j ∈ P, j ≠ i}      σ((s_j − s_i)/τ)            # smoothed positive rank
    rank_all_smooth(i) = 1 + Σ_{j ∈ (P ∪ N), j ≠ i} σ((s_j − s_i)/τ)           # smoothed total rank

AP_smooth = (1/|P|) · Σ_{i ∈ P}  rank_pos_smooth(i) / rank_all_smooth(i)
loss      = 1 − AP_smooth
```
- Time complexity: O(n · |P|) for the per-positive sweep
- Space complexity: O(|P|) for the running sums
- Property: as τ → 0⁺, σ → step function and Smooth-AP → exact AP; differentiable for any τ > 0; gradient is well-conditioned because both sums share the same sigmoid factor

## Academic source
**Brown, A., Xie, W., Kalogeiton, V., Zisserman, A. (2020).** "Smooth-AP: smoothing the path towards large-scale image retrieval." *Proc. ECCV 2020*, LNCS 12350, pp. 677-694. DOI: `10.1007/978-3-030-58621-8_39`.

## C++ Interface (pybind11)
```cpp
void smooth_ap(
    const float* scores, const int* labels, int n,
    float tau,
    float* out_loss,
    float* out_grad_scores               // dLoss / dscores, length n
);
```

## Memory budget
- Runtime RAM: <12 MB (n ≤ 2000, batch ≤ 32 queries via thread-local scratch holding rank-sum vectors)
- Disk: <1 MB
- Allocation: per-query scratch reused across the batch via thread-local arena

## Performance target
- Python baseline: `pytorch-metric-learning.losses.SmoothAPLoss`
- Target: ≥6x faster (analytic backward + fused per-positive kernel)
- Benchmark: batch=16 × n ∈ {100, 500, 2000} × |P|/n ∈ {0.05, 0.2}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in per-query kernel, NaN/Inf checks on scores and τ (τ ≤ 0 → ValueError), double accumulator for the per-positive Σ-sigmoid sums (positive set can hold thousands of items), σ implemented as numerically stable two-branch `1/(1+expf(−z))` vs `expf(z)/(1+expf(z))` based on sign(z) to prevent overflow, `noexcept` destructors, no `std::function` in inner per-positive loop, |P|=0 short-circuit returns loss=0 (AP undefined for all-negative query — not an error), analytic gradient hand-rolled (∂σ/∂s_j contributes to two ranks per positive: rank_pos and rank_all), SIMD sigmoid kernel uses `_mm256_zeroupper()`.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_80.py` | Loss and gradient match PyTorch autograd within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than PyTorch |
| 5 | Edge cases | |P|=0 (loss=0), |P|=n (loss=0), τ=1e-3 (near-step), all-equal scores pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Inline numerically-stable sigmoid (shared with META-76 ApproxNDCG)
- None external

## Pipeline stage (non-conflict)
**Owns:** smoothed Average Precision listwise loss slot (binary relevance)
**Alternative to:** META-76/77/78/79 (NDCG surrogates — graded relevance)
**Coexists with:** META-20/21/22 pairwise losses, META-81 listwise cross-entropy

## Test plan
- All positives ranked above all negatives: Smooth-AP → 1 (within 1e-3 for τ ≤ 0.1)
- Random scores, |P|=1: AP = 1/rank(positive) — Smooth-AP matches within 1e-3 for small τ
- |P|=0: returns loss=0, no division by zero
- |P|=n (all positives): returns loss=0
- Gradient finite-difference check: max |analytic − fd| ≤ 1e-3
