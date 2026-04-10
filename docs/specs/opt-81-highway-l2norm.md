# OPT-81 -- Highway SIMD for l2norm

## Overview
**Category:** Google library -- SIMD
**Extension file:** `l2norm.cpp` (modify existing)
**Expected speedup:** >=3x batch normalization throughput over auto-vectorization
**RAM:** 0 additional | **Disk:** ~3 MB shared Highway install
**Research basis:** Wassenberg J. & Alakuijala J., "Highway -- a portable SIMD library", Google Research 2023.

## Algorithm

Replace the row-wise L2 normalization loop in normalize_l2_batch() with Highway SIMD. Current code: sequential sum-of-squares, then divide. Highway: `hn::Mul` for element-wise square, `hn::Add` accumulator, `hn::ReduceSum` for norm, `hn::Div` for normalization -- all at full SIMD width. Handles tail elements via Highway's automatic masking.

## C++ Interface (pybind11)

```cpp
// No API change:
// normalize_l2(input) and normalize_l2_batch(input) signatures unchanged.
// HWY_DYNAMIC_DISPATCH for runtime ISA selection.
```

## Memory Budget
- Runtime RAM: 0 additional (in-place normalization)
- Disk: ~3 MB shared

## Performance Target
- Target: >=3x faster batch normalization
- Benchmark: 10K vectors x 1024D, batch normalization

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
- Highway (shared with OPT-80, 82)
- Note: l2norm currently uses std::execution::par on Windows -- Highway replaces the inner loop, TBB/par handles row-level parallelism

## Test Plan
- Correctness: normalized vectors have L2 norm == 1.0 within 1e-6
- Edge cases: zero vector (should remain zero), single element, NaN input
