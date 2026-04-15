# META-73 — Online AdaBoost.OC

## Overview
**Category:** Online ensemble learner (importance-weighted boosting with cost-sensitive updates)
**Extension file:** `online_adaboost_oc.cpp`
**Replaces/improves:** Batch AdaBoost in META-26 stacking when training data arrives one example at a time and the cost of the two error types differs (e.g. false-positive link suggestion costs more than a false-negative)
**Expected speedup:** ≥5x over Python reference (`river.ensemble.AdaBoostClassifier`)
**RAM:** <30 MB | **Disk:** <1 MB

## Algorithm
```
Input: stream of (x_t, y_t, c_t) where c_t is per-class cost vector,
       T weak online learners h_1..h_T (any META-70/72/74 base), initial weights α_i
Output: ensemble H(x) = sign( Σ_i α_i · h_i(x) )

initialise α_i = 0; weak learners h_i with their internal state
for each example (x_t, y_t, c_t):                                                   # Chen et al. 2012 §3
    λ_t = c_t · 1                                  # initial example importance
    for i = 1..T:
        # Online Poisson re-sampling for example weight (Oza 2001 trick)
        k ~ Poisson(λ_t)
        repeat k times: h_i.partial_fit(x_t, y_t)                                   # weighted update
        ŷ_i = h_i.predict(x_t)
        # Cost-sensitive error and α update (AdaBoost.OC variant)
        ε_i = (sw_i^wrong + smoothing) / (sw_i^total + 2·smoothing)                # smoothed error
        α_i = ½ · log((1 − ε_i) / ε_i)                                              # SAMME / OC weight
        if ŷ_i = y_t:  λ_t ← λ_t · (1 − ε_i) / 1                                    # decrease importance
        else:          λ_t ← λ_t · ε_i / (1 − ε_i)                                  # increase importance
        # Maintain running sw_i^wrong, sw_i^total via exp-decay
        sw_i^total  ← γ · sw_i^total  + λ_t
        sw_i^wrong  ← γ · sw_i^wrong  + λ_t · 𝟙[ŷ_i ≠ y_t]
```
- Time complexity: O(T · cost(weak.partial_fit)) per example
- Space complexity: O(T · |state of one weak learner|)
- Convergence: bounded regret if each weak learner has online sub-linear regret (Chen 2012 Thm 1)

## Academic source
**Chen, S.-T., Lin, H.-T., Lu, C.-J. (2012).** "An online boosting algorithm with theoretical justifications." *Journal of Machine Learning Research* 13:243-270. (Online AdaBoost.OC variant; original Oza online boosting in Oza & Russell 2001.)

## C++ Interface (pybind11)
```cpp
struct OnlineBoostState {
    int T;
    std::vector<float> alpha;
    std::vector<float> sw_total, sw_wrong;
    std::vector<std::function<int(const float*)>>     predictors;
    std::vector<std::function<void(const float*, int, float)>> updaters;   // (x, y, weight)
    float gamma_decay, smoothing;
    std::mt19937_64 rng;
};

void boost_step(OnlineBoostState& s, const float* x, int y, float cost);
int  boost_predict(const OnlineBoostState& s, const float* x);
```

## Memory budget
- Runtime RAM: <30 MB (T ≤ 50, weak-learner state ≤ 500 KB each)
- Disk: <1 MB
- Allocation: weak-learner state held by callbacks; α, sw arrays preallocated

## Performance target
- Python baseline: `river.ensemble.AdaBoostClassifier`
- Target: ≥5x faster (avoids per-example Python dispatch into each base learner)
- Benchmark: stream of 100k examples × T ∈ {10, 50}

## Pre-implementation safety checklist
**Must satisfy `backend/extensions/CPP-RULES.md`** — `-Werror -Wsign-conversion`, no raw `new`/`delete` in step kernel, RNG seeded once thread-locally, NaN/Inf checks on cost and on ε_i (clamp ε_i ∈ [smoothing, 1−smoothing] to keep log finite), double accumulator for sw_total / sw_wrong (decayed sums lose precision after 1M steps), `noexcept` destructors, Poisson sampler implemented inline (Knuth's algorithm for λ ≤ 30, Atkinson rejection for larger λ), no `std::function` in the inner k-repeat update loop (cache once via switch on i), gracefully handle weak learner that returns prediction outside {-1,+1} (treat as wrong).

## Pre-merge gates
| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings |
| 2 | `pytest test_parity_meta_73.py` | Cumulative accuracy within 2% of river reference over 100k stream |
| 3 | ASAN + UBSAN | Zero errors |
| 4 | Benchmark | ≥5x faster than Python |
| 5 | Edge cases | T=1, c_t=0, all-positive labels, NaN cost pass |
| 6 | Valgrind | Zero leaks |
| 7 | TSAN | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance |

## Dependencies
- META-70 FTRL-Proximal (default weak learner — fast online linear)
- META-72 OMD (alternative weak learner)
- Inline Knuth + Atkinson Poisson sampler

## Pipeline stage (non-conflict)
**Owns:** online ensemble boosting slot
**Alternative to:** META-26 stacking (offline batch), META-27 Bayesian model averaging (offline)
**Coexists with:** META-70/META-72/META-74 (any of which can be the weak learner), META-25 sliding-window retrainer

## Test plan
- Stationary stream: cumulative accuracy converges to batch AdaBoost within 2%
- Concept-drift stream: ensemble adapts within 1000 post-drift examples
- T=1: degenerates to single weak learner with weight α_1 = ½·log((1−ε)/ε)
- All-positive labels: α_i → +∞ — clamp triggers, no overflow
- NaN cost: example skipped, warning emitted
