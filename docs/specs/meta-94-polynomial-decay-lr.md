# META-94 — Polynomial Decay LR

## Overview
**Category:** Learning-rate scheduler (P10 LR schedulers block)
**Extension file:** `polynomial_decay_lr.cpp`
**Replaces/improves:** Constant LR with controllable decay curvature; p = 1 yields linear decay (paper-recommended for many large-batch settings), p = 2 yields quadratic
**Expected speedup:** N/A — convergence improvement; CPU work negligible
**RAM:** <1 KB | **Disk:** <1 MB

## Algorithm

```
Input: η_0 (initial), η_end (floor, default 0), T total steps, polynomial power p > 0
State: step t

Per-step update:
  η_t = (η_0 − η_end) · (1 − t/T)^p  +  η_end           for t < T
  η_t = η_end                                            for t ≥ T

Special cases:
  p = 1   → linear decay
  p = 2   → quadratic decay (concave, slow at start, fast at end — Goyal et al. recommended)
  p = 0.5 → square-root decay
  p → ∞  → step-like (drops at the very end)
```

- **Time complexity:** O(1) per step (one `pow`)
- **Space complexity:** O(1)
- **Convergence:** Smooth monotone — pairs naturally with linear-warmup phase if needed

## Academic source
Goyal, P., Dollár, P., Girshick, R., Noordhuis, P., Wesolowski, L., Kyrola, A., Tulloch, A., Jia, Y. and He, K., "Accurate, Large Minibatch SGD: Training ImageNet in 1 Hour", arXiv:1706.02677, 2017 — polynomial-decay schedule recommended in Section 2.2.

## C++ Interface (pybind11)

```cpp
class PolynomialDecayLR {
public:
    PolynomialDecayLR(float eta_0, float eta_end, int T, float power);
    float step();
    float peek(int t) const;
    void  reset();
    int   current_step() const;
};
```

## Memory Budget
- Runtime RAM: <1 KB
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: zero per-step

## Performance Target
- Python baseline: hand-rolled NumPy implementation
- Target: parity within 1e-7
- Benchmark: 3 sizes — 100, 10000, 1000000 sequential `step()` calls

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Single-thread.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate η_0 ≥ η_end ≥ 0, T ≥ 1, power > 0.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Scalar `pow` — fast-path for p ∈ {1, 2, 0.5} with multiplication / sqrt.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. `pow` in `double` then narrow to `float`. Clamp `(1 − t/T)` to ≥ 0 before `pow` to avoid NaN at t > T.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. Stepping past T returns η_end (do not throw).

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_94.py` | Matches NumPy reference within 1e-7 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_polynomial.py` | <60 ns per `step()` for p ∈ {1,2,0.5} on 3 sizes |
| 5 | `pytest test_edges_meta_94.py` | T=1, p=0.5, p=1, p=2, t > T (clamped), η_end=0 handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Boundary | At t=0 → η_0; at t=T → η_end exactly |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps

## Pipeline stage non-conflict declaration
- **Owns:** Polynomial LR decay with configurable order
- **Alternative to:** META-91 cosine, META-92 1-cycle, META-93 transformer warmup, META-95 step decay
- **Coexists with:** All P8 regularisers, all P9 calibrators; do not stack with another LR scheduler

## Test Plan
- p = 1, η_0 = 1, η_end = 0, T = 100: verify η at t = 50 = 0.5 (linear midpoint)
- p = 2: verify η at t = 50 = 0.25 (quadratic)
- p = 0.5: verify η at t = 50 = sqrt(0.5) ≈ 0.707
- t = T: verify η = η_end exactly
- t > T: verify clamps to η_end (no negative or NaN)
