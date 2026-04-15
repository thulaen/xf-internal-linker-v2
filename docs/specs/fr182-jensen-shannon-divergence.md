# FR-182 — Jensen-Shannon Divergence

## Overview
Jensen-Shannon (JS) divergence is the *symmetric, bounded* version of KL divergence. It compares each distribution to the average and averages the two KL values, yielding a value in `[0, log 2]` that satisfies `D_JS(P‖Q) = D_JS(Q‖P)` and whose square root is a true metric on probability distributions. For an internal-linker, JS gives a host-vs-destination similarity score that is direction-agnostic and well-bounded for ranking blends — unlike raw KL (FR-181). Foundational for clustering, retrieval-distance metrics, and recent generative-LM evaluation (FID, MAUVE).

## Academic source
Lin, J. "Divergence measures based on the Shannon entropy." *IEEE Transactions on Information Theory*, 37(1), pp. 145–151, 1991. DOI: `10.1109/18.61115`. Earlier reference for the symmetric construction: Endres, D. M. and Schindelin, J. E. "A new metric for probability distributions." *IEEE TIT* 49(7), 2003. DOI: `10.1109/TIT.2003.813506`.

## Formula
From Lin (1991), Eq. 4.1 — JS divergence is the average of two KLs against the mean distribution `M`:

```
D_JS(P ‖ Q) = (1/2) · D_KL(P ‖ M) + (1/2) · D_KL(Q ‖ M)

where
  M(x) = (P(x) + Q(x)) / 2
```

Properties:
- *Symmetric*: `D_JS(P‖Q) = D_JS(Q‖P)`
- *Bounded*: `0 ≤ D_JS(P‖Q) ≤ log 2`  (or `1` if log base 2)
- `D_JS(P‖Q) = 0` ⟺ `P = Q`
- *Square root is a metric* (Jensen-Shannon distance, Endres & Schindelin 2003)
- *Always finite* (no `+∞` problem from `Q(x)=0`, because `M(x) > 0` whenever either is positive)

For ranking, normalise to `[0, 1]`:

```
JS_norm(P, Q) = D_JS(P‖Q) / log 2
```

Convert to similarity via `1 - JS_norm`.

## Starting weight preset
```python
"js_div.enabled": "true",
"js_div.ranking_weight": "0.0",
"js_div.log_base": "2",
"js_div.return_distance": "false",
"js_div.smoothing_lambda": "0.4",
```

## C++ implementation
- File: `backend/extensions/js_divergence.cpp`
- Entry: `double js_divergence(const float* p, const float* q, int vocab_size)`
- Complexity: O(|V|) — single pass; computes `M(x)`, both KL terms, and accumulates
- Thread-safety: pure function on input slice; no shared state
- Builds via pybind11; SIMD for vectorised log; double accumulator

## Python fallback
`backend/apps/pipeline/services/js_divergence.py::compute_js` using NumPy: `m = 0.5*(p+q); 0.5*kl(p, m) + 0.5*kl(q, m)`.

## Benchmark plan

| Size | |V| | C++ target | Python target |
|---|---|---|---|
| Small | 5,000 | 0.1 ms | 3 ms |
| Medium | 50,000 | 0.8 ms | 24 ms |
| Large | 500,000 | 8 ms | 220 ms |

## Diagnostics
- JS value rendered as "JS: 0.32 bits (similarity 0.68)"
- Per-term KL contributions (both directions)
- C++/Python badge
- Debug fields: `js_value`, `kl_p_to_m`, `kl_q_to_m`, `js_distance`, `vocab_size`

## Edge cases & neutral fallback
- Identical distributions ⇒ JS = 0
- Maximally divergent (disjoint support) ⇒ JS = log 2 (= 1 in log₂)
- Zero in either P or Q on a position ⇒ harmless (`M > 0` guarantees finite JS)
- Distributions that don't sum to 1 ⇒ renormalise first; warn
- `return_distance = true` ⇒ return `√D_JS`, which *is* a metric (triangle inequality holds)

## Minimum-data threshold
Need both distributions based on at least 50 tokens of evidence each before signal contributes; otherwise neutral 0.5.

## Budget
Disk: 0 (computed on demand) · RAM: ~2 MB per LM at |V|=500k; transient `M` array same size

## Scope boundary vs existing signals
Distinct from `fr181-kl-divergence-source-destination` (asymmetric, unbounded, requires support-overlap) and `fr183-renyi-divergence` (α-family generalisation). Distinct from cosine-based semantic similarity. JS is the *bounded, symmetric, always-finite* divergence — the safest choice when feeding into a weighted ranking sum.

## Test plan bullets
- Unit: identical distributions ⇒ JS = 0
- Unit: disjoint support ⇒ JS = log 2 = 1.0 (in log₂)
- Symmetry: `D_JS(P‖Q) = D_JS(Q‖P)` within 1e-6
- Boundedness: `0 ≤ JS ≤ log 2` for any input
- Triangle inequality: `√JS` satisfies metric axioms within 1e-6 across 100 random triples
- Parity: C++ vs Python within 1e-6 on 500 pairs
- Integration: deterministic across runs given fixed inputs
- Regression: top-50 ranking unchanged when weight = 0.0
