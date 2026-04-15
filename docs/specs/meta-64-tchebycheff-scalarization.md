# META-64 — Tchebycheff Scalarisation

## Overview
**Category:** Multi-objective scalarisation (weighted-Chebyshev)
**Extension file:** `tchebycheff.cpp`
**Replaces/improves:** Linear weighted-sum scalarisation when the Pareto front is non-convex (weighted-sum cannot reach concave regions; Tchebycheff can)
**Expected speedup:** ≥8x over `numpy` per-call evaluation in MOEA/D inner loop
**RAM:** <2 MB | **Disk:** <1 MB

## Algorithm
```
Input: objective vector f(x) ∈ ℝ^M, weight vector λ ∈ ℝ^M with Σλ_i = 1, λ_i ≥ 0,
       reference (utopian/ideal) point z* with z*_i ≤ min f_i(x)
Output: scalar g_te(x | λ, z*) ∈ ℝ to be minimised

g_te(x | λ, z*) = max_{i=1..M}  λ_i · |f_i(x) − z*_i|       # Miettinen 1999 §3.4.3
```
- Vectorised form for M objectives: one fused-multiply-abs-max pass; SIMD-friendly
- Augmented Tchebycheff (regularised): `g_aug = g_te + ρ · Σ_i λ_i · |f_i(x) − z*_i|` with small ρ ≈ 1e-3 to ensure proper Pareto-optimality
- Time complexity: O(M) per call
- Space complexity: O(M)
- Property: every Pareto-optimal point is the unique minimiser of g_te for some λ (Miettinen 1999 Thm 3.4.5)

## Academic source
**Miettinen, K. (1999).** *Nonlinear Multiobjective Optimization*. Kluwer Academic Publishers, §3.4.3 ("Weighted Tchebycheff problem"). ISBN: `978-0-7923-8278-2`. Originated in Bowman (1976) and Steuer & Choo (1983).

## C++ Interface (pybind11)
```cpp
// Single-call evaluation; vectorised batch variant for MOEA/D neighbourhoods
float tchebycheff(const float* f, const float* lambda, const float* z_star, int M, float rho);

void tchebycheff_batch(
    const float* f_matrix, int N_solutions,
    const float* lambda, const float* z_star, int M,
    float rho, float* out_scalars
);
```

## Memory budget
- Runtime RAM: <2 MB (M ≤ 10, batch N ≤ 1000)
- Disk: <1 MB
- Allocation: stack-only; no heap

## Performance target
- Python baseline: `np.max(lambda * np.abs(f - z_star))`
- Target: ≥8x faster (eliminates Python broadcast and temporary allocation)
- Benchmark: M ∈ {2, 5, 10} × N_batch ∈ {100, 1000, 10000}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no heap allocation, NaN/Inf checks on f and z_star (NaN must short-circuit to +Inf so caller treats as infeasible), double accumulator for the augmented sum, `noexcept` function (pure scalar arithmetic), SIMD `_mm256_max_ps` reduction with `_mm256_zeroupper()` after kernel, no `std::function`, weight-sum invariant validated once at batch entry (Σλ ≈ 1 within 1e-6).

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_64.py` | Matches numpy reference within 1e-6 |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥8x faster than numpy |
| 5 | Edge cases | M=1, λ_i=0 for some i, z*=f, NaN, +Inf pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- None (standalone scalarisation primitive)

## Pipeline stage (non-conflict)
**Owns:** Chebyshev-norm scalarisation primitive slot
**Alternative to:** META-63 ε-constraint method (constraint-based), linear weighted-sum (built into other ops)
**Coexists with:** META-62 MOEA/D (consumes this as inner scalarisation), META-60 NSGA-II (no scalarisation needed)

## Test plan
- M=2 convex front: returns same minimiser as weighted-sum
- M=2 non-convex (concave) front: recovers concave-region points that weighted-sum cannot
- λ = (1, 0): degenerates to single-objective minimisation of f_1
- z* > f: returns negative value, no crash (caller’s contract requires z* ≤ f)
- NaN in f: returns +Inf, no exception
