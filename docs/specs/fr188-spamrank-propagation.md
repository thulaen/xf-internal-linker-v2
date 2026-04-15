# FR-188 — SpamRank Propagation

## Overview
SpamRank treats spamicity as a propagating quantity: pages that link to known spam pages absorb spam penalty, and that penalty flows backward through the inverse link graph. A forum thread that earns inbound links primarily from spammy hosts is itself suspect, even if the page text looks clean. Complements `fr187-host-trustrank` because TrustRank propagates positive seeds while SpamRank propagates negative seeds — operators want both.

## Academic source
Full citation: **Benczúr, A. A., Csalogány, K., Sarlós, T., & Uher, M. (2005).** "SpamRank — Fully automatic link spam detection." In *Proceedings of the 1st International Workshop on Adversarial Information Retrieval on the Web (AIRWeb)*, in conjunction with WebKDD/SIGKDD 2005, Chicago. Section 3.2 defines the spam propagation kernel.

## Formula
Benczúr et al. (2005), Section 3.2: spamicity propagates from a seed spam set `T` over inbound links, weighted by the source page's outdegree and a per-page bias term:

```
p(x) = Σ_{y ∈ N⁻(x)}  p(y) / |N⁺(y)|  · (1 + bias(x))

with seed condition
  p(x) = 1   for x ∈ T (known spam pages)

where
  N⁻(x)  = inbound link set of x
  N⁺(y)  = outbound link set of y
  bias(x) = Pearson-statistic deviation of x's PR distribution from the
            expected power-law (Section 3.1); typically in [0, 0.3]
```

Iterated to fixed point; final `p(x) ∈ [0, 1]` is the spamicity score.

## Starting weight preset
```python
"spamrank.enabled": "true",
"spamrank.ranking_weight": "0.0",
"spamrank.bias_max": "0.30",
"spamrank.max_iterations": "30",
"spamrank.seed_size": "500",
```

## C++ implementation
- File: `backend/extensions/spamrank.cpp`
- Entry: `std::vector<double> spamrank(const CSRGraph& host_graph, const std::vector<int>& spam_seeds, const std::vector<double>& bias, int max_iter)`
- Complexity: O(I · E) on host graph
- Thread-safety: read-only on input; single-threaded inner loop
- SIMD: AVX2 SpMV on transposed CSR
- Builds via pybind11; bias vector precomputed in Python and passed in

## Python fallback
`backend/apps/pipeline/services/spamrank.py::compute_spamrank` using `scipy.sparse` transpose and dampened propagation.

## Benchmark plan

| Size | Hosts | C++ target | Python target |
|---|---|---|---|
| Small | 100 | 0.7 ms | 35 ms |
| Medium | 5,000 | 40 ms | 2.0 s |
| Large | 100,000 | 1.0 s | 80 s |

## Diagnostics
- Per-host spamicity (e.g. "Spam: 0.04")
- Inverse score `1 − spamicity` used as ranker contribution
- C++/Python badge
- Fallback flag when seed set empty
- Debug fields: `n_spam_seeds`, `iterations_used`, `bias_min`, `bias_max`

## Edge cases & neutral fallback
- Empty spam seed set → neutral 0.5 for all hosts, fallback flag set
- Host on no inbound path from any seed → spamicity = 0
- Seed host receives `p(x) = 1` regardless of inbound flow
- Bias term clipped to `[0, 0.3]` to prevent runaway penalty

## Minimum-data threshold
At least 100 known spam seeds and ≥ 1,000 hosts in graph before signal contributes; otherwise fall back to neutral 0.5.

## Budget
Disk: 1.8 MB  ·  RAM: 12 MB per 100k hosts

## Scope boundary vs existing signals
Distinct from `fr187-host-trustrank` (positive seeds, forward propagation from trusted sources) and from `fr189-badrank-inverse-pagerank` (pure inverse-PR without bias term). SpamRank uniquely combines bias-weighted inverse propagation with seed spam pages.

## Test plan bullets
- Unit: chain spam→A→B returns monotonically decreasing spamicity
- Unit: clean host distant from any seed returns near-zero
- Parity: C++ vs Python on 5,000-host fixture within 1e-6
- Edge: empty seed set returns neutral 0.5 with fallback flag
- Edge: bias clipped at 0.30 ceiling
- Integration: `1 − spamicity` contributes additively when weight > 0
- Regression: ranking unchanged when weight = 0.0
