# META-47 — AdaDelta

## Overview
**Category:** Optimizer (first-order, adaptive learning rate, units-correcting)
**Extension file:** `adadelta.cpp`
**Replaces/improves:** META-46 AdaGrad whose monotonically growing G_t causes the effective learning rate to vanish; AdaDelta uses an EMA window so learning continues
**Expected speedup:** ≥6x over PyTorch `torch.optim.Adadelta` Python step
**RAM:** <24 MB | **Disk:** <1 MB

## Algorithm
```
Input: w_0 ∈ ℝ^d, decay ρ ∈ (0,1) (typ. 0.95), ε > 0
State: E[g²]_0 = 0, E[Δw²]_0 = 0   (both ∈ ℝ^d)

for t = 1..T:
    g_t = ∇f(w_{t−1})
    E[g²]_t  ← ρ · E[g²]_{t−1}  + (1−ρ) · g_t²              # Zeiler 2012 eq. (8)
    Δw_t     ← −(√(E[Δw²]_{t−1} + ε) / √(E[g²]_t + ε)) · g_t  # units-correcting factor, eq. (14)
    E[Δw²]_t ← ρ · E[Δw²]_{t−1} + (1−ρ) · Δw_t²
    w_t       ← w_{t−1} + Δw_t
```
- Time complexity: O(T · d) per step
- Space complexity: O(d) for E[g²] + O(d) for E[Δw²]
- Convergence: empirically robust; no published regret bound, see Zeiler 2012 §3 and §4 for empirical analysis

## Academic source
**Zeiler, M. D. (2012).** "ADADELTA: An adaptive learning rate method." arXiv preprint arXiv:`1212.5701`. URL: `https://arxiv.org/abs/1212.5701`.

## C++ Interface (pybind11)
```cpp
// AdaDelta single step or batched run with two EMA accumulators
void adadelta_step(
    double* w, double* Eg2, double* Edw2,
    const double* g, int d,
    double rho, double eps
);
std::vector<double> adadelta_run(
    const double* w0, int d,
    std::function<void(const double*, double*)> grad,
    int max_steps, double rho, double eps
);
```

## Memory budget
- Runtime RAM: <24 MB (d ≤ 1M → 8 MB w + 8 MB Eg2 + 8 MB Edw2)
- Disk: <1 MB
- Allocation: aligned 64-byte buffers; in-place SIMD update

## Performance target
- Python baseline: PyTorch `torch.optim.Adadelta` step
- Target: ≥6x faster (CPU)
- Benchmark: d ∈ {1k, 100k, 1M}, 1000 steps each

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete`, SIMD AVX2 with `_mm256_zeroupper()`, flush-to-zero on init, NaN/Inf entry checks, `noexcept` destructors, ρ ∈ (0,1) guard, ε > 0 guard, no `std::function` in per-coord loop.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_47.py` | Matches PyTorch Adadelta within 1e-6 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than PyTorch CPU |
| 5 | Edge cases | g=0 / NaN / d=1M / very small ε pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- None (standalone optimizer step)

## Pipeline stage (non-conflict)
**Owns:** first-order adaptive optimizer slot
**Alternative to:** META-34 Adam, META-46 AdaGrad, META-48 Nadam, META-49 AMSGrad, META-51 RAdam, META-52 Lion, META-53 Yogi
**Coexists with:** META-50 Lookahead, META-54 GP-EI HPO over ρ, ε

## Test plan
- Convex logistic regression: matches PyTorch within 1e-6
- Long horizon (10000 steps): no learning-rate decay-to-zero issue (vs AdaGrad)
- Identity at minimum: w unchanged
- NaN in g: raises `ValueError`
- d=1M, 1000 steps: meets target time
