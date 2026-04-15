# META-63 — ε-Constraint Method

## Overview
**Category:** Multi-objective scalarisation (constraint reformulation)
**Extension file:** `epsilon_constraint.cpp`
**Replaces/improves:** META-60 / META-62 when one objective is clearly primary and others are bounded constraints (e.g. minimise latency subject to NDCG ≥ ε_NDCG)
**Expected speedup:** ≥10x over Python loop calling `scipy.optimize.minimize` per ε-grid point
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm
```
Input: M objectives f_1..f_M, primary index j, K grid points per non-primary objective
Output: K^(M−1) candidate Pareto points (one per ε-vector)

# (Haimes, Lasdon, Wismer 1971 §III)
build ε-grid: for each i ≠ j, choose ε_i^(1) < ... < ε_i^(K) over [min f_i, max f_i]
for each ε-vector ε = (ε_1, ..., ε_{j-1}, ε_{j+1}, ..., ε_M):
    solve: x*(ε) = argmin_x f_j(x)
                    s.t. f_i(x) ≤ ε_i  for all i ≠ j
    if feasible: record (f_1(x*), ..., f_M(x*))
return Pareto-filter of recorded tuples
```
- Time complexity: O(K^(M−1) · T_solve(d, M−1)) where T_solve is the inner constrained-optimiser time
- Space complexity: O(K^(M−1) · M) for stored points
- Convergence: every weakly-Pareto-optimal point can be obtained by some ε (Miettinen 1999 Thm 3.2.1)

## Academic source
**Haimes, Y. Y., Lasdon, L. S., Wismer, D. A. (1971).** "On a bicriterion formulation of the problems of integrated system identification and system optimization." *IEEE Transactions on Systems, Man, and Cybernetics* SMC-1(3):296-297. Modern reference: Miettinen, *Nonlinear Multiobjective Optimization*, Kluwer 1999, §3.2.

## C++ Interface (pybind11)
```cpp
// Returns matrix of recorded objective tuples, one row per feasible ε-point
py::array_t<float> epsilon_constraint(
    const float* x0, int d,
    std::function<float(const float*)> f_primary,
    std::function<void(const float*, float*)> f_secondary,   // writes M-1 floats
    int M, int primary_index, int K_grid_per_axis,
    const float* eps_min, const float* eps_max,
    int inner_solver_id            // 0 = ALM, 1 = penalty, 2 = SQP-stub
);
```

## Memory budget
- Runtime RAM: <8 MB (K^(M−1) ≤ 10000 stored tuples × M ≤ 5)
- Disk: <1 MB
- Allocation: arena for stored tuples; aligned 64-byte for ε-vector

## Performance target
- Python baseline: outer Python loop wrapping `scipy.optimize.minimize` with constraint dict
- Target: ≥10x faster (avoids per-grid-point Python interpreter overhead)
- Benchmark: K ∈ {5, 10, 20} × M ∈ {2, 3} × d=10

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in the per-grid-point hot loop, NaN/Inf checks on every f_primary and f_secondary return, double accumulator for constraint-violation sums, `noexcept` destructors, no `std::function` inside the inner solver (cache once), arena allocator for stored Pareto tuples, SIMD constraint-check loop uses `_mm256_zeroupper()`, infeasibility flag returned cleanly without exception in hot path.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_63.py` | Recovered front matches scipy outer-loop within IGD < 1% |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥10x faster than Python |
| 5 | Edge cases | M=2, K=1, all-infeasible, NaN constraint pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-04 coordinate ascent or META-40 Newton (inner constrained-solver)
- Optional META-43 L-BFGS-B (box constraints) for SQP-stub mode

## Pipeline stage (non-conflict)
**Owns:** constraint-based scalarisation slot
**Alternative to:** META-64 Tchebycheff (weighting-based scalarisation)
**Coexists with:** META-60 NSGA-II (population-based MO), META-62 MOEA/D (decomposition MO)

## Test plan
- 2-obj convex test (f_1 = ‖x‖², f_2 = ‖x − e‖²): recovered front lies on x = α·e segment
- M=2, K=1: returns at most 1 point
- All ε infeasible: returns empty matrix, no crash
- NaN in primary objective: raises `ValueError`
- Bicriterion linear program: recovers full Pareto edge within tolerance
