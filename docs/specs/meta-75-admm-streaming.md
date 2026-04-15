# META-75 — Streaming ADMM (Consensus)

## Overview
**Category:** Distributed/streaming convex optimiser (alternating direction method of multipliers)
**Extension file:** `admm_streaming.cpp`
**Replaces/improves:** META-70 / META-74 when the loss naturally decomposes into N blocks (e.g. one per query cluster, one per content type) and a global consensus weight is required without sharing raw data across blocks
**Expected speedup:** ≥4x over Python `cvxpy` ADMM solver per round
**RAM:** <50 MB | **Disk:** <1 MB

## Algorithm
```
Input: N local convex losses f_i(w_i), consensus weight z ∈ ℝ^d, dual u_i ∈ ℝ^d,
       penalty ρ > 0
Output: consensus z* = argmin_z Σ_i f_i(z)

initialise w_i^0 = 0, u_i^0 = 0, z^0 = 0
for k = 0..max_iter:
    # 1. Local updates (parallel across i = 1..N)                            # Boyd et al. 2011 §7.1
    for i = 1..N:
        w_i^{k+1} = argmin_{w}  f_i(w) + (ρ/2) · ‖w − z^k + u_i^k‖²
    # 2. Global consensus (closed form: average of local + dual)
    z^{k+1} = (1/N) · Σ_i (w_i^{k+1} + u_i^k)                                # Eq. (7.7) in Boyd 2011
    # 3. Dual ascent (parallel across i)
    for i = 1..N:
        u_i^{k+1} = u_i^k + w_i^{k+1} − z^{k+1}
    # 4. Convergence check
    r^k = sqrt(Σ_i ‖w_i^{k+1} − z^{k+1}‖²)         # primal residual
    s^k = ρ · sqrt(N) · ‖z^{k+1} − z^k‖             # dual residual
    if r^k ≤ ε_pri AND s^k ≤ ε_dual: break
return z
```
- For streaming: re-evaluate f_i with the latest mini-batch each round; ρ may be adapted (Boyd 2011 §3.4.1)
- Time complexity: O(max_iter · N · cost(local-solve))
- Space complexity: O(N · d) for w_i and u_i + O(d) for z
- Convergence: residuals r^k, s^k → 0 for any convex closed proper f_i (Boyd 2011 Thm 1)

## Academic source
**Boyd, S., Parikh, N., Chu, E., Peleato, B., Eckstein, J. (2011).** "Distributed optimization and statistical learning via the alternating direction method of multipliers." *Foundations and Trends in Machine Learning* 3(1):1-122. DOI: `10.1561/2200000016`.

## C++ Interface (pybind11)
```cpp
struct ADMMState {
    int N, d;
    std::vector<float> z, w_blocks, u_blocks;     // w/u stored as N · d row-major
    float rho, eps_pri, eps_dual;
    std::vector<std::function<void(const float*, const float*, float, float*)>> local_solvers;
    // local_solvers[i](z, u_i, rho, w_i_out) writes argmin of the augmented Lagrangian for block i
};

bool admm_round(ADMMState& s);                    // returns true if converged
```

## Memory budget
- Runtime RAM: <50 MB (N ≤ 100 blocks, d ≤ 1000 → 100·1000·8 bytes = 0.8 MB; cap leaves headroom for local-solver scratch)
- Disk: <1 MB
- Allocation: aligned 64-byte arena for w_blocks and u_blocks; one scratch d-vector for residual computation

## Performance target
- Python baseline: `cvxpy` per-round ADMM
- Target: ≥4x faster (parallelisable across N via OpenMP)
- Benchmark: N ∈ {10, 100} × d ∈ {100, 1000} × 200 rounds, distributed lasso

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in round kernel, NaN/Inf checks on every w_i^{k+1} returned by a local solver (any NaN block → entire round aborts cleanly with error code, no silent contamination), double accumulator for the consensus average and the residual-norm reductions (sums over N blocks of d-vectors), `noexcept` destructors, no `std::function` invocation inside an OpenMP parallel-for that captures by reference (capture by value or via `static` block-index dispatch table), ρ adaptation guarded against ρ → 0 or ρ → ∞ (clamp ρ ∈ [1e-6, 1e6]), SIMD residual kernel uses `_mm256_zeroupper()`, GIL released around local-solver callback batch.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_75.py` | Final z matches cvxpy reference within 1e-4 on lasso |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥4x faster than Python |
| 5 | Edge cases | N=1 (degenerates to single-block prox), N=2, ρ=0 (caller error → ValueError), NaN block pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races (OpenMP parallel-for inside local-update phase) |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-17 elastic-net regulariser (default local-solve for lasso/ridge blocks)
- META-74 projected OGD (when local f_i is constrained but smooth)
- OpenMP for the parallel local-update phase

## Pipeline stage (non-conflict)
**Owns:** consensus / distributed online optimiser slot
**Alternative to:** META-70 FTRL (single-machine sparse), META-74 projected OGD (single-machine), proximal-gradient methods
**Coexists with:** META-71 ONS (per-block), META-72 OMD (per-block), META-25 sliding-window retrainer

## Test plan
- Distributed lasso (N=10, d=100): consensus z matches centralised lasso within 1e-4
- N=1: degenerates to single-block proximal step, matches the local solver's output
- ρ adaptation: residual ratio kept within [0.1, 10] across rounds
- NaN in one block's w_i: round aborts, state unchanged, error returned
- 1000-round run with concept-drift: consensus tracks shifting optimum
