# META-71 — Online Newton Step

## Overview
**Category:** Online learner (quasi-Newton, exp-concave loss)
**Extension file:** `online_newton_step.cpp`
**Replaces/improves:** META-74 projected OGD when the loss is exp-concave (e.g. log-loss with bounded weights) — ONS gives O(log T) regret vs OGD's O(√T)
**Expected speedup:** ≥6x over Python reference implementation
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm
```
Input: convex compact set K ⊂ ℝ^d, exp-concave loss L_t, learning rate η, regularisation ε
Output: weight sequence w_1, w_2, ..., w_T

initialise w_1 ∈ K; A_0 = ε · I_d                                         # Hazan, Agarwal, Kale 2007 §3
for t = 1..T:
    receive L_t; play w_t; suffer L_t(w_t)
    g_t = ∇L_t(w_t)
    A_t = A_t-1 + g_t · g_tᵀ                                              # rank-1 update
    y_{t+1} = w_t − (1/η) · A_t⁻¹ · g_t                                   # quasi-Newton step
    w_{t+1} = Π_K^{A_t}(y_{t+1}) = argmin_{w ∈ K} (w − y_{t+1})ᵀ A_t (w − y_{t+1})
```
- A_t⁻¹ maintained incrementally via Sherman-Morrison: A_t⁻¹ = A_{t−1}⁻¹ − (A_{t−1}⁻¹·g_t·g_tᵀ·A_{t−1}⁻¹) / (1 + g_tᵀ·A_{t−1}⁻¹·g_t)
- Time complexity: O(d²) per step (Sherman-Morrison + projection)
- Space complexity: O(d²) for A_t⁻¹
- Regret bound: O((1/α + GD)·d·log T) for α-exp-concave losses (Hazan 2007 Thm 3)

## Academic source
**Hazan, E., Agarwal, A., Kale, S. (2007).** "Logarithmic regret algorithms for online convex optimization." *Machine Learning* 69(2-3):169-192. DOI: `10.1007/s10994-007-5016-8`.

## C++ Interface (pybind11)
```cpp
struct ONSState {
    std::vector<double> A_inv;     // d × d, row-major, double for stability
    std::vector<float>  w;         // d
    int d;
    float eta, eps;
};

void ons_step(
    ONSState& s,
    const float* gradient,                    // dense d-vector
    std::function<void(float*, int)> project   // projects onto K under A-norm; in-place
);
```

## Memory budget
- Runtime RAM: <20 MB (d ≤ 500 → 1 MB for A_inv, plus scratch)
- Disk: <1 MB
- Allocation: aligned 64-byte for A_inv (double) and gradient scratch

## Performance target
- Python baseline: numpy Sherman-Morrison + scipy projection
- Target: ≥6x faster
- Benchmark: d ∈ {50, 200, 500} × 10k steps, log-loss

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in step kernel, NaN/Inf checks on gradient and on Sherman-Morrison denominator (1 + gᵀA⁻¹g — must be > 0; if ≤ 1e-12 skip update and warn), double accumulator throughout (A_inv stored as double to prevent drift over 1M steps), `noexcept` destructors, no `std::function` in inner SIMD GEMV (cache projection callable once outside the inner kernel), SIMD GEMV uses `_mm256_zeroupper()` after each call, A_inv symmetry enforced periodically (`A_inv = (A_inv + A_invᵀ)/2` every 1000 steps to prevent rounding-induced asymmetry), projection callback wrapped in pybind11 GIL-release/acquire pattern.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_71.py` | Cumulative regret matches numpy reference within 1% over 10k steps |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than Python |
| 5 | Edge cases | d=1, g=0, ε=0 (singular A_0), 1M steps without drift pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-12 Cholesky / inline LAPACKE for occasional A_inv re-symmetrisation
- META-19 max-norm clipper as the default projection (when K is a box)

## Pipeline stage (non-conflict)
**Owns:** quasi-Newton online optimiser slot (exp-concave losses, dense d ≤ 500)
**Alternative to:** META-70 FTRL-Proximal (sparse L1), META-72 OMD (Bregman-divergence), META-74 projected OGD (cheaper but worse regret)
**Coexists with:** META-75 streaming ADMM (consensus across blocks), META-25 sliding-window retrainer

## Test plan
- Online linear regression: cumulative regret grows like log(T), not √T
- d=1: degenerates to scaled gradient step, matches OGD trajectory after rescaling
- Repeated identical gradient: A_inv → 0 along that direction, weight stops moving (correct behaviour)
- ε=0 + first gradient zero: A_t still singular — must skip update, no NaN propagation
- 1M-step run: A_inv symmetry deviation ≤ 1e-6 (max(|A_inv − A_invᵀ|) check)
