# META-60 — NSGA-II Multi-Objective Selector

## Overview
**Category:** Multi-objective evolutionary optimizer (Pareto-rank + crowding)
**Extension file:** `nsga_ii.cpp`
**Replaces/improves:** Single-objective META-04 / META-08 when ranking weight-tuning must trade off two or more objectives (e.g. NDCG vs latency vs diversity)
**Expected speedup:** ≥6x over `pymoo.algorithms.moo.nsga2.NSGA2`
**RAM:** <30 MB | **Disk:** <1 MB

## Algorithm
```
Input: population P of size N, M objective functions f_1..f_M, mutation σ, crossover p_c
Output: non-dominated front F_1 of size ≤ N

initialise P_0 randomly; evaluate f(x) for x ∈ P_0
for t = 0..max_gen:
    Q_t = make_offspring(P_t, p_c, σ)            # SBX crossover + polynomial mutation
    R_t = P_t ∪ Q_t                              # |R_t| = 2N
    (F_1, F_2, ...) = fast_non_dominated_sort(R_t)   # Deb 2002 §III.A
    P_{t+1} = ∅
    i = 1
    while |P_{t+1}| + |F_i| ≤ N:
        crowding_distance_assignment(F_i)        # Deb 2002 §III.B
        P_{t+1} ← P_{t+1} ∪ F_i
        i = i + 1
    sort F_i by (rank_asc, crowding_desc)        # crowded-comparison operator ≺_n
    P_{t+1} ← P_{t+1} ∪ first (N − |P_{t+1}|) of F_i
return F_1 of P_max_gen
```
- Time complexity: O(max_gen · M · N²) dominated by non-dominated sort
- Space complexity: O(M · N) for objective matrix + O(N²) for domination flags
- Convergence: empirically Pareto-front-converging; no closed-form proof (Deb 2002 §IV)

## Academic source
**Deb, K., Pratap, A., Agarwal, S., Meyarivan, T. (2002).** "A fast and elitist multiobjective genetic algorithm: NSGA-II." *IEEE Transactions on Evolutionary Computation* 6(2):182-197. DOI: `10.1109/4235.996017`.

## C++ Interface (pybind11)
```cpp
// NSGA-II returns the final non-dominated front (rows = solutions, cols = d weights)
py::array_t<float> nsga_ii(
    const float* init_pop, int N, int d,
    std::function<void(const float*, float*)> eval_objectives,   // writes M floats
    int M, int max_gen, float p_crossover, float p_mutation, uint64_t seed
);
```

## Memory budget
- Runtime RAM: <30 MB (N ≤ 200, d ≤ 100, M ≤ 5)
- Disk: <1 MB
- Allocation: arena for combined R_t (2N rows), `reserve(2*N*d)`; aligned 64-byte for objective matrix

## Performance target
- Python baseline: `pymoo.algorithms.moo.nsga2.NSGA2`
- Target: ≥6x faster (avoids per-individual Python callbacks)
- Benchmark: N ∈ {50, 100, 200} × d ∈ {10, 50} × M ∈ {2, 3} × 100 generations

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — flags `-Wall` through `-Werror -Wsign-conversion -Wshadow`, no raw `new`/`delete` in hot paths, no `std::recursive_mutex`, RNG seeded once and stored in static thread-local, NaN/Inf checks on every objective return, double accumulator for crowding-distance sums, `noexcept` destructors, no `std::function` inside the per-individual evaluation loop (cache function pointer once), arena allocator for R_t to avoid per-generation `new`, SIMD comparison loops use `_mm256_zeroupper()`.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_60.py` | Final front matches pymoo NSGA-II within hypervolume diff < 1% |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than Python |
| 5 | Edge cases | M=1 (degenerates to GA), N=2, NaN objective, max_gen=0 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-08 Differential evolution mutation primitive (re-used for polynomial mutation)
- Mersenne Twister RNG (std::mt19937_64)

## Pipeline stage (non-conflict)
**Owns:** multi-objective Pareto selector slot (2 ≤ M ≤ 5 objectives)
**Alternative to:** META-61 NSGA-III (better for M ≥ 4), META-62 MOEA/D (decomposition-based)
**Coexists with:** META-04 coordinate ascent (single-objective), META-39 query-cluster router (per-cluster MO tuning)

## Test plan
- ZDT1 benchmark (M=2, d=30): final front IGD ≤ 0.005 vs analytical Pareto front
- Single objective (M=1): degenerates to vanilla GA, matches META-08 within 1%
- N=2, max_gen=10: returns at most 2 non-dominated solutions
- NaN in objective: raises `ValueError`
- Conflicting objectives (f_1 = x, f_2 = −x): final front spans entire decision range
