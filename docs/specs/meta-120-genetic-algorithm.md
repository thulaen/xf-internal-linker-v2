# META-120 — Genetic Algorithm (GA)

## Overview
**Category:** Evolutionary weight optimizer (population-based)
**Extension file:** `genetic_algorithm.cpp`
**Replaces/improves:** Gradient-free global search when ELBO/NDCG landscape is rugged
**Expected speedup:** ≥8x over Python `deap` GA loop
**RAM:** <30 MB | **Disk:** <1 MB

## Algorithm

```
Input: population size P, dimensionality d, fitness f, crossover p_c, mutation p_m
Output: best individual w*

initialize population {w_i}_{i=1..P} ~ q_0
for gen = 1..G:
    # selection → crossover (uniform or single-point) → mutation (bit-flip with p_m); replace generation
    parents ← tournament_select(population, f)
    offspring ← []
    for (a, b) in pairs(parents):
        if U(0,1) < p_c:
            (a', b') ← crossover(a, b)              # uniform or single-point
        else:
            (a', b') ← (a, b)
        a' ← mutate(a', p_m);  b' ← mutate(b', p_m)  # bit-flip or Gaussian perturb
        offspring += [a', b']
    population ← offspring
    track best
return best
```

- **Time complexity:** O(G × P × (select + crossover + mutate + f_eval))
- **Space complexity:** O(P × d)
- **Convergence:** No monotonic guarantee; elitism + finite patience stops when plateau reached

## Academic Source
Holland J.H. *Adaptation in Natural and Artificial Systems: An Introductory Analysis with Applications to Biology, Control, and Artificial Intelligence.* University of Michigan Press, 1975. ISBN: 978-0-472-08460-9.

## C++ Interface (pybind11)

```cpp
// Canonical GA with tournament selection, uniform crossover, per-gene mutation
std::vector<float> genetic_algorithm(
    int pop_size, int d,
    std::function<float(const float*)> fitness,
    float crossover_rate, float mutation_rate, int tournament_k,
    int n_generations, int elitism, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <30 MB (P=500 × d=200 × 2 gens)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: double-buffered population arena `alignas(64)`

## Performance Target
- Python baseline: `deap` toolbox
- Target: ≥8x faster
- Benchmark: P ∈ {100, 500, 2000} × G=200 × d ∈ {10, 50, 200}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Fitness eval may use OpenMP.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills. Population stored as `std::vector<float>` flat array of size P×d.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on population buffer.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on fitness. Double accumulator for fitness averages.

**Performance:** No `std::endl` loops. No `std::function` hot loops (pass template or pointer). No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_120.py` | Best fitness within 3% of deap on Rastrigin |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than deap reference |
| 5 | `pytest test_edges_meta_120.py` | P=2, d=1, constant fitness all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone)

## Pipeline Stage Non-Conflict
**Owns:** Population-based gradient-free global search.
**Alternative to:** META-04 coord ascent (GA handles non-differentiable, multi-modal).
**Coexists with:** META-121 ES, META-123 tabu — selected by `optimizer.family`.

## Test Plan
- Rastrigin d=10: reaches f < 1 within 200 gens
- Sphere: converges to origin within 5%
- Constant fitness: population stays diverse (no premature collapse if elitism=0)
- Fitness NaN: verify raises ValueError
