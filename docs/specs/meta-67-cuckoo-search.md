# META-67 — Cuckoo Search via Lévy Flights

## Overview
**Category:** Metaheuristic optimizer (Lévy-flight global search + local replacement)
**Extension file:** `cuckoo_search.cpp`
**Replaces/improves:** META-65 PSO when the search landscape has rare, far-away optima reachable only by heavy-tailed jumps (Gaussian / Cauchy proposals miss them)
**Expected speedup:** ≥6x over Python `mealpy` cuckoo implementation
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm
```
Input: n nests (candidate solutions), discovery probability p_a ∈ (0,1),
       Lévy exponent β ∈ (1,3] (β=1.5 standard), step scale α
Output: best nest x* ≈ argmin f(x)

initialise nests x_1..x_n ∈ [lb, ub]^d uniformly; evaluate f
for t = 0..max_iter:
    # 1. Generate a new solution via Lévy flight                                    # Yang & Deb 2009 §3
    pick random cuckoo i; sample step from Lévy(β):
        u ~ N(0, σ_u²),  v ~ N(0, 1)
        step = u / |v|^(1/β)
        with σ_u = (Γ(1+β)·sin(π·β/2) / (Γ((1+β)/2)·β·2^((β−1)/2)))^(1/β)         # Mantegna 1994
    x_new = x_i + α · step ⊙ (x_i − x_best)
    x_new ← clamp(x_new, lb, ub)
    pick random nest j; if f(x_new) < f(x_j): x_j = x_new
    # 2. Abandon worst p_a fraction of nests
    sort nests by fitness; replace worst ⌊p_a·n⌋ with new random nests
return best of nests
```
- Time complexity: O(max_iter · n · d) plus n_eval fitness calls
- Space complexity: O(n · d)
- Convergence: heavy-tailed Lévy step ensures positive probability of escaping any compact set in finite time (Yang 2010 §6.3)

## Academic source
**Yang, X.-S., Deb, S. (2009).** "Cuckoo search via Lévy flights." *Proc. World Congress on Nature & Biologically Inspired Computing (NaBIC)*, IEEE, pp. 210-214. DOI: `10.1109/NABIC.2009.5393690`.

## C++ Interface (pybind11)
```cpp
std::vector<float> cuckoo_search(
    const float* lb, const float* ub, int d,
    std::function<float(const float*)> fitness,
    int n_nests, int max_iter,
    float p_abandon, float beta_levy, float alpha_step,
    uint64_t seed
);
```

## Memory budget
- Runtime RAM: <12 MB (n ≤ 100, d ≤ 200)
- Disk: <1 MB
- Allocation: aligned 64-byte arena for nests

## Performance target
- Python baseline: `mealpy.swarm_based.CSO` (cuckoo search)
- Target: ≥6x faster
- Benchmark: n=25 × d ∈ {10, 50, 200} × 500 iters on Rastrigin

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in inner loop, RNG seeded once thread-locally, NaN/Inf checks on fitness and on the Lévy step (|v|≈0 → divide-by-zero — clamp |v| ≥ 1e-12), double accumulator for σ_u Mantegna constant computed once at entry, `noexcept` destructors, no `std::function` in inner loop, sort step uses `std::partial_sort` for the worst p_a fraction (no full sort), SIMD clamp uses `_mm256_zeroupper()`, Mantegna σ_u pre-computed once and cached.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_67.py` | Final best within 5% of mealpy reference |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥6x faster than Python |
| 5 | Edge cases | n=1, d=1, p_a=0, p_a=1, β=1.0001, β=3 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Mersenne Twister RNG (std::mt19937_64)
- Inline Mantegna Lévy sampler (no external dep)

## Pipeline stage (non-conflict)
**Owns:** Lévy-flight metaheuristic slot
**Alternative to:** META-65 PSO, META-68 firefly, META-69 bat (other nature-inspired)
**Coexists with:** META-66 ant colony (combinatorial), META-04 coordinate ascent

## Test plan
- 2D Rastrigin: finds global min ≥85% of seeds within 500 iters
- Multi-modal Schwefel d=10: outperforms META-65 PSO on equal eval budget
- p_a=0: no abandonment, all-Lévy search
- p_a=1: degenerates to random restart per iteration
- β=1.0001: extremely heavy tail, large jumps, no overflow
