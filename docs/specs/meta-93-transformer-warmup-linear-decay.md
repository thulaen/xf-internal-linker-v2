# META-93 — Transformer Warmup + Inverse-Sqrt Decay

## Overview
**Category:** Learning-rate scheduler (P10 LR schedulers block)
**Extension file:** `transformer_lr.cpp`
**Replaces/improves:** Constant LR for transformer-style attention components in cross-encoder reranker; warmup prevents early-step instability and inverse-sqrt decay matches paper recommendation
**Expected speedup:** N/A — convergence improvement; CPU work negligible
**RAM:** <1 KB | **Disk:** <1 MB

## Algorithm

```
Input: model dimension d_model, warmup_steps W
State: step t (1-indexed)

Per-step LR (paper Eq. 3, "Attention Is All You Need"):
  η_t = d_model^(-0.5) · min(t^(-0.5), t · W^(-1.5))

Two-phase interpretation:
  Phase A (t ≤ W):   η_t = d_model^(-0.5) · t · W^(-1.5)        (linear ramp up)
  Phase B (t > W):   η_t = d_model^(-0.5) · t^(-1.5)            (inverse-sqrt decay)

  At t = W:           both branches equal d_model^(-0.5) · W^(-0.5) — peak LR.
```

- **Time complexity:** O(1) per step
- **Space complexity:** O(1)
- **Convergence:** Standard for transformer training; warmup prevents Adam second-moment instability with poorly-initialised attention

## Academic source
Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł. and Polosukhin, I., "Attention Is All You Need", *Advances in Neural Information Processing Systems (NIPS)*, 2017 — schedule defined in Section 5.3, Equation 3.

## C++ Interface (pybind11)

```cpp
class TransformerLR {
public:
    TransformerLR(int d_model, int warmup_steps);
    float step();           // returns η for current step, advances t
    float peek(int t) const; // pure function, no state change
    void  reset();
    int   current_step() const;
};
```

## Memory Budget
- Runtime RAM: <1 KB
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: zero per-step

## Performance Target
- Python baseline: hand-rolled NumPy implementation of paper Eq. 3
- Target: parity within 1e-7
- Benchmark: 3 sizes — 100, 10000, 1000000 sequential `step()` calls; verify O(1) per call

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Single-thread.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate d_model ≥ 1, warmup_steps ≥ 1.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Scalar `pow`/`sqrt` — use `1.0/std::sqrt` instead of `std::pow(x, -0.5)` for speed.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Use `double` for the `pow`/`sqrt` then narrow to `float` to prevent drift over millions of steps. Pre-compute `d_model^(-0.5)` and `W^(-1.5)` in constructor.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. t = 0 raises (formula is for t ≥ 1, paper is 1-indexed); first call sets t = 1 internally.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_93.py` | Matches NumPy reference within 1e-7 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_transformer_lr.py` | <80 ns per `step()` call on 3 sizes |
| 5 | `pytest test_edges_meta_93.py` | warmup_steps=1, t=W (peak), t=W+1, very large t (1e9) handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Continuity | At t = W, the two branches agree to 1e-7 |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps

## Pipeline stage non-conflict declaration
- **Owns:** Inverse-sqrt warmup → inverse-sqrt decay schedule
- **Alternative to:** META-91 cosine warm restart, META-92 1-cycle, META-94 polynomial decay, META-95 step decay
- **Coexists with:** All P8 regularisers, all P9 calibrators; do not stack with another LR scheduler

## Test Plan
- d_model = 512, warmup = 4000 (paper defaults): verify η at t = 4000 matches paper
- t = 1: verify finite, equals d_model^(-0.5) · 1 · W^(-1.5)
- t = W: verify both branches yield d_model^(-0.5) · W^(-0.5)
- t = 1e6: verify monotone decay, no overflow
- d_model = 1, warmup = 1 degenerate case: verify finite output
