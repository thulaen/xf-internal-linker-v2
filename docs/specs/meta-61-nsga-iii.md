# META-61 — NSGA-III Many-Objective Selector

## Overview
**Category:** Many-objective evolutionary optimizer (reference-point niching)
**Extension file:** `nsga_iii.cpp`
**Replaces/improves:** META-60 NSGA-II when M ≥ 4 objectives (NSGA-II crowding distance fails to maintain diversity in high-dimensional objective space)
**Expected speedup:** ≥5x over `pymoo.algorithms.moo.nsga3.NSGA3`
**RAM:** <40 MB | **Disk:** <1 MB

## Algorithm
```
Input: population P of size N, M objectives, structured reference points Z (Das & Dennis 1998)
Output: non-dominated front of size ≤ N, evenly spread across reference directions

generate Z = das_dennis(M, p_divisions)              # |Z| = C(M+p−1, p)
initialise P_0; evaluate
for t = 0..max_gen:
    Q_t = make_offspring(P_t, p_c, σ)
    R_t = P_t ∪ Q_t
    (F_1, ...) = fast_non_dominated_sort(R_t)        # same as NSGA-II
    S_t = ∅; i = 1
    while |S_t| + |F_i| ≤ N:
        S_t ← S_t ∪ F_i; i = i + 1
    if |S_t| = N: P_{t+1} = S_t; continue
    # Niching using reference points (Deb & Jain 2014 §IV)
    normalise(S_t ∪ F_i, ideal_point z*, intercepts a)
    associate each x ∈ S_t ∪ F_i with nearest reference line in Z
    ρ_j = niche_count(z_j, S_t)
    while |S_t| < N:
        choose z_j with min ρ_j; pick member of F_i associated with z_j (random if ρ_j=0,
            else closest perpendicular distance); add to S_t; ρ_j += 1
    P_{t+1} = S_t
```
- Time complexity: O(max_gen · M · N² + max_gen · |Z| · N)
- Space complexity: O(M · N) + O(|Z| · M)
- Convergence: empirically maintains diversity along Z; no analytical proof

## Academic source
**Deb, K., Jain, H. (2014).** "An evolutionary many-objective optimization algorithm using reference-point-based nondominated sorting approach, part I: solving problems with box constraints." *IEEE Transactions on Evolutionary Computation* 18(4):577-601. DOI: `10.1109/TEVC.2013.2281535`.

## C++ Interface (pybind11)
```cpp
py::array_t<float> nsga_iii(
    const float* init_pop, int N, int d,
    std::function<void(const float*, float*)> eval_objectives,
    int M, int p_divisions, int max_gen,
    float p_crossover, float p_mutation, uint64_t seed
);
```

## Memory budget
- Runtime RAM: <40 MB (N ≤ 200, d ≤ 100, M ≤ 10, |Z| ≤ 1000)
- Disk: <1 MB
- Allocation: arena for R_t, separate aligned buffer for reference-point matrix

## Performance target
- Python baseline: `pymoo.algorithms.moo.nsga3.NSGA3`
- Target: ≥5x faster
- Benchmark: N=200 × d=50 × M ∈ {3, 5, 10} × 100 generations

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion -Wshadow`, no raw `new`/`delete` in hot paths, NaN/Inf checks on objectives and intercepts (intercept solve can be singular — fallback to nadir), double accumulator for perpendicular-distance sums, RAII RNG, `noexcept` destructors, SIMD distance loops use `_mm256_zeroupper()`, no `std::function` in inner loops, arena allocator for niche-count arrays.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_61.py` | Final front IGD vs pymoo NSGA-III diff < 2% |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥5x faster than Python |
| 5 | Edge cases | M=2 (degenerates to NSGA-II), singular intercepts, p=1 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-60 NSGA-II (shares non-dominated sort)
- Das-Dennis structured reference-point generator (inline)

## Pipeline stage (non-conflict)
**Owns:** many-objective Pareto selector slot (M ≥ 4)
**Alternative to:** META-60 NSGA-II (M ≤ 3), META-62 MOEA/D (decomposition variant)
**Coexists with:** META-39 query-cluster router (per-cluster MO tuning), META-04 coordinate ascent

## Test plan
- DTLZ2 (M=3, d=12): IGD ≤ 0.005 vs analytical Pareto surface
- DTLZ2 (M=5, d=14): IGD ≤ 0.05
- M=2: matches META-60 NSGA-II within 5% IGD
- Singular intercept matrix: falls back to nadir-point normalisation, no crash
- |Z| > N: raises `ValueError` with descriptive message
