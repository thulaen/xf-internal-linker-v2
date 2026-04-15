# META-195 — Meta-Learner Family (T/S/X-Learner)

## Overview
**Category:** Causal inference (model-agnostic CATE via base regressors)
**Extension file:** `meta_learners.cpp`
**Replaces/improves:** Single-recipe CATE models (causal forest META-194) when base regressors can be swapped
**Expected speedup:** ≥5x over Python econml metalearner numpy composition
**RAM:** <24 MB | **Disk:** <1 MB

## Algorithm

```
Input: n samples (X_i, T_i, Y_i), base regressors trained by caller; choice ∈ {T, S, X}

T-learner:
    μ̂_1 = regressor fit on {(X_i, Y_i) : T_i = 1}
    μ̂_0 = regressor fit on {(X_i, Y_i) : T_i = 0}
    τ̂_T(x) = μ̂_1(x) − μ̂_0(x)

S-learner:
    μ̂ = regressor fit on {((X_i, T_i), Y_i)}          // treatment is a feature
    τ̂_S(x) = μ̂(x, 1) − μ̂(x, 0)

X-learner:
    Fit μ̂_1, μ̂_0 as T-learner
    Impute counterfactuals:
        D̃_i^1 = Y_i − μ̂_0(X_i)    for T_i = 1
        D̃_i^0 = μ̂_1(X_i) − Y_i    for T_i = 0
    Fit τ̂_1 on (X, D̃^1) using treated; τ̂_0 on (X, D̃^0) using controls
    Propensity ê(x); combine:   τ̂_X(x) = ê(x)·τ̂_0(x) + (1 − ê(x))·τ̂_1(x)
```

- **Paper update rule (Künzel et al.):** T-learner trains separate models `μ̂_1, μ̂_0`; S-learner fuses with T as feature; X-learner imputes counterfactuals then averages
- **Time complexity:** O(n) per combine pass (base-regressor cost lives in caller)
- **Space complexity:** O(n) for pseudo-outcome buffers (X-learner only)

## Academic Source
Künzel, S. R., Sekhon, J. S., Bickel, P. J. & Yu, B. (2019). "Metalearners for Estimating Heterogeneous Treatment Effects Using Machine Learning". Proceedings of the National Academy of Sciences, Vol. 116, No. 10, pp. 4156-4165. DOI: 10.1073/pnas.1804597116

## C++ Interface (pybind11)

```cpp
// T-learner combine
std::vector<float> t_learner_combine(
    const float* mu1, const float* mu0, int n);

// X-learner combine (requires per-sample ê and both τ̂_1, τ̂_0 predictions)
std::vector<float> x_learner_combine(
    const float* tau1, const float* tau0, const float* e_hat, int n);

// X-learner pseudo-outcome builder (called before fitting second-stage τ̂_0, τ̂_1)
void x_learner_pseudo(
    const uint8_t* treatment, const float* outcome,
    const float* mu1, const float* mu0,
    int n, float* out_d1, float* out_d0);
```

## Memory Budget
- Runtime RAM: <24 MB for n=1e6 (4 MB per combined vector; X-learner uses 2 buffers)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: single `std::vector<float>` per API; `reserve(n)`

## Performance Target
- Python baseline: `econml.metalearners` numpy composition
- Target: ≥5x faster via fused AVX2 lerp
- Benchmark: 3 sizes — n=1e3, n=1e5, n=1e6

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** OpenMP parallel per-sample; all operations are embarrassingly parallel.

**Memory:** No raw `new`/`delete`. `reserve()` on outputs. Bounds-checked in debug.

**Object lifetime:** Read-only input pointers; caller owns output buffers for `x_learner_pseudo`.

**Type safety:** Explicit `static_cast` narrowing. `T ∈ {0,1}`; `ê ∈ [0,1]` validated.

**SIMD:** AVX2 FMA for lerp `ê·τ̂_0 + (1−ê)·τ̂_1`. `_mm256_zeroupper()` on exit. `alignas(64)`.

**Floating point:** Flush-to-zero. NaN/Inf entry checks. No division, so no clipping needed.

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Fused single pass per API call.

**Error handling:** Destructors `noexcept`. Validate all shapes equal. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_195.py` | Matches econml T/S/X learners within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than econml numpy reference |
| 5 | `pytest test_edges_meta_195.py` | ê=0, ê=1, n=1, identical μ̂_1 and μ̂_0 |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races across OMP |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Caller supplies base-regressor predictions (μ̂_1, μ̂_0, τ̂_0, τ̂_1, ê)

## Pipeline Stage Non-Conflict
- **Owns:** Meta-learner combine step (T, S, X) given nuisance predictions
- **Alternative to:** META-194 (causal forest), META-193 (doubly robust for ATE only)
- **Coexists with:** META-193 (DR) — DR pseudo-outcomes can be plugged into X-learner's second stage; META-194 can serve as the base τ̂_0/τ̂_1 regressor

## Test Plan
- T-learner with identical μ̂_1, μ̂_0: verify τ̂ = 0 everywhere
- X-learner with ê ≡ 0: verify τ̂_X = τ̂_1 exactly
- X-learner with ê ≡ 1: verify τ̂_X = τ̂_0 exactly
- Pseudo-outcome builder: verify D̃^1 has values only where T=1, D̃^0 only where T=0
- NaN in any input: verify raises ValueError
