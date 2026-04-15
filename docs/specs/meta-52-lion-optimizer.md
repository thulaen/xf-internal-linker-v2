# META-52 — Lion (EvoLved Sign Momentum)

## Overview
**Category:** Optimizer (first-order, sign-of-momentum, memory-light)
**Extension file:** `lion_optimizer.cpp`
**Replaces/improves:** META-34 Adam — Lion uses only one state (momentum) instead of two (m + v), halving memory; it computes the sign of an interpolated momentum, eliminating square-root and square operations
**Expected speedup:** ≥8x over PyTorch `Lion` Python step (Lion is faster per-step than Adam by design)
**RAM:** <16 MB | **Disk:** <1 MB

## Algorithm
```
Input: w_0 ∈ ℝ^d, η, β_1 (typ. 0.9), β_2 (typ. 0.99), weight decay λ
State: m_0 = 0 ∈ ℝ^d

for t = 1..T:
    g_t = ∇f(w_{t−1})
    c_t  ← β_1·m_{t−1} + (1−β_1)·g_t                   # interpolated momentum (Chen 2023 eq. 3)
    w_t  ← w_{t−1} − η · ( sign(c_t) + λ·w_{t−1} )      # update: w_t = w_{t−1} − η·sign(...)
    m_t  ← β_2·m_{t−1} + (1−β_2)·g_t                   # momentum updated AFTER weight step
```
- Time complexity: O(T · d) per step — pure linear, no sqrt
- Space complexity: O(d) — single momentum buffer (vs 2 for Adam)
- Convergence: empirically validated; Chen 2023 §3 Tab. 1 — beats Adam on ViT/ImageNet

## Academic source
**Chen, X., Liang, C., Huang, D., Real, E., Wang, K., Liu, Y., Pham, H., Dong, X., Luong, T., Hsieh, C.-J., Lu, Y., & Le, Q. V. (2023).** "Symbolic Discovery of Optimization Algorithms." arXiv preprint arXiv:`2302.06675`. URL: `https://arxiv.org/abs/2302.06675`.

## C++ Interface (pybind11)
```cpp
// Lion single step or batched run; only one state buffer (momentum)
void lion_step(
    double* w, double* m, const double* g, int d,
    double lr, double beta1, double beta2, double weight_decay
);
std::vector<double> lion_run(
    const double* w0, int d,
    std::function<void(const double*, double*)> grad,
    int max_steps, double lr, double beta1, double beta2, double weight_decay
);
```

## Memory budget
- Runtime RAM: <16 MB (d ≤ 1M → 8 MB w + 8 MB m only)
- Disk: <1 MB
- Allocation: two aligned 64-byte `std::vector<double>`; in-place SIMD update; SIMD `sign` via bit-mask

## Performance target
- Python baseline: PyTorch `lion-pytorch` package
- Target: ≥8x faster (CPU) — Lion's simplicity means C++ step is dominated by memory bandwidth
- Benchmark: d ∈ {1k, 100k, 1M}, 1000 steps each

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete`, SIMD AVX2 sign via `_mm256_or_pd` and `_mm256_and_pd` with bitmask, `_mm256_zeroupper()`, flush-to-zero on init (sign of denormal handled), NaN/Inf entry checks (sign(NaN) is implementation-defined — guard explicitly), `noexcept` destructors, β_1, β_2 ∈ (0,1), no `std::function` in per-coord loop.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_52.py` | Matches `lion-pytorch` within 1e-6 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥8x faster than PyTorch CPU |
| 5 | Edge cases | sign(0) = 0 / sign(NaN) raises / d=1M pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- None (standalone optimizer step)

## Pipeline stage (non-conflict)
**Owns:** first-order adaptive optimizer slot
**Alternative to:** META-34 Adam, META-46–49, META-51 RAdam, META-53 Yogi
**Coexists with:** META-50 Lookahead, META-54 GP-EI HPO

## Test plan
- Convex logistic regression: converges; Chen 2023 reports comparable end loss to Adam at lower memory
- sign(0) handling: matches reference (Lion paper specifies sign(0) = 0)
- NaN in g: raises `ValueError`
- Memory check: peak RSS within 50% of Adam (single state buffer)
- d=1M, 1000 steps: meets target time
