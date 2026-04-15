# META-62 — MOEA/D Decomposition Optimizer

## Overview
**Category:** Multi-objective optimizer (decomposition into N scalar subproblems)
**Extension file:** `moea_d.cpp`
**Replaces/improves:** META-60 NSGA-II / META-61 NSGA-III when objectives are smoothly tradeable and a fixed weight grid is acceptable; benefits from neighbourhood reuse
**Expected speedup:** ≥4x over `pymoo.algorithms.moo.moead.MOEAD`
**RAM:** <25 MB | **Disk:** <1 MB

## Algorithm
```
Input: N weight vectors λ_1..λ_N (uniform on simplex), neighbourhood size T,
       M objectives, scalarisation g(x | λ, z*) ∈ {Tchebycheff, weighted-sum}
Output: N solutions, one per scalar subproblem; their union approximates the front

generate λ via Das-Dennis; build neighbour list B_i = T closest λ_j to λ_i  (Zhang & Li 2007 §III.A)
initialise P = {x_1, ..., x_N}; evaluate F_i = f(x_i); set z*_m = min_i f_m(x_i)
for t = 0..max_gen:
    for i = 1..N (random order):
        choose two parents x_k, x_l with k,l ∈ B_i uniformly
        y = crossover_then_mutate(x_k, x_l)
        update z*: z*_m ← min(z*_m, f_m(y)) for m=1..M
        for j ∈ B_i:
            if g(y | λ_j, z*) ≤ g(x_j | λ_j, z*): x_j ← y; F_j ← f(y)    # neighbour replacement
return non-dominated subset of {x_1..x_N}
```
- Time complexity: O(max_gen · N · T · M)
- Space complexity: O(N · M) for objectives + O(N · T) for neighbourhood lists
- Convergence: each subproblem g(· | λ_i) is scalar — local convergence per subproblem (Zhang & Li 2007 Thm 1)

## Academic source
**Zhang, Q., Li, H. (2007).** "MOEA/D: A multiobjective evolutionary algorithm based on decomposition." *IEEE Transactions on Evolutionary Computation* 11(6):712-731. DOI: `10.1109/TEVC.2007.892759`.

## C++ Interface (pybind11)
```cpp
py::array_t<float> moea_d(
    const float* init_pop, int N, int d,
    std::function<void(const float*, float*)> eval_objectives,
    int M, int T_neighbours, int max_gen,
    int scalarisation,           // 0 = Tchebycheff, 1 = weighted-sum, 2 = PBI
    float p_crossover, float p_mutation, uint64_t seed
);
```

## Memory budget
- Runtime RAM: <25 MB (N ≤ 300, d ≤ 100, M ≤ 5, T ≤ 20)
- Disk: <1 MB
- Allocation: aligned 64-byte for λ matrix and objective matrix; arena for offspring

## Performance target
- Python baseline: `pymoo.algorithms.moo.moead.MOEAD`
- Target: ≥4x faster
- Benchmark: N=100 × d=30 × M ∈ {2, 3} × 200 generations

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in inner loops, RNG seeded once, NaN/Inf checks on objectives, double accumulator for Tchebycheff max-reduction, `noexcept` destructors, SIMD scalarisation kernel uses `_mm256_zeroupper()`, no `std::function` in per-individual loop, neighbourhood lists pre-computed once and stored as `std::vector<int>` per i (no per-generation allocation).

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_62.py` | Hypervolume diff vs pymoo MOEA/D < 2% |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥4x faster than Python |
| 5 | Edge cases | T=1, T=N, M=1, NaN objective pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-64 Tchebycheff scalarisation (default scalarisation function)
- META-08 differential-evolution mutation primitive
- Das-Dennis simplex generator (shared with META-61)

## Pipeline stage (non-conflict)
**Owns:** decomposition-based MO optimizer slot
**Alternative to:** META-60 NSGA-II (Pareto-rank), META-61 NSGA-III (reference-point)
**Coexists with:** META-63 ε-constraint method (alternative scalarisation), META-04 coordinate ascent

## Test plan
- ZDT1 (M=2, d=30): IGD ≤ 0.01
- DTLZ2 (M=3, d=12): IGD ≤ 0.05
- T=1 (no neighbour reuse): degenerates to N independent optimisations, no crash
- M=1: matches META-08 differential evolution within 1%
- NaN in objective: raises `ValueError`
