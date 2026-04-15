# FR-181 — KL Divergence (Source ↔ Destination Language Models)

## Overview
Kullback-Leibler divergence measures how much information is lost when you approximate one probability distribution with another. Applied here, KL between a host paragraph's language model `P` and a candidate destination's language model `Q` quantifies whether the destination is *too narrow* (low KL = good fit) or *too broad / off-topic* (high KL = poor fit) relative to the host. Asymmetric: `D_KL(P‖Q) ≠ D_KL(Q‖P)` — the spec uses the source-to-destination direction by default. Foundational for FR-170 Clarity, FR-182 JS divergence, FR-183 Rényi divergence, and many neural-LM evaluation metrics.

## Academic source
Kullback, S. and Leibler, R. A. "On information and sufficiency." *The Annals of Mathematical Statistics*, 22(1), pp. 79–86, 1951. DOI: `10.1214/aoms/1177729694`. Textbook treatment: Cover, T. M. and Thomas, J. A. *Elements of Information Theory*, 2nd ed., Wiley, 2006, ISBN 978-0-471-24195-9.

## Formula
From Kullback & Leibler (1951), Eq. 2.1 — discrete KL divergence:

```
D_KL(P ‖ Q) = Σ_{x ∈ X} P(x) · log( P(x) / Q(x) )

with the convention
  0 · log(0/q)  = 0
  p · log(p/0)  = +∞     (P must be absolutely continuous w.r.t. Q)
```

Properties:
- `D_KL(P‖Q) ≥ 0` (Gibbs' inequality)
- `D_KL(P‖Q) = 0` ⟺ `P = Q` almost everywhere
- *Asymmetric*: `D_KL(P‖Q) ≠ D_KL(Q‖P)` in general
- *Not a metric*: triangle inequality fails

For the linker, `P` is the host paragraph LM and `Q` is the destination LM; both are smoothed (Jelinek-Mercer or Dirichlet) against the collection LM `P_C` to ensure `Q(x) > 0` wherever `P(x) > 0`.

## Starting weight preset
```python
"kl_div.enabled": "true",
"kl_div.ranking_weight": "0.0",
"kl_div.smoothing": "jelinek_mercer",
"kl_div.smoothing_lambda": "0.4",
"kl_div.log_base": "2",
"kl_div.direction": "source_to_dest",
```

## C++ implementation
- File: `backend/extensions/kl_divergence.cpp`
- Entry: `double kl_divergence(const float* p, const float* q, int vocab_size)`
- Complexity: O(|V|) — single pass; SIMD log via vectorised polynomial
- Thread-safety: pure function on input slice; no shared state
- Builds via pybind11; double accumulator for KL sum

## Python fallback
`backend/apps/pipeline/services/kl_divergence.py::compute_kl` using `(p * np.log2(p / q)).sum()` with `np.where(p > 0, ..., 0)` to enforce the `0·log 0 = 0` convention.

## Benchmark plan

| Size | |V| | C++ target | Python target |
|---|---|---|---|
| Small | 5,000 | 0.05 ms | 1.5 ms |
| Medium | 50,000 | 0.4 ms | 12 ms |
| Large | 500,000 | 4 ms | 110 ms |

## Diagnostics
- KL value rendered as "KL(host ‖ dest): 1.83 bits"
- Top-10 contributing terms (highest `P(x) · log(P(x)/Q(x))`)
- C++/Python badge
- Debug fields: `direction`, `smoothing_lambda`, `vocab_size`, `unsmoothed_zero_count_q`

## Edge cases & neutral fallback
- `P(x) > 0` and `Q(x) = 0` ⇒ `+∞` ⇒ apply Jelinek-Mercer or Dirichlet smoothing on `Q` first; verify no zero in support after smoothing
- `P(x) = 0` ⇒ that term contributes 0 (`0·log 0 = 0`)
- Distributions that do not sum to 1 ⇒ renormalise; emit warning
- Asymmetry: log direction (`source→dest` vs `dest→source`); document choice; both directions can be exposed
- Negative KL is impossible — if observed, numerical bug; assert and fall back

## Minimum-data threshold
Need both LMs based on at least 50 tokens of evidence each before signal contributes; otherwise neutral 0.5.

## Budget
Disk: 0 (LMs computed on demand) · RAM: ~2 MB per LM at |V|=500k

## Scope boundary vs existing signals
Distinct from `fr182-jensen-shannon-divergence` (symmetric, bounded, smoothed) and `fr183-renyi-divergence` (α-family generalisation). Distinct from `fr170-query-clarity-score` (KL of query LM vs collection LM, with retrieval mixture). Distinct from `fr011-field-aware-relevance-scoring` (per-document BM25). KL is the foundational asymmetric divergence on which many other signals are built.

## Test plan bullets
- Unit: identical distributions ⇒ KL = 0
- Unit: known small example matches manual computation within 1e-6
- Identity: `D_KL(P‖Q) ≥ 0` for any P, Q on shared support
- Parity: C++ vs Python within 1e-6 on 500 LM pairs
- Edge: smoothed `Q` never contains zeros after JM smoothing
- Edge: `P` distribution that sums to 0.99 (rounding) is renormalised
- Integration: deterministic across runs given fixed seed and smoothing
- Regression: top-50 ranking unchanged when weight = 0.0
