# META-150 — Leave-One-Out Target Encoding

## Overview
**Category:** Feature engineering (categorical encoder)
**Extension file:** `loo_target_encoding.cpp`
**Replaces/improves:** Plain target encoding (META-148) where in-sample leakage harms validation fidelity
**Expected speedup:** ≥4x over category_encoders `LeaveOneOutEncoder`
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

```
Input: c ∈ {0,...,C-1}^N, y ∈ ℝ^N
Output: encoded e ∈ ℝ^N (no leakage)

Rule (Micci-Barreca 2001 LOO variant):
    for each row i with category c_i = c:
        n_c = Σ_j 1{c_j = c}
        if n_c > 1:
            E[y | c]_i = (Σ_{j : c_j = c, j ≠ i} y_j) / (n_c − 1)
        else:
            E[y | c]_i = ȳ                        (global mean fallback)
    e_i = E[y | c]_i

Efficient computation: precompute per-category sum S_c and count n_c, then
    e_i = (S_{c_i} − y_i) / (n_{c_i} − 1)       (or ȳ when n_{c_i} = 1)
```

- **Time complexity:** O(N) two-pass
- **Space complexity:** O(C) for sum and count tables
- **Convergence:** Unbiased leave-one-out target mean; prevents train leakage

## C++ Interface (pybind11)

```cpp
// Fit aggregates: per-category sum and count
void loo_target_encode_fit(
    double* sum_out, int64_t* count_out,
    const int* c, const float* y, int N, int C
);

// Transform with LOO correction
void loo_target_encode_transform(
    float* e_out,
    const int* c, const float* y, int N,
    const double* sums, const int64_t* counts, int C,
    float global_mean
);
```

## Memory Budget
- Runtime RAM: <20 MB (sums + counts + output)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: category_encoders `LeaveOneOutEncoder`
- Target: ≥4x faster via single-pass aggregate + LOO correction
- Benchmark: N=1_000_000, C ∈ {10, 1000, 100_000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Use double for per-category sum.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Singleton category falls back to global_mean — documented.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_150.py` | Matches category_encoders LeaveOneOutEncoder within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than category_encoders |
| 5 | `pytest test_edges_meta_150.py` | singleton category, all-same-target, NaN y, C=1 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained)

## Pipeline Stage Non-Conflict
- **Owns:** Leave-one-out target-mean encoding
- **Alternative to:** META-147 (hashing), META-148 (target), META-149 (count) — mutually exclusive per categorical column
- **Coexists with:** META-143..146 numerical encoders; optimizers META-128..135

## Test Plan
- Singleton category: e_i = global_mean exactly
- All-same-target within category: e_i = that constant
- Sum-minus-self invariant: (S_c − y_i)/(n_c − 1) matches naive O(N²) reference within 1e-5
- No leakage: verify e_i never depends on y_i
