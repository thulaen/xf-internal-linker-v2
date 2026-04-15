# META-76 — ApproxNDCG Listwise Loss

## Overview
**Category:** Listwise ranking loss (smooth surrogate for NDCG via sigmoid-relaxed sort)
**Extension file:** `approx_ndcg.cpp`
**Replaces/improves:** Pairwise META-20 / META-21 / META-22 losses when end-to-end NDCG@k is the reported metric and gradient-based optimisation directly on a smoothed NDCG is preferred
**Expected speedup:** ≥6x over PyTorch reference (`pytorchltr.loss.ApproxNDCGLoss`)
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm
```
Input: scores s ∈ ℝ^n for one query, relevance labels y ∈ ℕ^n, sigmoid sharpness α > 0
Output: smooth NDCG approximation in [0, 1] (loss = 1 − approx_ndcg)

# 1. Smooth rank: replace 1[s_j > s_i] with σ(α · (s_j − s_i))                 # Qin, Liu, Li 2010 §3.2
for i = 1..n:
    π̂(i) = 1 + Σ_{j ≠ i} σ(α · (s_j − s_i))                                    # smooth (1-indexed) rank

# 2. Substitute π̂ into NDCG gain / discount
gain(i)     = 2^{y_i} − 1                                                       # standard NDCG gain
discount(i) = 1 / log_2(1 + π̂(i))                                              # smooth discount (π̂ is real)

DCG_smooth  = Σ_i  gain(i) · discount(i)
IDCG        = Σ_i  gain(σ_y(i)) · 1/log_2(1+i)         # ideal sort by y, exact integer ranks
approx_ndcg = DCG_smooth / IDCG
loss        = 1 − approx_ndcg
```
- Time complexity: O(n²) for the all-pairs smooth-rank sum
- Space complexity: O(n) for π̂
- Property: as α → ∞, π̂ → exact integer rank and ApproxNDCG → exact NDCG; differentiable for any finite α

## Academic source
**Qin, T., Liu, T.-Y., Li, H. (2010).** "A general approximation framework for direct optimization of information retrieval measures." *Information Retrieval* 13(4):375-397. DOI: `10.1007/s10791-009-9124-x`.

## C++ Interface (pybind11)
```cpp
// Forward + backward in one call (per-query batch); writes loss and ds/dscores
void approx_ndcg(
    const float* scores, const int* labels, int n,
    float alpha,
    int truncation_k,                  // 0 = full NDCG, k > 0 = NDCG@k via discount mask
    float* out_loss,
    float* out_grad_scores             // dLoss / dscores, length n
);
```

## Memory budget
- Runtime RAM: <12 MB (n ≤ 1000 candidates per query, batch ≤ 64 queries; aligned 64-byte for π̂ matrix scratch)
- Disk: <1 MB
- Allocation: per-query scratch reused across the batch via thread-local arena

## Performance target
- Python baseline: `pytorchltr.loss.ApproxNDCGLoss` with autograd
- Target: ≥6x faster (autograd traversal eliminated; analytic gradient hand-rolled)
- Benchmark: batch=32 × n ∈ {50, 200, 1000}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in per-query kernel, NaN/Inf checks on scores and labels (NaN score → loss = 1, gradient = 0 for that query), double accumulator for the all-pairs sigmoid sum (Σ over n−1 sigmoids per i), `noexcept` destructors, no `std::function` in inner pair loop, σ(z) implemented as numerically stable `1/(1+expf(−z))` with branch on sign(z) to prevent overflow when α·Δs is large negative (use `expf(z)/(1+expf(z))` for z > 0), analytic gradient derived once (not via autograd) using ∂π̂(i)/∂s_k = α·σ'·(δ_ik − δ_jk-style indicator), SIMD sigmoid kernel uses `_mm256_zeroupper()`, IDCG cached per query (does not depend on scores).

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_76.py` | Loss and gradient match PyTorch autograd within 1e-4 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than PyTorch |
| 5 | Edge cases | n=1 (loss=0), all-equal labels (IDCG=0 → loss=0), all-equal scores, large α (=1e3) pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-09 quantile normaliser (optional pre-processing of scores for stability)
- Inline numerically-stable sigmoid + log2 helpers

## Pipeline stage (non-conflict)
**Owns:** smooth-rank listwise NDCG-surrogate slot
**Alternative to:** META-77 LambdaLoss, META-78 NeuralNDCG, META-79 SoftRank, META-81 listwise cross-entropy
**Coexists with:** META-20/21/22 pairwise losses (different loss family — can be linearly combined as a multi-task term), META-04 coordinate ascent (treats this as the objective)

## Test plan
- Single relevant doc at top: loss → 0 (within 1e-3) for any α ≥ 10
- Single relevant doc at bottom: loss → 1 − 1/log_2(1+n) for large α
- All-zero labels: IDCG = 0 → loss returns 0 (avoid NaN division)
- Large α (=1e3): smooth NDCG matches exact NDCG within 1e-3
- Gradient finite-difference check: max |analytic − fd| ≤ 1e-3
