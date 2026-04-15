# META-242 — Generalisation-Loss (GL) Early Stopping

## Overview
**Category:** Training / validation control
**Extension file:** `gl_early_stopping.cpp`
**Replaces/improves:** Fixed epoch budgets or ad-hoc patience stopping in training loops
**Expected speedup:** Not a speed target — reduces wasted epochs by detecting overfitting early
**RAM:** <1 MB | **Disk:** <1 MB

## Algorithm

```
Input: validation loss stream E_va(1), E_va(2), ..., threshold α, patience p
Output: boolean stop flag and reason

Track running minimum (paper, eq. 2):
  E_opt(t) = min_{1 ≤ s ≤ t} E_va(s)

Generalisation loss (paper, eq. 3):
  GL(t) = 100 · (E_va(t) / E_opt(t) − 1)

Primary stop rule GL_α (paper, Section 2):
  if GL(t) > α:  stop

Optional secondary stop (paper, Section 2 — patience criterion):
  P_k(t) = 1000 · ( E_train_mean_k(t) / min_k_window(E_train(t)) − 1 )
  if E_va did not decrease for p consecutive epochs: stop

Combined quotient rule (paper, eq. 5):
  PQ_α: stop if GL(t) / P_k(t) > α

Return also: best_epoch = argmin E_va (restore checkpoint).
```

- **Time complexity:** O(1) per epoch
- **Space complexity:** O(1) (running min and patience counter)

## Academic Source
Prechelt, L. "Automatic early stopping using cross validation: quantifying the criteria." Neural Networks 11, no. 4 (1998), pp. 761–767. DOI: 10.1016/S0893-6080(98)00010-0

## C++ Interface (pybind11)

```cpp
// Stateful early-stopping controller
struct GLEarlyStopper {
    float alpha;           // GL threshold (%)
    int   patience;        // epochs without improvement
    float best_va;         // E_opt so far
    int   best_epoch;
    int   non_improving;
};
GLEarlyStopper gl_make(float alpha, int patience);
bool gl_should_stop(GLEarlyStopper& s, int epoch, float e_va, float e_tr);
int  gl_best_epoch(const GLEarlyStopper& s);
```

## Memory Budget
- Runtime RAM: <1 MB (scalar state)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: none in hot path

## Performance Target
- Python baseline: Keras `EarlyStopping` callback
- Target: parity (the hot path is O(1)); primary value is correctness + clear checkpoint semantics
- Benchmark: 10k, 100k, 1M epoch ticks

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** Not thread safe by default — caller must hold a mutex if shared across workers.

**Memory:** No raw `new`/`delete`. No heap allocation in hot path.

**Object lifetime:** Self-assignment safe. Controller is POD-like.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** Not applicable.

**Floating point:** Flush-to-zero on init. NaN in E_va treated as +∞ (never becomes best). E_opt divisor clamped to `max(·, 1e-12)`.

**Performance:** No `std::endl` loops. No `std::function` hot loops.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Illegal α or patience raises.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_242.py` | Stop decisions match Keras EarlyStopping baseline on synthetic curves |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | Overhead <1 µs per call |
| 5 | `pytest test_edges_meta_242.py` | NaN E_va, flat curve, monotonic improvement all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if caller serialises access) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Standalone — plugs into any training loop
- Co-exists with META-243 (PBT uses early stopping for exploit step)

## Pipeline Stage Non-Conflict
- **Owns:** stopping decision and best-epoch tracking
- **Alternative to:** fixed epoch budgets
- **Coexists with:** META-38 successive-halving (ASHA), META-243 PBT

## Test Plan
- Monotone decreasing E_va: verify never stops (except on patience if enabled)
- U-shaped curve (decrease then increase): verify stops after GL exceeds α
- E_va all NaN: verify does not crash and eventually stops
- α = 0: verify stops on first non-improvement
