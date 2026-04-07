# META-12-BOX-COX-TRANSFORM — Box-Cox Transformer

## Overview
**Category:** Score normalizer
**Extension file:** `boxcox_tf.cpp`
**Replaces/improves:** scipy.stats.boxcox
**Expected speedup:** ≥3x over scipy
**RAM:** <1 MB | **Disk:** <1 MB

## Algorithm

y(s;λ) = (s^λ - 1)/λ if λ≠0, else log(s). Learn λ per signal by maximising Shapiro-Wilk normality statistic. O(n log n) for SW test.

## C++ Interface (pybind11)

```cpp
float boxcox_fit_lambda(const float* scores, int n); void boxcox_transform(const float* scores, int n, float lambda, float* out);
```

## Memory Budget
- Runtime RAM: <1 MB
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: std::vector with reserve() or arena

## Performance Target
- Target: ≥3x over scipy
- Benchmark: 1000 iterations on production-size input

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_*.py` | Output matches Python reference within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than Python reference |
| 5 | `pytest test_edges_*.py` | Empty, single, NaN/Inf, n=10000 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None

## Test Plan
- λ=1: identity (y=s-1)
- λ=0: log transform
- Negative input: raises ValueError
