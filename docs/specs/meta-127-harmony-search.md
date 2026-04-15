# META-127 — Harmony Search

## Overview
**Category:** Music-inspired metaheuristic (memory-based continuous search)
**Extension file:** `harmony_search.cpp`
**Replaces/improves:** GA for low-dimensional continuous problems with simple memory update
**Expected speedup:** ≥6x over Python reference loop
**RAM:** <15 MB | **Disk:** <1 MB

## Algorithm

```
Input: d dimensions, HMS harmony memory size, HMCR ∈ [0,1], PAR ∈ [0,1], bandwidth bw
Output: best harmony (solution)

# maintain HM harmony memory; new harmony: for each dimension,
#   with prob HMCR pick from HM (then with prob PAR perturb by bandwidth),
#   else random
initialize HM = {h_1, ..., h_HMS} uniformly in bounds
for iter = 1..n_iters:
    h_new ← empty
    for i = 1..d:
        if U(0,1) < HMCR:
            h_new[i] ← HM[random_row][i]
            if U(0,1) < PAR:
                h_new[i] ← h_new[i] + U(-1,1) · bw
        else:
            h_new[i] ← uniform(lower[i], upper[i])
    if cost(h_new) < cost(worst in HM):
        replace worst in HM with h_new
return best in HM
```

- **Time complexity:** O(n_iters × d × cost_eval)
- **Space complexity:** O(HMS × d)
- **Convergence:** No monotonic guarantee; HMCR controls memory usage, PAR controls local adjustment

## Academic Source
Geem Z.W., Kim J.H., Loganathan G.V. "A New Heuristic Optimization Algorithm: Harmony Search." *Simulation* 76(2):60–68, 2001. DOI: 10.1177/003754970107600201.

## C++ Interface (pybind11)

```cpp
// Harmony search for continuous box-constrained problems
std::vector<float> harmony_search(
    int d, const float* lower_bounds, const float* upper_bounds,
    std::function<float(const float*)> cost_fn,
    int hms, float hmcr, float par, const float* bandwidth,
    int n_iters, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <15 MB (HMS=50 × d=200 × 4 bytes + overhead)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(HMS * d)`; HM stored `alignas(64)` flat

## Performance Target
- Python baseline: pyHarmonySearch
- Target: ≥6x faster
- Benchmark: n_iters=10k × HMS ∈ {20, 50, 100} × d ∈ {10, 50, 200}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on HM buffer.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on cost. Clamp new harmony to bounds.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. HMCR/PAR outside [0,1] raise.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_127.py` | Best cost within 5% of Python reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than Python reference |
| 5 | `pytest test_edges_meta_127.py` | HMCR=0, HMCR=1, d=1, HMS=1 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone)

## Pipeline Stage Non-Conflict
**Owns:** Memory-based continuous metaheuristic search.
**Alternative to:** META-120 GA, META-121 ES for low-dim continuous problems.
**Coexists with:** META-123..126 combinatorial metaheuristics — selected via `optimizer.metaheuristic`.

## Test Plan
- Sphere d=10: converges to f < 1e-3 within 5k iters
- Rastrigin d=10: best f < 5 within 20k iters
- HMS=1: reduces to local random-walk
- NaN cost / bounds violation: verify raises ValueError
