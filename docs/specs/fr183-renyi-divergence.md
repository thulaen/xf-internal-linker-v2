# FR-183 — Rényi Divergence (α-family)

## Overview
Rényi divergence is a one-parameter family of f-divergences indexed by `α ∈ (0, 1) ∪ (1, ∞)`. It generalises KL (recovered as `α → 1`), Hellinger (`α = 1/2`), and the χ² distance (`α = 2`). Different `α` values emphasise different parts of the distribution: `α < 1` emphasises low-probability mass (tail-sensitive), `α > 1` emphasises modes (peak-sensitive). For an internal-linker, exposing α as a tunable knob lets operators dial the host-destination divergence between "matches the long tail of the host topic" and "matches the dominant terms only". Complements `fr181-kl-divergence-source-destination` and `fr182-jensen-shannon-divergence`.

## Academic source
Rényi, A. "On measures of entropy and information." *Proceedings of the 4th Berkeley Symposium on Mathematical Statistics and Probability, Volume 1: Contributions to the Theory of Statistics*, University of California Press, pp. 547–561, 1961. URL: https://projecteuclid.org/euclid.bsmsp/1200512181. Modern reference: van Erven, T. and Harremoës, P. "Rényi Divergence and Kullback-Leibler Divergence." *IEEE Transactions on Information Theory* 60(7), 2014. DOI: `10.1109/TIT.2014.2320500`.

## Formula
From Rényi (1961), Eq. 5 — α-divergence for `α > 0, α ≠ 1`:

```
D_α(P ‖ Q) = ( 1 / (α − 1) ) · log( Σ_{x ∈ X} P(x)^α · Q(x)^(1 − α) )
```

Special cases:

```
α = 1/2 ⇒ D_{1/2}(P‖Q) = −2 · log( Σ √(P(x) · Q(x)) )      (Bhattacharyya / Hellinger-related)
α → 1   ⇒ D_α(P‖Q)    → D_KL(P‖Q)                          (Cover & Thomas 2006, p. 19)
α = 2   ⇒ D_2(P‖Q)    = log( Σ P(x)² / Q(x) )              (χ²-like)
α → ∞   ⇒ D_∞(P‖Q)    = log( max_x P(x)/Q(x) )             (max-divergence; min-entropy related)
```

Properties:
- `D_α(P‖Q) ≥ 0`, equality iff `P = Q`
- *Monotonic in α*: `α₁ ≤ α₂ ⇒ D_{α₁}(P‖Q) ≤ D_{α₂}(P‖Q)` (van Erven & Harremoës 2014)
- *Asymmetric in general*

## Starting weight preset
```python
"renyi_div.enabled": "true",
"renyi_div.ranking_weight": "0.0",
"renyi_div.alpha": "0.5",
"renyi_div.log_base": "2",
"renyi_div.smoothing_lambda": "0.4",
```

## C++ implementation
- File: `backend/extensions/renyi_divergence.cpp`
- Entry: `double renyi_divergence(const float* p, const float* q, int vocab_size, double alpha)`
- Complexity: O(|V|) — single pass with two `pow()` calls per cell
- Thread-safety: pure function on input slice
- Builds via pybind11; uses `std::pow` with vectorised SIMD path; double accumulator

## Python fallback
`backend/apps/pipeline/services/renyi_divergence.py::compute_renyi` using `(np.power(p, alpha) * np.power(q, 1 - alpha)).sum()` then log.

## Benchmark plan

| Size | |V| | C++ target | Python target |
|---|---|---|---|
| Small | 5,000 | 0.15 ms | 3.5 ms |
| Medium | 50,000 | 1.2 ms | 30 ms |
| Large | 500,000 | 12 ms | 290 ms |

## Diagnostics
- Rényi value rendered as "Rényi (α=0.5): 0.51 bits"
- Sum of `P^α · Q^(1−α)` shown
- C++/Python badge
- Debug fields: `alpha`, `vocab_size`, `inner_sum`, `log_base`, `chosen_special_case` (if α maps to KL/Hellinger/χ²)

## Edge cases & neutral fallback
- `α = 1` ⇒ formula degenerates (`1/(α-1)` undefined); fall back to FR-181 KL with diagnostic note
- `α ≤ 0` ⇒ reject as invalid; raise ValueError
- `Q(x) = 0` and `α > 1` ⇒ `Q(x)^(1−α) → ∞`; require smoothing on `Q` first
- `P(x) = 0` and `α < 1` ⇒ `P(x)^α = 0`; harmless
- Distributions don't sum to 1 ⇒ renormalise; warn

## Minimum-data threshold
Need both distributions based on at least 50 tokens of evidence each, and `α ∈ (0, 1) ∪ (1, 100]` before signal contributes; otherwise neutral 0.5.

## Budget
Disk: 0 · RAM: ~2 MB per LM at |V|=500k

## Scope boundary vs existing signals
Distinct from `fr181-kl-divergence-source-destination` (the `α=1` limit) and `fr182-jensen-shannon-divergence` (symmetric, not α-parameterised). Distinct from `fr184-hellinger-distance` (which corresponds to `α=1/2` here but is reported as a true metric, not a divergence). Rényi is the *parametric family*; the others are special cases.

## Test plan bullets
- Unit: `α=0.5` matches Bhattacharyya identity within 1e-6
- Unit: `α → 1` (e.g., 0.99) matches `D_KL` within 0.01
- Unit: `α = 2` matches `log(Σ P²/Q)` within 1e-6
- Identity: `D_α ≥ 0` for any α ∈ (0,1)∪(1,∞)
- Monotonicity: `D_{0.5} ≤ D_{1.0} ≤ D_{2.0}` on 100 random LM pairs
- Parity: C++ vs Python within 1e-6 on 500 pairs at α ∈ {0.5, 1.5, 2.0}
- Integration: deterministic across runs
- Regression: top-50 ranking unchanged when weight = 0.0
