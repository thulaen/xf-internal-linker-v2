# META-69 — Bat Algorithm

## Overview
**Category:** Metaheuristic optimizer (echolocation, frequency-tuned velocity + adaptive local search)
**Extension file:** `bat.cpp`
**Replaces/improves:** META-65 PSO when the search needs an explicit exploration / exploitation toggle controlled by per-individual loudness and pulse-emission rate
**Expected speedup:** ≥5x over `mealpy.swarm_based.BA`
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm
```
Input: n bats, frequency range [f_min, f_max], initial loudness A_0 ≈ 1, initial pulse rate r_0 ∈ (0,1),
       loudness-decay α ∈ (0,1), pulse-rate growth γ > 0
Output: best bat x* ≈ argmin f(x)

initialise x_1..x_n; v_1..v_n = 0; A_i = A_0; r_i = r_0; evaluate
x_best = argmin f
for t = 0..max_iter:
    for i = 1..n:
        β ~ U[0,1]
        f_i = f_min + (f_max − f_min) · β                            # Yang 2010 eq. 1
        v_i ← v_i + (x_i − x_best) · f_i
        x_new = x_i + v_i                                            # eq. 2
        if rand() > r_i:
            x_new = x_best + 0.001 · ε · A_avg          where ε ~ N(0,1)^d   # local random walk
        x_new ← clamp(x_new, lb, ub)
        if rand() < A_i AND f(x_new) < f(x_i):
            x_i = x_new
            A_i = α · A_i                                            # loudness decays as bat closes in
            r_i = r_0 · (1 − exp(−γ · t))                            # pulse rate increases
            if f(x_i) < f(x_best): x_best = x_i
return x_best
```
- Time complexity: O(max_iter · n · d) plus n fitness evals per iter
- Space complexity: O(n · d) for positions + O(n · d) for velocities
- Convergence: heuristic — empirical convergence on standard test suite (Yang 2010 §4)

## Academic source
**Yang, X.-S. (2010).** "A new metaheuristic bat-inspired algorithm." *Nature Inspired Cooperative Strategies for Optimization (NICSO 2010)*, Studies in Computational Intelligence vol. 284, Springer, pp. 65-74. DOI: `10.1007/978-3-642-12538-6_6`.

## C++ Interface (pybind11)
```cpp
std::vector<float> bat_algorithm(
    const float* lb, const float* ub, int d,
    std::function<float(const float*)> fitness,
    int n_bats, int max_iter,
    float f_min, float f_max,
    float A0, float r0, float alpha_loud, float gamma_rate,
    uint64_t seed
);
```

## Memory budget
- Runtime RAM: <12 MB (n ≤ 50, d ≤ 200)
- Disk: <1 MB
- Allocation: aligned 64-byte arena for positions and velocities

## Performance target
- Python baseline: `mealpy.swarm_based.BA`
- Target: ≥5x faster
- Benchmark: n=30 × d ∈ {10, 50, 200} × 500 iters on Schwefel

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in inner loop, RNG seeded once thread-locally (one for U[0,1], one for N(0,1)), NaN/Inf checks on fitness and on f_max−f_min (must be > 0), double accumulator for SIMD velocity update if d ≥ 64, `noexcept` destructors, no `std::function` in inner per-bat loop, A_avg recomputed once per generation (not per bat), exp() in pulse-rate update guarded against extreme γ·t (overflow → r_i = r_0), SIMD position-clamp uses `_mm256_zeroupper()`.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_69.py` | Final best within 5% of mealpy reference |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥5x faster than Python |
| 5 | Edge cases | n=1, f_min=f_max=0, A_0=0, r_0=1, NaN fitness pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Mersenne Twister RNG (std::mt19937_64)
- META-19 max-norm clipper (position clamp)

## Pipeline stage (non-conflict)
**Owns:** echolocation metaheuristic slot
**Alternative to:** META-65 PSO, META-67 cuckoo, META-68 firefly
**Coexists with:** META-66 ant colony, META-04 coordinate ascent

## Test plan
- 2D Rosenbrock: converges to (1, 1) within 300 iters
- Schwefel d=10: finds global min ≥75% of seeds within 500 iters
- f_min=f_max=0: velocity update degenerates to pure inertia
- A_0=0: no bat ever accepts a new position — returns initial best
- r_0=1: never enters local-walk branch — pure echolocation
