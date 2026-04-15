# META-66 — Ant Colony Optimization

## Overview
**Category:** Combinatorial metaheuristic (pheromone-trail construction)
**Extension file:** `aco.cpp`
**Replaces/improves:** Greedy combinatorial selection (e.g. picking K best link slots) when interactions between choices matter and a probabilistic, history-aware constructor outperforms greedy
**Expected speedup:** ≥5x over Python ACO reference (`acopy` library)
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm
```
Input: graph G = (V, E), heuristic η_ij (e.g. 1/d_ij), evaporation ρ ∈ (0,1),
       deposit Q, exponents α (pheromone weight), β (heuristic weight), n_ants per cycle
Output: best tour T* (or best subset for set-construction problems)

initialise τ_ij = τ_0 ∀ (i,j) ∈ E
for cycle = 1..max_cycles:
    for each ant k = 1..n_ants:
        construct tour T_k by repeatedly choosing next node j with probability         # Dorigo 1992 §4.2
            p_ij^k = (τ_ij^α · η_ij^β) / Σ_{l ∈ allowed_k(i)} (τ_il^α · η_il^β)
        compute L(T_k)                                                                  # tour cost
    evaporate: τ_ij ← (1 − ρ) · τ_ij ∀ (i,j)
    deposit:   τ_ij ← τ_ij + Σ_{k: (i,j) ∈ T_k} Δτ_ij^k     where Δτ_ij^k = Q / L(T_k)
    track best: T* ← argmin L over all tours seen
return T*
```
- Time complexity: O(max_cycles · n_ants · |V|² )
- Space complexity: O(|V|² ) for pheromone matrix + O(n_ants · |V|) for tours
- Convergence: limit-pheromone bounded; convergence in value (Stützle & Dorigo 2002 Thm 4)

## Academic source
**Dorigo, M. (1992).** "Optimization, Learning and Natural Algorithms." PhD Thesis, Politecnico di Milano. Modern reference: Dorigo & Stützle, *Ant Colony Optimization*, MIT Press 2004, ISBN: `978-0-262-04219-2`.

## C++ Interface (pybind11)
```cpp
// Returns ordered tour (subset selection variant returns chosen indices)
std::vector<int> aco(
    const float* edge_cost, int V,            // V × V cost matrix (NaN for forbidden edges)
    int n_ants, int max_cycles,
    float alpha, float beta, float rho, float Q,
    float tau0, uint64_t seed
);
```

## Memory budget
- Runtime RAM: <20 MB (V ≤ 500 → 1 MB pheromone, n_ants ≤ 50)
- Disk: <1 MB
- Allocation: aligned 64-byte for τ matrix; arena for per-cycle tour storage

## Performance target
- Python baseline: `acopy` library
- Target: ≥5x faster
- Benchmark: V ∈ {50, 200, 500} × n_ants=30 × 100 cycles on synthetic TSP

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in inner construction loop, RNG seeded once thread-locally, NaN handled as forbidden edge (probability 0), double accumulator for the probability denominator (Σ over allowed neighbours can sum 1000s of small terms), `noexcept` destructors, no `std::function` in per-ant loop, allowed-set tracked via fixed-size `std::vector<bool>` reused per ant (no per-step allocation), SIMD pheromone-evaporate kernel uses `_mm256_zeroupper()`, roulette-wheel selection uses prefix-sum binary search rather than linear scan.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_66.py` | Best tour within 2% of acopy reference |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥5x faster than Python |
| 5 | Edge cases | V=2, n_ants=1, all-NaN row, ρ=0, ρ=1 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- Mersenne Twister RNG (std::mt19937_64)
- Inline prefix-sum + binary-search roulette wheel (no external dep)

## Pipeline stage (non-conflict)
**Owns:** combinatorial pheromone metaheuristic slot
**Alternative to:** META-65 PSO (continuous), META-67 cuckoo (continuous), META-68 firefly (continuous)
**Coexists with:** META-04 coordinate ascent (continuous params), META-39 query-cluster router

## Test plan
- TSP berlin52 instance: returns tour within 5% of known optimum
- V=2: returns the only valid tour
- All edges forbidden (NaN matrix): returns empty tour, no crash
- ρ=0 (no evaporation): pheromone grows unbounded — clamp triggers, no overflow
- ρ=1 (full evaporation): degenerates to per-cycle greedy random construction
