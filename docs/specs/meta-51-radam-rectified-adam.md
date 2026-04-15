# META-51 — RAdam (Rectified Adam)

## Overview
**Category:** Optimizer (first-order, variance-rectified Adam)
**Extension file:** `radam.cpp`
**Replaces/improves:** META-34 Adam, which Liu et al. 2020 show has unstable adaptive learning rate in early steps; RAdam adds a closed-form variance rectification term ρ_t to remove the warm-up requirement
**Expected speedup:** ≥6x over PyTorch `torch.optim.RAdam` step
**RAM:** <24 MB | **Disk:** <1 MB

## Algorithm
```
Input: w_0 ∈ ℝ^d, η, β_1, β_2, ε
State: m_0 = 0, v_0 = 0 ∈ ℝ^d
ρ_∞ = 2/(1−β_2) − 1                                    # Liu 2020 eq. 5

for t = 1..T:
    g_t = ∇f(w_{t−1})
    m_t  ← β_1·m_{t−1} + (1−β_1)·g_t
    v_t  ← β_2·v_{t−1} + (1−β_2)·g_t²
    m̂_t ← m_t / (1 − β_1^t)
    ρ_t  ← ρ_∞ − 2·t·β_2^t / (1 − β_2^t)              # length of approximated SMA
    if ρ_t > 4:                                         # variance is tractable
        v̂_t ← √(v_t / (1 − β_2^t))
        r_t  ← √( (ρ_t − 4)·(ρ_t − 2)·ρ_∞ / ((ρ_∞ − 4)·(ρ_∞ − 2)·ρ_t) )   # rectification, eq. 9
        w_t ← w_{t−1} − η · r_t · m̂_t / (v̂_t + ε)
    else:                                              # fall back to SGD-with-momentum
        w_t ← w_{t−1} − η · m̂_t
```
- Time complexity: O(T · d) plus O(1) ρ_t computation
- Space complexity: O(d) for m + O(d) for v
- Convergence: Liu 2020 §4 — equivalent to Adam with adaptive warmup; matches Adam asymptotically

## Academic source
**Liu, L., Jiang, H., He, P., Chen, W., Liu, X., Gao, J., & Han, J. (2020).** "On the variance of the adaptive learning rate and beyond." *International Conference on Learning Representations* (ICLR). URL: `https://openreview.net/forum?id=rkgz2aEKDr`. arXiv: `1908.03265`.

## C++ Interface (pybind11)
```cpp
// RAdam single step or batched run; computes rho_t and rectification factor r_t
void radam_step(
    double* w, double* m, double* v,
    const double* g, int d, int t,
    double lr, double beta1, double beta2, double eps
);
std::vector<double> radam_run(
    const double* w0, int d,
    std::function<void(const double*, double*)> grad,
    int max_steps, double lr, double beta1, double beta2, double eps
);
```

## Memory budget
- Runtime RAM: <24 MB (d ≤ 1M)
- Disk: <1 MB
- Allocation: aligned 64-byte buffers for w, m, v; in-place SIMD update

## Performance target
- Python baseline: PyTorch `torch.optim.RAdam`
- Target: ≥6x faster (CPU)
- Benchmark: d ∈ {1k, 100k, 1M}, 1000 steps each

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete`, SIMD AVX2 with `_mm256_zeroupper()`, flush-to-zero on init, NaN/Inf entry checks on g, `noexcept` destructors, β_1, β_2 ∈ (0,1) guards, ε > 0, ρ_t branch tested for both `> 4` and `≤ 4` paths, no `std::function` in per-coord loop.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_51.py` | Matches PyTorch RAdam within 1e-6 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than PyTorch CPU |
| 5 | Edge cases | early steps (ρ_t ≤ 4 path) / NaN / d=1M pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- None (standalone optimizer step)

## Pipeline stage (non-conflict)
**Owns:** first-order adaptive optimizer slot
**Alternative to:** META-34 Adam, META-46 AdaGrad, META-47 AdaDelta, META-48 Nadam, META-49 AMSGrad, META-52 Lion, META-53 Yogi
**Coexists with:** META-50 Lookahead wrapper, META-54 GP-EI HPO

## Test plan
- Convex logistic regression: matches PyTorch within 1e-6
- Early-step path (ρ_t ≤ 4): verify SGD-with-momentum behaviour
- Late-step path: verify rectified Adam behaviour
- NaN in g: raises `ValueError`
- d=1M, 1000 steps: meets target time
