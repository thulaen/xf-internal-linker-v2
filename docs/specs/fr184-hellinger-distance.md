# FR-184 — Hellinger Distance

## Overview
Hellinger distance is a *true metric* on probability distributions, bounded in `[0, 1]`, symmetric, and computable from the square roots of probabilities. Unlike KL it is always finite and obeys the triangle inequality. Hellinger has special status in statistics — it is the natural geometry on the simplex of probability distributions and underlies Le Cam's lower bounds for hypothesis testing. For an internal-linker, Hellinger gives a clean, bounded host-destination similarity that sits between cosine (vector geometry) and JS divergence (information theory). Complements `fr181-kl-divergence-source-destination`, `fr182-jensen-shannon-divergence`, and `fr183-renyi-divergence` (α=1/2 special case).

## Academic source
Hellinger, E. "Neue Begründung der Theorie quadratischer Formen von unendlichvielen Veränderlichen." *Journal für die reine und angewandte Mathematik*, 136, pp. 210–271, 1909. DOI: `10.1515/crll.1909.136.210`. Modern statistical treatment: Le Cam, L. *Asymptotic Methods in Statistical Decision Theory*, Springer, 1986, ISBN 978-0-387-96307-5.

## Formula
From Hellinger (1909) — discrete Hellinger distance between distributions `P` and `Q` over a finite support:

```
H(P, Q) = (1 / √2) · √( Σ_{x ∈ X} ( √P(x) − √Q(x) )² )
```

Equivalent forms:

```
H(P, Q)² = 1 − Σ_{x} √( P(x) · Q(x) )                       (1 − Bhattacharyya coefficient)
H(P, Q)² = (1/2) · Σ_{x} ( √P(x) − √Q(x) )²
```

Properties:
- *Bounded*: `0 ≤ H(P, Q) ≤ 1`
- *Symmetric*: `H(P, Q) = H(Q, P)`
- *Metric*: `H(P, Q) ≤ H(P, R) + H(R, Q)` (triangle inequality)
- `H(P, Q) = 0` ⟺ `P = Q`
- `H(P, Q) = 1` ⟺ disjoint supports

Relation to Bhattacharyya distance `B(P, Q) = −log Σ √(PQ)`:

```
H(P, Q)² = 1 − exp( −B(P, Q) )
```

## Starting weight preset
```python
"hellinger.enabled": "true",
"hellinger.ranking_weight": "0.0",
"hellinger.return_squared": "false",
"hellinger.smoothing_lambda": "0.0",
```

## C++ implementation
- File: `backend/extensions/hellinger.cpp`
- Entry: `double hellinger_distance(const float* p, const float* q, int vocab_size)`
- Complexity: O(|V|) — single pass; vectorised `sqrt` via SIMD intrinsics
- Thread-safety: pure function on input slice
- Builds via pybind11; double accumulator; one final `std::sqrt`

## Python fallback
`backend/apps/pipeline/services/hellinger.py::compute_hellinger` using `np.sqrt(0.5 * np.sum((np.sqrt(p) - np.sqrt(q))**2))`.

## Benchmark plan

| Size | |V| | C++ target | Python target |
|---|---|---|---|
| Small | 5,000 | 0.04 ms | 1.2 ms |
| Medium | 50,000 | 0.3 ms | 9 ms |
| Large | 500,000 | 3 ms | 90 ms |

## Diagnostics
- Hellinger value rendered as "Hellinger: 0.42 (similarity 0.58)"
- Bhattacharyya coefficient `Σ √(PQ)` shown alongside
- C++/Python badge
- Debug fields: `hellinger`, `bhattacharyya_coeff`, `vocab_size`, `return_squared`

## Edge cases & neutral fallback
- Identical distributions ⇒ H = 0
- Disjoint support ⇒ H = 1 (maximum)
- No need to smooth — Hellinger is well-defined for `P(x) = 0` or `Q(x) = 0` (`√0 = 0`)
- Distributions that don't sum to 1 ⇒ renormalise; warn
- Negative probabilities (numerical noise from rounding) ⇒ clip to 0

## Minimum-data threshold
Need both distributions based on at least 50 tokens of evidence each before signal contributes; otherwise neutral 0.5.

## Budget
Disk: 0 · RAM: ~2 MB per LM at |V|=500k; transient `√P` and `√Q` arrays same size

## Scope boundary vs existing signals
Distinct from `fr181-kl-divergence-source-destination` (asymmetric, unbounded, smoothing-sensitive) and `fr182-jensen-shannon-divergence` (symmetric, not a metric without √, requires `M`). Distinct from `fr183-renyi-divergence` α=1/2 case which is the related Bhattacharyya-form *log-divergence*, not a normalised metric. Hellinger is the *only true metric* in the divergence family.

## Test plan bullets
- Unit: identical distributions ⇒ H = 0
- Unit: disjoint support ⇒ H = 1
- Symmetry: `H(P,Q) = H(Q,P)` within 1e-6
- Triangle inequality: `H(P,R) ≤ H(P,Q) + H(Q,R)` on 100 random triples
- Boundedness: `0 ≤ H ≤ 1` for any input
- Identity: `H² = 1 − Σ √(PQ)` within 1e-6
- Parity: C++ vs Python within 1e-6 on 500 pairs
- Regression: top-50 ranking unchanged when weight = 0.0
