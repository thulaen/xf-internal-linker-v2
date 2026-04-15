# META-74 — Projected Online Gradient Descent

## Overview
**Category:** Online learner (Euclidean projection onto convex constraint set)
**Extension file:** `projected_ogd.cpp`
**Replaces/improves:** META-35 SGD-momentum when the weight vector must stay in a convex set K (e.g. simplex, box, or ‖w‖₂ ≤ R) and the cheapest sub-linear-regret algorithm is desired
**Expected speedup:** ≥8x over Python loop with `numpy` projection
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm
```
Input: convex compact K ⊂ ℝ^d with diameter R = max_{u,v ∈ K} ‖u − v‖₂,
       gradient bound G ≥ ‖g_t‖₂ for all t, time horizon T
Output: weight sequence w_1, w_2, ...

η = R / (G · sqrt(T))                                                       # Zinkevich 2003 §2
initialise w_1 ∈ K (e.g. centroid)
for t = 1..T:
    receive convex L_t; play w_t; suffer L_t(w_t)
    g_t = ∇L_t(w_t)
    y_{t+1} = w_t − η · g_t                                                 # Euclidean gradient step
    w_{t+1} = Π_K(y_{t+1}) = argmin_{w ∈ K} ‖w − y_{t+1}‖₂                  # Euclidean projection
```
- Common projections:
  - **Box** Π_K(y)_i = clamp(y_i, lb_i, ub_i)                  → O(d)
  - **L2-ball** Π_K(y) = y · min(1, R / ‖y‖₂)                  → O(d)
  - **Simplex** sort-then-shift (Held & Wolfe / Duchi 2008)    → O(d log d)
- Time complexity: O(d) per step (box / L2), O(d log d) (simplex)
- Space complexity: O(d)
- Regret bound: R · G · sqrt(T) (Zinkevich 2003 Thm 1) — tight for adversarial convex losses

## Academic source
**Zinkevich, M. (2003).** "Online convex programming and generalized infinitesimal gradient ascent." *Proc. 20th International Conference on Machine Learning (ICML)*, pp. 928-935.

## C++ Interface (pybind11)
```cpp
struct OGDState {
    std::vector<float> w;
    int d;
    float eta;
    int proj_kind;            // 0 = box, 1 = L2-ball, 2 = simplex
    std::vector<float> lb, ub;   // for box
    float R;                  // for L2-ball / simplex sum constraint
};

void ogd_step(OGDState& s, const float* gradient);
```

## Memory budget
- Runtime RAM: <8 MB (d ≤ 100000)
- Disk: <1 MB
- Allocation: aligned 64-byte for w; one scratch buffer for the gradient step result

## Performance target
- Python baseline: numpy loop with `np.clip` / projection helper
- Target: ≥8x faster
- Benchmark: d ∈ {100, 1000, 100000} × 100k steps for each projection kind

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in step kernel, NaN/Inf checks on gradient (NaN component → skip the entire step, log warning), double accumulator for L2-ball ‖y‖₂ reduction (sum of d squares), `noexcept` destructors, no `std::function` in step kernel (proj_kind selected once at state-construct, branch hoisted), simplex projection uses `std::sort` once on a scratch buffer (no per-step allocation thanks to a member scratch vector reserved at construction), SIMD clamp / norm uses `_mm256_zeroupper()` after each kernel.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_74.py` | Final w matches numpy reference within 1e-6 over 10k steps for each proj kind |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥8x faster than Python |
| 5 | Edge cases | d=1, η=0, gradient orthogonal to K (projection onto closest face), NaN, simplex with d=1 pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-19 max-norm clipper (re-used as box-projection kernel)
- Inline Held-Wolfe / Duchi simplex projection helper

## Pipeline stage (non-conflict)
**Owns:** Euclidean projected online gradient slot
**Alternative to:** META-70 FTRL-Proximal (sparse L1), META-71 ONS (quasi-Newton, exp-concave), META-72 OMD (Bregman, non-Euclidean)
**Coexists with:** META-75 streaming ADMM, META-25 sliding-window retrainer, META-35 SGD-momentum (offline)

## Test plan
- Box projection: matches `np.clip` exactly
- L2-ball: vector inside ball unchanged; vector outside scaled to radius R
- Simplex: result sums to R (within 1e-6) and all components ≥ 0
- η=0: w never moves
- NaN gradient: state unchanged, warning emitted
