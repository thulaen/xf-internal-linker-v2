# META-49 — AMSGrad

## Overview
**Category:** Optimizer (first-order, Adam variant with non-decreasing v̂ for proven convergence)
**Extension file:** `amsgrad.cpp`
**Replaces/improves:** META-34 Adam, which Reddi et al. 2018 showed can fail to converge on certain convex problems; AMSGrad fixes this with `v̂_t = max(v̂_{t−1}, v_t)`
**Expected speedup:** ≥6x over PyTorch `torch.optim.Adam(amsgrad=True)` Python step
**RAM:** <32 MB | **Disk:** <1 MB

## Algorithm
```
Input: w_0 ∈ ℝ^d, η, β_1 (typ. 0.9), β_2 (typ. 0.999), ε
State: m_0 = 0, v_0 = 0, v̂_0 = 0 ∈ ℝ^d

for t = 1..T:
    g_t = ∇f(w_{t−1})
    m_t  ← β_1·m_{t−1} + (1−β_1)·g_t
    v_t  ← β_2·v_{t−1} + (1−β_2)·g_t²
    v̂_t  ← max(v̂_{t−1}, v_t)                       # element-wise max (Reddi 2018 eq. 6)
    w_t  ← w_{t−1} − η · m_t / (√v̂_t + ε)         # use v̂_t, NOT bias-corrected v_t
```
- Time complexity: O(T · d)
- Space complexity: O(d) for m, v, v̂ — three buffers
- Convergence: Reddi, Kale, Kumar 2018 Thm 4: data-dependent regret bound O(√T) for online convex optimisation

## Academic source
**Reddi, S. J., Kale, S., & Kumar, S. (2018).** "On the convergence of Adam and beyond." *International Conference on Learning Representations* (ICLR), Best Paper Award. URL: `https://openreview.net/forum?id=ryQu7f-RZ`. arXiv: `1904.09237`.

## C++ Interface (pybind11)
```cpp
// AMSGrad single step or batched run; v_hat is the running maximum of v_t
void amsgrad_step(
    double* w, double* m, double* v, double* v_hat,
    const double* g, int d,
    double lr, double beta1, double beta2, double eps
);
std::vector<double> amsgrad_run(
    const double* w0, int d,
    std::function<void(const double*, double*)> grad,
    int max_steps, double lr, double beta1, double beta2, double eps
);
```

## Memory budget
- Runtime RAM: <32 MB (d ≤ 1M → 8 MB each for w, m, v, v̂)
- Disk: <1 MB
- Allocation: aligned 64-byte `std::vector<double>`; in-place SIMD update; AVX2 `_mm256_max_pd` for v̂ update

## Performance target
- Python baseline: PyTorch `torch.optim.Adam(amsgrad=True)`
- Target: ≥6x faster (CPU)
- Benchmark: d ∈ {1k, 100k, 1M}, 1000 steps each

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete`, SIMD AVX2 max with `_mm256_zeroupper()`, flush-to-zero on init, NaN/Inf entry checks (NaN propagates incorrectly through `max` — guard explicitly), `noexcept` destructors, β_1, β_2 ∈ (0,1) guards, ε > 0, no `std::function` in per-coord loop.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_49.py` | Matches PyTorch AMSGrad within 1e-6 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than PyTorch CPU |
| 5 | Edge cases | NaN propagation through max / d=1M / monotone v̂ verified |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- None (standalone optimizer step)

## Pipeline stage (non-conflict)
**Owns:** first-order adaptive optimizer slot
**Alternative to:** META-34 Adam, META-46 AdaGrad, META-47 AdaDelta, META-48 Nadam, META-51 RAdam, META-52 Lion, META-53 Yogi
**Coexists with:** META-50 Lookahead, META-54 GP-EI HPO

## Test plan
- Reddi 2018 §3 counter-example (synthetic): Adam fails, AMSGrad converges
- Convex logistic regression: matches PyTorch within 1e-6
- v̂ monotonicity invariant: verify v̂_t ≥ v̂_{t−1} element-wise across run
- NaN in g: raises `ValueError` (do not silently propagate via max)
- d=1M, 1000 steps: meets target time
