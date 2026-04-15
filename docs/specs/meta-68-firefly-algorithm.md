# META-68 — Firefly Algorithm

## Overview
**Category:** Metaheuristic optimizer (attractiveness-based, all-pairs interaction)
**Extension file:** `firefly.cpp`
**Replaces/improves:** META-65 PSO when the landscape has many local optima of comparable quality (firefly's attractiveness decays with distance, so each local basin is preserved as a sub-swarm)
**Expected speedup:** ≥4x over `mealpy.swarm_based.FFA`
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm
```
Input: n fireflies, base attractiveness β_0, light absorption γ, randomisation α,
       fitness f (interpret f as inverse light intensity)
Output: best firefly x* ≈ argmin f(x)

initialise x_1..x_n ∈ [lb, ub]^d uniformly; evaluate I_i = f(x_i)
for t = 0..max_iter:
    for i = 1..n:
        for j = 1..n:
            if I_j < I_i:                                       # firefly j is brighter (lower fitness)
                r_ij = ‖x_i − x_j‖₂                            # Yang 2008 §10
                β = β_0 · exp(−γ · r_ij²)                      # attraction kernel
                ε ~ U[−0.5, 0.5]^d
                x_i ← x_i + β · (x_j − x_i) + α · ε             # move firefly i toward j
                x_i ← clamp(x_i, lb, ub)
                I_i = f(x_i)
    α ← α · 0.97                                                # cooling schedule (optional)
return argmin_i I_i
```
- Time complexity: O(max_iter · n² · d) — quadratic per iter (all-pairs interaction)
- Space complexity: O(n · d)
- Convergence: heuristic — no analytical convergence proof, but empirical robustness on multi-modal benchmarks (Yang 2008 Ch. 10)

## Academic source
**Yang, X.-S. (2008).** *Nature-Inspired Metaheuristic Algorithms*. Luniver Press, Chapter 10. ISBN: `978-1-905986-10-1`. Updated form in Yang (2010) *Engineering Optimization*, Wiley.

## C++ Interface (pybind11)
```cpp
std::vector<float> firefly(
    const float* lb, const float* ub, int d,
    std::function<float(const float*)> fitness,
    int n_fireflies, int max_iter,
    float beta0, float gamma, float alpha, float alpha_cooling,
    uint64_t seed
);
```

## Memory budget
- Runtime RAM: <12 MB (n ≤ 50, d ≤ 200)
- Disk: <1 MB
- Allocation: aligned 64-byte arena for positions; pre-computed exp() lookup table optional

## Performance target
- Python baseline: `mealpy.swarm_based.FFA`
- Target: ≥4x faster (smaller multiplier than PSO because the all-pairs O(n²) loop is the bottleneck and Python’s numpy is already vectorised over n)
- Benchmark: n=30 × d ∈ {10, 50, 200} × 200 iters on Ackley

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in inner pair loop, RNG seeded once thread-locally, NaN/Inf checks on fitness, double accumulator for r_ij² (sum of squared diffs across d), `noexcept` destructors, no `std::function` in inner pair loop, exp() called via `std::expf` with NaN guard (γ·r²≈Inf → β=0, no exception), SIMD distance kernel uses `_mm256_zeroupper()`, position-clamp fused with update, fitness re-evaluated only when firefly actually moves (skip if I_j ≥ I_i guard above).

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_68.py` | Final best within 5% of mealpy reference |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥4x faster than Python |
| 5 | Edge cases | n=1, n=2, γ=0 (no decay), γ→∞ (random walk), NaN fitness pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Mersenne Twister RNG (std::mt19937_64)
- META-19 max-norm clipper for the per-dimension position clamp

## Pipeline stage (non-conflict)
**Owns:** attractiveness-decay metaheuristic slot
**Alternative to:** META-65 PSO, META-67 cuckoo, META-69 bat
**Coexists with:** META-66 ant colony (combinatorial), META-04 coordinate ascent (gradient-aware)

## Test plan
- Ackley d=10: finds global min ≥80% of seeds within 200 iters
- n=1: degenerates to random walk, no crash
- γ=0: every firefly attracts every other equally — degenerates to centroid drift
- γ→∞ (γ=1e6): all attractions → 0, only α·ε noise survives, becomes random search
- Equal fitness everywhere: no movement, returns initial best
