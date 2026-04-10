# OPT-80 -- Highway SIMD for simsearch

## Overview
**Category:** Google library -- SIMD
**Extension file:** `simsearch.cpp` (modify existing)
**Expected speedup:** >=3x dot-product throughput over auto-vectorization
**RAM:** 0 additional | **Disk:** ~3 MB shared Highway install
**Research basis:** Wassenberg J. & Alakuijala J., "Highway -- a portable SIMD library", Google Research 2023. Highway provides explicit SIMD with compile-time dispatch to best available instruction set (SSE4, AVX2, AVX-512, NEON).

## Algorithm

Replace the raw dot-product loop in score_and_topk() with Highway HWY_NAMESPACE vector operations. Current code relies on `-march=native` auto-vectorization which misses opportunities (loop-carried dependencies, alignment). Highway's `hn::Mul` + `hn::Add` with explicit accumulator vectors guarantee full SIMD width utilization. Final horizontal sum via `hn::ReduceSum`.

## C++ Interface (pybind11)

```cpp
// No API change -- internal loop replacement:
// score_and_topk() and cscore_and_topk() signatures unchanged.
// HWY_DYNAMIC_DISPATCH selects best SIMD at runtime.
```

## Memory Budget
- Runtime RAM: 0 additional (operates on existing numpy arrays)
- Disk: ~3 MB shared across OPT-80, 81, 82

## Performance Target
- Target: >=3x faster dot products
- Benchmark: 10K candidate embeddings x 1024D, top-50, 100 iterations

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Predicate-form `condition_variable::wait()`. Document atomic ordering. `_mm_pause()` spinlocks with 1000-iter fallback.

**Memory:** No raw `new`/`delete` hot paths. No `alloca`/VLA. No `void*` delete. RAII only. Debug bounds checks. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` beyond scope. No return ref to local.

**Type safety:** `static_cast` for narrowing. No signed/unsigned mismatch. No aliasing violation. All switch handled.

**SIMD:** No SSE/AVX mix without `zeroupper`. Unaligned loads. Max 12 YMM. `alignas(64)` hot arrays.

**Floating point:** Flush-to-zero init. NaN/Inf entry checks. Double accumulator >100 elements.

**Performance:** No `std::endl` loops. No `std::function` hot. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** `noexcept` destructors. `const&` catch. Basic guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_str)`. Scrub memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings `-Werror` |
| 2 | `pytest test_parity_*.py` | Matches Python ref within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero ASAN/UBSan errors |
| 4 | `bench_extensions.py` | >=3x faster than Python |
| 5 | `pytest test_edges_*.py` | Empty, single, NaN/Inf, n=10000 pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md confirmed |

## Dependencies
- Highway (google/highway, Apache 2.0) -- shared with OPT-81, 82
- Compiles on MSVC (AVX2) and GCC/Clang (-march=native)

## Test Plan
- Correctness: top-K indices and scores match current implementation within 1e-4
- Edge cases: n=0 candidates, n=1, dimension mismatch, NaN embeddings
- Platform: verify on both Windows (MSVC) and Linux (GCC)
