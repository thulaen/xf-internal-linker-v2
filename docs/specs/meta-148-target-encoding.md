# META-148 — Target Encoding

## Overview
**Category:** Feature engineering (categorical encoder)
**Extension file:** `target_encoding.cpp`
**Replaces/improves:** One-hot encoding for high-cardinality categoricals where category-mean of target is predictive
**Expected speedup:** ≥4x over category_encoders `TargetEncoder`
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

```
Input: categorical column c ∈ {0,...,C-1}^N, target y ∈ ℝ^N, smoothing m ≥ 0
Output: encoded vector e ∈ ℝ^N

Rule (Micci-Barreca, SIGKDD Explorations 2001):
    ȳ = mean(y)                                (global target mean)
    n_c = count of rows where c_i = c
    ȳ_c = mean(y_i | c_i = c)
    E[y | c] = (n_c · ȳ_c + m · ȳ) / (n_c + m)    (Bayesian smoothed mean)
    e_i = E[y | c = c_i]
```

- **Time complexity:** O(N) fit + O(N) transform
- **Space complexity:** O(C) for encoding table
- **Convergence:** Bayesian credible-mean estimate; m controls shrinkage

## C++ Interface (pybind11)

```cpp
// Fit: returns per-category smoothed mean table
void target_encode_fit(
    float* encoding_out,   // (C,)
    const int* c, const float* y, int N,
    int C, float smoothing
);

// Transform: maps c to encoding
void target_encode_transform(
    float* e_out,
    const int* c, int N,
    const float* encoding, int C,
    float global_mean
);
```

## Memory Budget
- Runtime RAM: <20 MB (category table + per-row output)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: category_encoders `TargetEncoder`
- Target: ≥4x faster via single-pass counters
- Benchmark: N=1_000_000, C ∈ {10, 1000, 100_000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Category id ∈ [0, C).

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Unknown categories in transform: fall back to global_mean.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_148.py` | Matches category_encoders TargetEncoder within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than category_encoders |
| 5 | `pytest test_edges_meta_148.py` | singleton category, empty category, m=0, m→∞ all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained)

## Pipeline Stage Non-Conflict
- **Owns:** Bayesian-smoothed per-category target mean encoding
- **Alternative to:** META-147 (hashing), META-149 (count), META-150 (LOO target) — mutually exclusive per categorical column
- **Coexists with:** META-143..146 numerical encoders; optimizers META-128..135

## Test Plan
- m=0: encoding equals raw ȳ_c exactly for non-empty categories
- m→∞: encoding → ȳ uniformly
- Singleton category: encoding is a weighted blend of single y and ȳ
- Unknown category in transform: returns global_mean
