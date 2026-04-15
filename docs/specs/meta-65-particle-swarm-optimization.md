# META-65 — Particle Swarm Optimization

## Overview
**Category:** Metaheuristic optimizer (population, velocity-based)
**Extension file:** `pso.cpp`
**Replaces/improves:** META-04 coordinate ascent and META-06 random search on rugged, multi-modal NDCG landscapes where gradient information is unavailable
**Expected speedup:** ≥6x over `pyswarms.single.global_best.GlobalBestPSO`
**RAM:** <15 MB | **Disk:** <1 MB

## Algorithm
```
Input: swarm size S, dim d, inertia ω, cognitive c_1, social c_2, fitness f
Output: g_best ≈ argmin f(x)

initialise positions x_i ∈ [lb, ub]^d uniformly; v_i = 0; p_best_i = x_i
g_best = argmin_{i} f(x_i)
for t = 0..max_iter:
    for i = 1..S:
        sample r_1, r_2 ~ U[0,1]^d                                  # Kennedy & Eberhart 1995 eq. 1
        v_i ← ω·v_i + c_1·r_1·(p_best_i − x_i) + c_2·r_2·(g_best − x_i)
        v_i ← clamp(v_i, −v_max, +v_max)                            # velocity clamping (Eberhart 2000)
        x_i ← x_i + v_i                                             # eq. 2
        x_i ← clamp(x_i, lb, ub)
        if f(x_i) < f(p_best_i): p_best_i = x_i
    if f(min p_best) < f(g_best): g_best = argmin_i f(p_best_i)
return g_best
```
- Time complexity: O(max_iter · S · d) per iteration plus S evaluations of f
- Space complexity: O(S · d) for positions + O(S · d) for velocities + O(S · d) for p_best
- Convergence: linear-time-stable when ω + c_1/2 + c_2/2 < 1 (Clerc & Kennedy 2002 §III)

## Academic source
**Kennedy, J., Eberhart, R. (1995).** "Particle swarm optimization." *Proceedings of IEEE International Conference on Neural Networks*, vol. 4, pp. 1942-1948. DOI: `10.1109/ICNN.1995.488968`.

## C++ Interface (pybind11)
```cpp
std::vector<float> pso(
    const float* lb, const float* ub, int d,
    std::function<float(const float*)> fitness,
    int swarm_size, int max_iter,
    float omega, float c1, float c2, float v_max_frac, uint64_t seed
);
```

## Memory budget
- Runtime RAM: <15 MB (S ≤ 100, d ≤ 200)
- Disk: <1 MB
- Allocation: aligned 64-byte arena for positions/velocities/p_best (3 · S · d floats)

## Performance target
- Python baseline: `pyswarms.single.global_best.GlobalBestPSO`
- Target: ≥6x faster
- Benchmark: S=50 × d ∈ {10, 50, 200} × 500 iterations on Rastrigin

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in inner loop, RNG seeded once and stored thread-locally, NaN/Inf checks on every fitness call (NaN → +Inf), double accumulator for SIMD velocity update reductions if needed, `noexcept` destructors, no `std::function` in per-particle inner loop (cache function pointer once at entry), velocity-clamp uses fused SIMD `_mm256_min_ps`/`_mm256_max_ps` with `_mm256_zeroupper()` after kernel, position-clamp likewise.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_65.py` | Final g_best within 5% of pyswarms reference |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than Python |
| 5 | Edge cases | S=1, d=1, lb=ub, NaN fitness pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Mersenne Twister RNG (std::mt19937_64), shared with META-60/META-66
- META-19 max-norm clipper (re-used for velocity clamp logic)

## Pipeline stage (non-conflict)
**Owns:** swarm metaheuristic optimizer slot
**Alternative to:** META-66 ant colony, META-67 cuckoo search, META-68 firefly, META-69 bat (other nature-inspired metaheuristics)
**Coexists with:** META-04 coordinate ascent (gradient-aware), META-08 differential evolution (genetic alternative)

## Test plan
- 2D Rosenbrock: converges to (1, 1) within 200 iters
- Rastrigin (d=10): finds global minimum within 500 iters with high probability (≥90% of seeds)
- S=1: degenerates to random walk, no crash
- lb = ub: returns lb (constant-fitness landscape)
- NaN in fitness: treated as +Inf, particle still updates
