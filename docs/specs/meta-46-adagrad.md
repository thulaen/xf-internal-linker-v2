# META-46 — AdaGrad

## Overview
**Category:** Optimizer (first-order, per-parameter adaptive learning rate)
**Extension file:** `adagrad.cpp`
**Replaces/improves:** META-34 Adam baseline for sparse-feature regimes (CTR, embedding tail) where cumulative squared gradients give better convergence than EMA
**Expected speedup:** ≥6x over PyTorch `torch.optim.Adagrad` step in pure-python loops; ≥1.5x on GPU-equivalent workloads
**RAM:** <16 MB | **Disk:** <1 MB

## Algorithm
```
Input: w_0 ∈ ℝ^d, learning rate η, ε > 0
State: G_0 = 0 ∈ ℝ^d (cumulative squared gradients)

for t = 1..T:
    g_t = ∇f(w_{t−1})
    G_t ← G_{t−1} + g_t ⊙ g_t                    # element-wise (Duchi et al. 2011 eq. 5)
    w_t ← w_{t−1} − η · g_t / (√G_t + ε)         # update: w_t = w_{t−1} − η·g_t / √(G_t + ε)
```
- Time complexity: O(T · d) per step
- Space complexity: O(d) — diagonal accumulator only
- Convergence: Duchi 2011 Thm 5: regret bound O(√T · max_t‖g_t‖∞) for convex losses, sub-linear for sparse gradients

## Academic source
**Duchi, J., Hazan, E., & Singer, Y. (2011).** "Adaptive subgradient methods for online learning and stochastic optimization." *Journal of Machine Learning Research*, 12, 2121-2159. URL: `https://www.jmlr.org/papers/v12/duchi11a.html`.

## C++ Interface (pybind11)
```cpp
// AdaGrad single step or batched run with cumulative-grad-square accumulator
void adagrad_step(
    double* w, double* G, const double* g, int d,
    double lr, double eps
);
std::vector<double> adagrad_run(
    const double* w0, int d,
    std::function<void(const double*, double*)> grad,
    int max_steps, double lr, double eps
);
```

## Memory budget
- Runtime RAM: <16 MB (d ≤ 1M → 8 MB for w + 8 MB for G)
- Disk: <1 MB
- Allocation: aligned 64-byte `std::vector<double>` for w and G; in-place SIMD update

## Performance target
- Python baseline: PyTorch `torch.optim.Adagrad` Python step
- Target: ≥6x faster (CPU, pure step) on d ∈ {1k, 100k, 1M}
- Benchmark: 3-size sweep, 1000 steps each

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete` (in-place update), SIMD AVX2/AVX-512 with `_mm256_zeroupper()`, flush-to-zero on init (denormals from `g²` near 0), NaN/Inf entry checks on g_t, `noexcept` destructors, ε strictly positive guard, no `std::function` inside per-coord loop.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_46.py` | Matches PyTorch Adagrad within 1e-6 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than PyTorch CPU |
| 5 | Edge cases | Sparse g (95% zeros) / NaN / d=1M pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races (single-threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- None (standalone optimizer step)

## Pipeline stage (non-conflict)
**Owns:** first-order adaptive optimizer slot
**Alternative to:** META-34 Adam, META-47 AdaDelta, META-48 Nadam, META-49 AMSGrad, META-51 RAdam, META-52 Lion, META-53 Yogi
**Coexists with:** META-50 Lookahead (wraps any of the above), META-54 GP-EI HPO over η, ε

## Test plan
- Convex logistic regression: matches PyTorch loss curve within 1e-6
- Sparse gradient (95% zeros): only touched coords update; verify O(nnz) cost path
- Identity at minimum (g = 0): w unchanged
- NaN in g: raises `ValueError`
- d=1M, 1000 steps: meets target time
