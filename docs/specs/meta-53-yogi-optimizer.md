# META-53 — Yogi

## Overview
**Category:** Optimizer (first-order, additive second-moment update for non-convex stability)
**Extension file:** `yogi_optimizer.cpp`
**Replaces/improves:** META-34 Adam — Adam's multiplicative v_t update can suffer from large adaptive lr blow-ups; Yogi replaces it with an additive sign-based update that controls the rate of v_t growth/decay
**Expected speedup:** ≥6x over PyTorch `tensorflow_addons.optimizers.Yogi` Python step
**RAM:** <24 MB | **Disk:** <1 MB

## Algorithm
```
Input: w_0 ∈ ℝ^d, η, β_1 (typ. 0.9), β_2 (typ. 0.999), ε
State: m_0 = 0, v_0 ∈ ℝ^d (init e.g. 1e-6 to avoid div-by-zero)

for t = 1..T:
    g_t = ∇f(w_{t−1})
    m_t  ← β_1·m_{t−1} + (1−β_1)·g_t
    # Yogi additive update (Zaheer 2018 eq. 5):
    v_t  ← v_{t−1} − (1−β_2) · sign(v_{t−1} − g_t²) · g_t²
    m̂_t ← m_t / (1 − β_1^t)
    v̂_t ← v_t / (1 − β_2^t)
    w_t ← w_{t−1} − η · m̂_t / (√v̂_t + ε)
```
- Time complexity: O(T · d)
- Space complexity: O(d) for m + O(d) for v
- Convergence: Zaheer 2018 Thm 4: O(1/√T) regret bound for non-convex stochastic objectives under standard assumptions

## Academic source
**Zaheer, M., Reddi, S., Sachan, D., Kale, S., & Kumar, S. (2018).** "Adaptive methods for nonconvex optimization." *Advances in Neural Information Processing Systems* (NeurIPS), 31. URL: `https://papers.nips.cc/paper_files/paper/2018/hash/90365351ccc7437a1309dc64e4db32a3`.

## C++ Interface (pybind11)
```cpp
// Yogi single step or batched run with additive v_t update
void yogi_step(
    double* w, double* m, double* v,
    const double* g, int d, int t,
    double lr, double beta1, double beta2, double eps
);
std::vector<double> yogi_run(
    const double* w0, int d,
    std::function<void(const double*, double*)> grad,
    int max_steps, double lr, double beta1, double beta2, double eps,
    double v_init
);
```

## Memory budget
- Runtime RAM: <24 MB (d ≤ 1M)
- Disk: <1 MB
- Allocation: aligned 64-byte buffers for w, m, v; in-place SIMD update; SIMD `sign` via bitmask

## Performance target
- Python baseline: TensorFlow Addons `tfa.optimizers.Yogi`
- Target: ≥6x faster (CPU)
- Benchmark: d ∈ {1k, 100k, 1M}, 1000 steps each

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Wall` through `-Werror`, no raw `new`/`delete`, SIMD AVX2 sign+conditional with `_mm256_zeroupper()`, flush-to-zero on init, NaN/Inf entry checks (sign(NaN) guarded), `noexcept` destructors, β_1, β_2 ∈ (0,1) guards, ε > 0, v_init > 0 to prevent division by zero, no `std::function` in per-coord loop.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_53.py` | Matches TFA Yogi within 1e-6 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than TFA CPU |
| 5 | Edge cases | v_init = 0 raises / sign(0) handled / NaN raises / d=1M pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- None (standalone optimizer step)

## Pipeline stage (non-conflict)
**Owns:** first-order adaptive optimizer slot
**Alternative to:** META-34 Adam, META-46–49, META-51 RAdam, META-52 Lion
**Coexists with:** META-50 Lookahead, META-54 GP-EI HPO

## Test plan
- Non-convex synthetic loss: more stable v_t trajectory than Adam (verify max(v_t) bounded)
- v_init = 0: raises `ValueError`
- sign(v − g²) at exact equality: returns 0 (no update to v)
- NaN in g: raises `ValueError`
- d=1M, 1000 steps: meets target time
