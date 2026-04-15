# META-72 — Online Mirror Descent

## Overview
**Category:** Online learner (Bregman-divergence proximal step)
**Extension file:** `online_mirror_descent.cpp`
**Replaces/improves:** META-74 projected OGD when the geometry of the weight space is non-Euclidean (e.g. simplex weights → use entropic mirror map; positive weights → use squared-root map). OMD adapts the step to the local geometry via the Bregman divergence.
**Expected speedup:** ≥5x over Python reference
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm
```
Input: convex set K, mirror map ψ : K → ℝ (strictly convex, differentiable),
       Bregman divergence D_ψ(u, v) = ψ(u) − ψ(v) − ⟨∇ψ(v), u − v⟩,
       step size η, gradient g_t
Output: weight sequence w_1, w_2, ...

initialise w_1 = argmin_{w ∈ K} ψ(w)                                        # Bregman projection of 0
for t = 1..T:
    g_t = ∇L_t(w_t)
    w_{t+1} = argmin_{w ∈ K} (η · ⟨g_t, w⟩  +  D_ψ(w, w_t))                # Beck & Teboulle 2003 §2
    # Equivalent two-step form via dual mapping:
    #   y_{t+1} = (∇ψ)⁻¹(∇ψ(w_t) − η · g_t)             # gradient step in dual space
    #   w_{t+1} = argmin_{w ∈ K} D_ψ(w, y_{t+1})          # Bregman projection
```
- Common mirror maps:
  - **Euclidean** ψ(w)=½‖w‖² → recovers META-74 projected OGD
  - **Entropic** ψ(w)=Σ w_i·log w_i (simplex) → multiplicative weights / Hedge update `w_{t+1,i} ∝ w_{t,i} · exp(−η · g_{t,i})`
  - **p-norm** ψ(w)=½‖w‖_p² (p > 1)
- Time complexity: O(d) per step (general); O(d) for entropic with closed-form projection
- Space complexity: O(d)
- Regret bound: O(√(T · D_ψ(w*, w_1))) for convex losses (Beck & Teboulle 2003 Thm 4.1)

## Academic source
**Beck, A., Teboulle, M. (2003).** "Mirror descent and nonlinear projected subgradient methods for convex optimization." *Operations Research Letters* 31(3):167-175. DOI: `10.1016/S0167-6377(02)00231-6`.

## C++ Interface (pybind11)
```cpp
struct OMDState {
    std::vector<float> w;
    int d;
    float eta;
    int mirror_kind;     // 0 = Euclidean, 1 = entropic (simplex), 2 = p-norm
    float p_param;       // for p-norm
};

void omd_step(
    OMDState& s,
    const float* gradient
);
```

## Memory budget
- Runtime RAM: <10 MB (d ≤ 10000)
- Disk: <1 MB
- Allocation: aligned 64-byte for w; one scratch buffer of size d for dual step

## Performance target
- Python baseline: numpy entropic / Euclidean step
- Target: ≥5x faster
- Benchmark: d ∈ {100, 1000, 10000} × 100k steps for each mirror kind

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in step kernel, NaN/Inf checks on gradient (NaN → skip update), double accumulator for entropic-projection normaliser Σ exp(·) — use the log-sum-exp shift trick (subtract max before exp) to prevent overflow, `noexcept` destructors, no `std::function` in step kernel (mirror kind selected once via switch and inlined), SIMD `expf` via Cephes/SVML wrapper with `_mm256_zeroupper()`, entropic projection clamps w_i ≥ ε_min (=1e-30) to prevent log(0) on the next step, p-norm step uses `std::powf` only when p ≠ 2.

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_72.py` | Final w matches numpy reference within 1e-5 over 10k steps for each mirror kind |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥5x faster than Python |
| 5 | Edge cases | d=1, η=0, all-zero gradient, large gradient (entropic overflow guard), NaN pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-19 max-norm clipper (Euclidean projection onto box)
- Inline log-sum-exp helper (entropic projection)

## Pipeline stage (non-conflict)
**Owns:** Bregman-divergence online optimiser slot (mirror descent)
**Alternative to:** META-70 FTRL (sparse L1), META-71 ONS (quasi-Newton), META-74 projected OGD (Euclidean only)
**Coexists with:** META-75 streaming ADMM, META-25 sliding-window retrainer

## Test plan
- Entropic on simplex (d=10): converges to argmin gradient direction (single best expert)
- Euclidean: matches META-74 projected OGD exactly
- p=2: equivalent to Euclidean
- η=0: w never moves
- Large gradient (entropic): exp-overflow handled by log-sum-exp shift, no NaN
