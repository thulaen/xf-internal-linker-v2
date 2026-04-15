# META-91 — Cosine Annealing with Warm Restarts (SGDR)

## Overview
**Category:** Learning-rate scheduler (P10 LR schedulers block)
**Extension file:** `cosine_annealing_lr.cpp`
**Replaces/improves:** Constant or stepped LR in weight-tuning epochs; smoother LR decay improves NDCG plateau and enables snapshot ensembling (META-98)
**Expected speedup:** N/A — accuracy/convergence improvement; CPU work is negligible
**RAM:** <1 KB | **Disk:** <1 MB

## Algorithm

```
Input: η_max, η_min, initial cycle length T_0, multiplier T_mult ≥ 1
State: cycle index i, intra-cycle step T_cur, current cycle length T_i

Per-step update (paper Eq. 5):
  η_t = η_min + (1/2)·(η_max − η_min)·(1 + cos(π · T_cur / T_i))

Warm restart trigger (when T_cur >= T_i):
  T_cur ← 0
  T_i   ← T_i · T_mult        (geometric cycle growth; T_mult = 1 for fixed length)
  i     ← i + 1
  (η jumps back to η_max — the "warm restart")
```

- **Time complexity:** O(1) per step
- **Space complexity:** O(1) — three scalars
- **Convergence:** Empirically faster + better minima than constant LR; restarts let optimiser escape sharp local minima

## Academic source
Loshchilov, I. and Hutter, F., "SGDR: Stochastic Gradient Descent with Warm Restarts", *International Conference on Learning Representations (ICLR)*, 2017.

## C++ Interface (pybind11)

```cpp
class CosineAnnealingWR {
public:
    CosineAnnealingWR(float eta_max, float eta_min, int T_0, float T_mult);
    float step();              // returns η for the current step, advances state
    void  reset();
    int   cycle_index() const; // useful for snapshot-ensemble triggering
    int   T_cur() const;
    int   T_i() const;
};
```

## Memory Budget
- Runtime RAM: <1 KB (single tiny stateful object)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: zero per-step

## Performance Target
- Python baseline: `torch.optim.lr_scheduler.CosineAnnealingWarmRestarts`
- Target: parity within 1e-6, not a speedup target
- Benchmark: 3 sizes — 100, 10000, 1000000 sequential `step()` calls; verify O(1) per call

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Scheduler is single-thread; users wrap externally if shared.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate T_0 ≥ 1 and T_mult ≥ 1 and η_max ≥ η_min ≥ 0.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Scalar `cos` call — no vectorisation needed at 1 element/step.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. `cos` computed in `double` then narrowed to `float` to avoid drift over very long schedules.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_91.py` | Per-step LR matches PyTorch reference within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_cosine.py` | <100 ns per `step()` call on 3 sizes |
| 5 | `pytest test_edges_meta_91.py` | T_0=1, T_mult=1 (fixed cycles), T_mult=2 (geometric), η_min=η_max all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Drift check | After 1M steps, computed η matches ground truth within 1e-5 |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps

## Pipeline stage non-conflict declaration
- **Owns:** Cosine LR schedule with warm-restart trigger
- **Alternative to:** META-92 1-cycle, META-93 transformer warmup, META-94 polynomial decay, META-95 step decay
- **Coexists with:** META-96 SWA (consumes restart cycle index), META-98 snapshot ensemble (triggers on cycle min); LR scheduler is orthogonal to all P8 regularisers and P9 calibrators

## Test Plan
- η_max=1, η_min=0, T_0=10, T_mult=1: verify η at step 5 = 0.5 (cosine midpoint)
- T_mult=2: verify cycle lengths 10, 20, 40, 80, …
- η_max = η_min: verify constant LR for all steps
- After warm restart: verify η jumps back exactly to η_max
- Cycle index increments correctly at boundary
