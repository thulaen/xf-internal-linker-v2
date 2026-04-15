# META-149 — Count Encoding

## Overview
**Category:** Feature engineering (categorical encoder)
**Extension file:** `count_encoding.cpp`
**Replaces/improves:** Plain integer or one-hot encoding when category frequency itself is informative
**Expected speedup:** ≥5x over category_encoders `CountEncoder`
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

```
Input: categorical column c ∈ {0,...,C-1}^N
Output: encoded vector e ∈ ℕ^N

Rule (Pargent, Bischl, Thomas, NeurIPS 2021):
    n_c = Σ_i 1{c_i = c}               (count per category)
    e_i = n_{c_i}                      (replace each row with count of its category)

Optional variants:
    log-count:      e_i = log(1 + n_{c_i})
    normalised:     e_i = n_{c_i} / N
```

- **Time complexity:** O(N) two-pass (or single-pass with hash map for unseen fit time)
- **Space complexity:** O(C) count table
- **Convergence:** Deterministic; preserves frequency ordering

## C++ Interface (pybind11)

```cpp
// Fit: build count table
void count_encode_fit(
    int64_t* counts_out,  // (C,)
    const int* c, int N, int C
);

// Transform
void count_encode_transform(
    float* e_out,
    const int* c, int N,
    const int64_t* counts, int C,
    bool log_transform, bool normalise, int64_t total_n
);
```

## Memory Budget
- Runtime RAM: <10 MB (counts + output)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: category_encoders `CountEncoder`
- Target: ≥5x faster via single-pass histogram
- Benchmark: N=1_000_000, C ∈ {10, 1000, 100_000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Use int64 counts to avoid overflow on N>2³¹.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. log(1 + n) preferred over log(n) to allow zero-count handling.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_149.py` | Matches category_encoders CountEncoder exactly |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than category_encoders |
| 5 | `pytest test_edges_meta_149.py` | empty input, single category, C=1, overflow guard all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained)

## Pipeline Stage Non-Conflict
- **Owns:** Category-frequency replacement
- **Alternative to:** META-147 (hashing), META-148 (target), META-150 (LOO target) — mutually exclusive per categorical column
- **Coexists with:** META-143..146 numerical encoders; optimizers META-128..135

## Test Plan
- Count sum invariant: Σ_c counts[c] = N
- log_transform: verify e_i = log(1 + n_{c_i})
- normalise: verify Σ output / N is constant
- C=1: encoding = N for every row
