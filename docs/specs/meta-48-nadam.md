# META-48 — Nadam (Nesterov-Accelerated Adam)

## Overview
**Category:** Optimizer (first-order, Adam + Nesterov momentum)
**Extension file:** `nadam.cpp`
**Replaces/improves:** META-34 Adam baseline; Nadam typically converges faster on convex and mildly non-convex problems
**Expected speedup:** ≥6x over PyTorch `torch.optim.NAdam` Python step
**RAM:** <24 MB | **Disk:** <1 MB

## Algorithm
```
Input: w_0 ∈ ℝ^d, η, β_1 (typ. 0.9), β_2 (typ. 0.999), ε
State: m_0 = 0, v_0 = 0 ∈ ℝ^d

for t = 1..T:
    g_t = ∇f(w_{t−1})
    m_t  ← β_1·m_{t−1} + (1−β_1)·g_t
    v_t  ← β_2·v_{t−1} + (1−β_2)·g_t²
    # Nesterov-corrected first-moment estimate (Dozat 2016 eq. 5):
    m̂_t ← β_1 · m_t / (1 − β_1^{t+1}) + (1 − β_1) · g_t / (1 − β_1^t)
    v̂_t ← v_t / (1 − β_2^t)
    w_t ← w_{t−1} − η · m̂_t / (√v̂_t + ε)
```
- Time complexity: O(T · d)
- Space complexity: O(d) for m + O(d) for v
- Convergence: Dozat 2016 §3 — empirical superiority over Adam on MNIST, NLP; no formal regret bound

## Academic source
**Dozat, T. (2016).** "Incorporating Nesterov momentum into Adam." ICLR 2016 Workshop. URL: `https://openreview.net/forum?id=OM0jvwB8jIp57ZJjtNEZ`. Also: Stanford CS229 report (2016).

## C++ Interface (pybind11)
```cpp
// Nadam single step or batched run with bias-corrected m̂ using Nesterov form
void nadam_step(
    double* w, double* m, double* v,
    const double* g, int d, int t,
    double lr, double beta1, double beta2, double eps
);
std::vector<double> nadam_run(
    const double* w0, int d,
    std::function<void(const double*, double*)> grad,
    int max_steps, double lr, double beta1, double beta2, double eps
);
```

## Memory budget
- Runtime RAM: <24 MB (d ≤ 1M → 8 MB each for w, m, v)
- Disk: <1 MB
- Allocation: aligned 64-byte buffers; in-place SIMD update

## Performance target
- Python baseline: PyTorch `torch.optim.NAdam`
- Target: ≥6x faster (CPU)
- Benchmark: d ∈ {1k, 100k, 1M}, 1000 steps each

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete`, SIMD AVX2 with `_mm256_zeroupper()`, flush-to-zero on init, NaN/Inf entry checks, `noexcept` destructors, β_1, β_2 ∈ (0,1) guards, ε > 0, t ≥ 1 (avoid 1−β^0 = 0), no `std::function` in per-coord loop, double accumulator unnecessary (per-coord, no reductions).

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_48.py` | Matches PyTorch NAdam within 1e-6 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than PyTorch CPU |
| 5 | Edge cases | t=1 / NaN / d=1M / β_1 → 1 numerical guard pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- None (standalone optimizer step)

## Pipeline stage (non-conflict)
**Owns:** first-order adaptive optimizer slot
**Alternative to:** META-34 Adam, META-46 AdaGrad, META-47 AdaDelta, META-49 AMSGrad, META-51 RAdam, META-52 Lion, META-53 Yogi
**Coexists with:** META-50 Lookahead wrapper, META-54 GP-EI HPO

## Test plan
- Convex logistic regression: matches PyTorch within 1e-6, converges faster than Adam
- t=1 step: no division-by-zero in (1 − β^t)
- Identity at minimum: w unchanged
- NaN in g: raises `ValueError`
- d=1M, 1000 steps: meets target time
