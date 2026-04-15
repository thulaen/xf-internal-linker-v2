# META-92 — 1-Cycle Learning Rate Policy

## Overview
**Category:** Learning-rate scheduler (P10 LR schedulers block)
**Extension file:** `one_cycle_lr.cpp`
**Replaces/improves:** Constant or stepped LR; 1-cycle (super-convergence) trains models in ~1/4 the epochs and often improves final accuracy
**Expected speedup:** N/A — convergence improvement; CPU work is negligible
**RAM:** <1 KB | **Disk:** <1 MB

## Algorithm

```
Input: η_init, η_max, η_final (= η_init / div_final, e.g. /1e4),
       total_steps T, pct_start ∈ (0,1) (fraction in warmup, paper: 0.3),
       optional momentum window (m_max, m_min)
State: current step t

Phase A — warmup (0 ≤ t < pct_start·T):
  η_t   = η_init  +  (η_max  − η_init) · (t / (pct_start·T))
  m_t   = m_max   −  (m_max  − m_min ) · (t / (pct_start·T))     (mirror)

Phase B — annealing + cooldown (pct_start·T ≤ t ≤ T):
  τ     = (t − pct_start·T) / ((1 − pct_start)·T)
  η_t   = η_max   +  (η_final − η_max) · cosine_anneal(τ)
  m_t   = m_min   +  (m_max   − m_min) · cosine_anneal(τ)

  where cosine_anneal(τ) = (1 − cos(π·τ)) / 2 ∈ [0,1]
```

- **Time complexity:** O(1) per step
- **Space complexity:** O(1)
- **Convergence:** Empirically achieves "super-convergence" — paper reports CIFAR-10 in 70 epochs vs 350 baseline

## Academic source
Smith, L. N., "A Disciplined Approach to Neural Network Hyper-Parameters: Part 1 — Learning Rate, Batch Size, Momentum, and Weight Decay", U.S. Naval Research Laboratory / U.S. Air Force Research Laboratory Technical Report, arXiv:1803.09820, 2018.

## C++ Interface (pybind11)

```cpp
class OneCycleLR {
public:
    OneCycleLR(float eta_init, float eta_max, float eta_final,
               int total_steps, float pct_start,
               float m_max = 0.95f, float m_min = 0.85f);
    struct StepOut { float lr; float momentum; };
    StepOut step();          // advances and returns (lr, momentum)
    void    reset();
    int     current_step() const;
};
```

## Memory Budget
- Runtime RAM: <1 KB
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: zero per-step

## Performance Target
- Python baseline: `torch.optim.lr_scheduler.OneCycleLR`
- Target: parity within 1e-6
- Benchmark: 3 sizes — 100, 10000, 1000000 sequential `step()` calls; verify O(1) per call

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Single-thread scheduler.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate 0 < pct_start < 1, η_final < η_max, m_min < m_max.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Scalar `cos` — no vectorisation needed.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. `cos` in `double` then narrow to `float`.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. Stepping past total_steps clamps at last value (do not throw).

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_92.py` | Matches PyTorch `OneCycleLR` within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_one_cycle.py` | <100 ns per `step()` call on 3 sizes |
| 5 | `pytest test_edges_meta_92.py` | pct_start=0.5, total_steps=1, T=2 (warmup 1 cooldown 1), m_max=m_min handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Boundary check | At t=0 → η_init; at t=pct_start·T → η_max; at t=T → η_final |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps

## Pipeline stage non-conflict declaration
- **Owns:** Triangular-then-cosine 1-cycle LR + mirrored momentum
- **Alternative to:** META-91 cosine warm restart, META-93 transformer warmup, META-94 polynomial decay, META-95 step decay
- **Coexists with:** All P8 regularisers, all P9 calibrators; do not stack with another LR scheduler

## Test Plan
- pct_start = 0.3, T = 100: verify warmup ends at step 30 with η = η_max
- η_init = η_max: verify warmup is no-op (constant during phase A)
- m_max = m_min: verify momentum constant throughout
- t = T (end): verify η = η_final, m = m_max
- Stepping past T: verify clamped (no error, returns last value)
