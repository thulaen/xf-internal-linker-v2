# OPT-78 -- Abseil Mutex

## Overview
**Category:** Google library -- mutex
**Extension file:** `strpool.cpp`, `pulse_metrics.cpp` (modify existing)
**Expected speedup:** >=3x lock/unlock throughput over `std::mutex`
**RAM:** Same | **Disk:** ~5 MB shared Abseil install
**Research basis:** Abseil documentation. absl::Mutex provides adaptive spinning, thread annotations, and deadlock detection in debug builds. No overhead in release builds.

## Algorithm

Drop-in replace `std::mutex` + `std::lock_guard` with `absl::Mutex` + `absl::MutexLock`. Abseil Mutex uses adaptive spinning (spin briefly before kernel sleep) which avoids syscall overhead for short critical sections -- exactly the pattern in strpool.intern() and pulse_metrics.push().

## C++ Interface (pybind11)

```cpp
// No API change -- internal type swap:
// absl::Mutex mu_;  // replaces std::mutex mu_;
// absl::MutexLock lock(&mu_);  // replaces std::lock_guard<std::mutex> lock(mu_);
```

## Memory Budget
- Runtime RAM: Same as std::mutex (~40 bytes per mutex)
- Disk: ~5 MB shared

## Performance Target
- Target: >=3x faster lock/unlock under contention
- Benchmark: 8 threads, 1M lock cycles each, measure total throughput

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
- Abseil C++ (shared with OPT-73-77, 79)

## Test Plan
- Correctness: strpool intern/get and pulse_metrics push/summary produce identical output
- Thread safety: TSAN with 8 concurrent threads must pass
- Deadlock detection: debug build with ABSL_MUTEX_DEADLOCK_DETECTION enabled
