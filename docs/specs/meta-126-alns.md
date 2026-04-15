# META-126 — Adaptive Large Neighborhood Search (ALNS)

## Overview
**Category:** Metaheuristic destroy-repair with adaptive operator weights
**Extension file:** `alns.cpp`
**Replaces/improves:** Large Neighborhood Search (LNS) with hand-tuned operator weights
**Expected speedup:** ≥6x over Python reference loop
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

```
Input: destroy ops D = {d_j}, repair ops R = {r_k}, initial x, n_iters, segment_size
Output: best x*

x ← x_0;  x_best ← x_0
weights_d ← 1/|D|;  weights_r ← 1/|R|
scores_d ← 0;  scores_r ← 0
for iter = 1..n_iters:
    # destroy Q elements, repair greedily; adaptive weights per operator based on success rate
    d_j ← sample_weighted(weights_d)
    r_k ← sample_weighted(weights_r)
    Q ← sample_destroy_size()
    x_destroyed ← d_j(x, Q)
    x_new ← r_k(x_destroyed)
    # simulated-annealing acceptance
    if accept(x_new, x, T):
        x ← x_new
    update scores based on (new best, improved, accepted)
    if iter % segment_size == 0:
        weights ← (1-ρ) · weights + ρ · scores / usage
        scores ← 0; usage ← 0
    if cost(x) < cost(x_best): x_best ← x
return x_best
```

- **Time complexity:** O(n_iters × (destroy + repair))
- **Space complexity:** O(|solution|)
- **Convergence:** Heuristic; adaptive weights concentrate on effective operator pairs

## Academic Source
Ropke S., Pisinger D. "An Adaptive Large Neighborhood Search Heuristic for the Pickup and Delivery Problem with Time Windows." *Transportation Science* 40(4):455–472, 2006. DOI: 10.1287/trsc.1050.0135.

## C++ Interface (pybind11)

```cpp
// ALNS with weighted operator selection and SA acceptance
std::vector<int> alns(
    const int* initial_x, int n_items,
    std::function<float(const int*)> cost_fn,
    std::vector<std::function<void(int*, int, int, uint64_t)>> destroy_ops,
    std::vector<std::function<void(int*, int, uint64_t)>> repair_ops,
    int destroy_q, int n_iters, int segment_size,
    float reaction_rho, float initial_temp, float cooling,
    uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <20 MB (solution + operator stats)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve`

## Performance Target
- Python baseline: `alns` Python package
- Target: ≥6x faster
- Benchmark: n_iters ∈ {5k, 25k, 100k} × n_items ∈ {100, 500, 2000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on solution buffer.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on cost. Clamp operator weights to [1e-6, ∞) to keep probabilities positive.

**Performance:** No `std::endl` loops. No `std::function` hot loops (operators may be stored as function pointers). No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. Empty operator lists raise.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_126.py` | Best cost within 3% of Python `alns` reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than Python reference |
| 5 | `pytest test_edges_meta_126.py` | 1 op each, destroy_q=n, cooling=1 handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Caller supplies destroy and repair operator lists

## Pipeline Stage Non-Conflict
**Owns:** Adaptive destroy-repair search for large combinatorial instances.
**Alternative to:** META-123 tabu, META-125 VNS when solutions are partial-rebuildable.
**Coexists with:** META-125 VNS — VNS picks neighborhood structure, ALNS picks operator weights.

## Test Plan
- Small VRP (n=30): within 3% of optimum
- Weights converge: operator usage stats track scores
- Single operator pair: degenerates to classic LNS
- NaN cost: verify raises ValueError
