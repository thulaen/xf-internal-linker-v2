# FR-126 — IA-Select Diversification

## Overview
The current ranker can return ten suggestions that are all near-duplicates of each other (ten threads about the same iPhone model, ten reviews of the same camera). Operators want a slate that *covers different aspects* of the host topic. IA-Select (Intent-Aware Select) is the foundational diversification algorithm: it greedily picks the next suggestion that maximises marginal aspect coverage given an aspect distribution `P(c|q)`. On a forum, aspects are sub-topics (price, performance, alternatives, troubleshooting). Complements FR-015 final-slate diversity reranking because FR-015 uses generic dissimilarity; IA-Select uses an explicit aspect-probability model from the host page's classified sub-topics.

## Academic source
**Agrawal, R., Gollapudi, S., Halverson, A., & Ieong, S. (2009).** "Diversifying Search Results." *Proceedings of the 2nd ACM International Conference on Web Search and Data Mining (WSDM 2009)*, Barcelona, Spain, pages 5-14. DOI: `10.1145/1498759.1498766`.

## Formula
From Agrawal et al. (2009), Eq. 1 (the IA-Select objective) and Algorithm 1 (greedy maximisation):

```
U(S | q) = Σ_{c ∈ C}  P(c | q) · ( 1 - Π_{d ∈ S} (1 - V(d | q, c)) )       (Eq. 1)

Greedy selection (Alg. 1):
    S ← ∅
    for k = 1..K:
        d* ← argmax_{d ∉ S}  Σ_{c}  U(c) · V(d | q, c)
        where U(c) ← U(c) · (1 - V(d* | q, c))    after each pick
              U(c) initialised to P(c | q)
        S ← S ∪ {d*}

Where:
    q              = host page (the "query")
    C              = set of aspects/sub-topics
    P(c | q)       ∈ [0, 1], aspect probability distribution, Σ_c P(c|q) = 1
    V(d | q, c)    ∈ [0, 1], probability that document d satisfies aspect c for query q
    S              = current selected slate
    K              = target slate size (e.g. 10 suggestions)
    1 - Π(1 - V)   = "at least one of the picked docs covers c" probability
```

The greedy algorithm achieves a `(1 - 1/e) ≈ 0.63` approximation of the NP-hard optimum (paper Theorem 2).

## Starting weight preset
```python
"ia_select.enabled": "true",
"ia_select.ranking_weight": "0.0",
"ia_select.aspect_source": "host_classified_topics",
"ia_select.satisfaction_proxy": "semantic_similarity",
"ia_select.target_slate_size": "10",
```

## C++ implementation
- File: `backend/extensions/ia_select.cpp`
- Entry: `std::vector<int> ia_select_pick(const float* aspect_probs, int n_aspects, const float* satisfaction_matrix, int n_candidates, int target_k)` where `satisfaction_matrix` is row-major shape `[n_candidates × n_aspects]`
- Complexity: O(K · n · |C|) for K picks over n candidates and |C| aspects — K = 10, n ≈ 200, |C| ≈ 10 → 20,000 ops per host
- Thread-safety: stateless; SIMD-friendly inner product over `|C|` aspects (AVX2 can do 8 float multiplies per cycle)
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/ia_select.py::ia_select_pick` — pure NumPy implementation using `np.argmax` over `(satisfaction_matrix * U).sum(axis=1)`.

## Benchmark plan
| Candidates × aspects | Slate K | C++ target | Python target |
|---|---|---|---|
| small (50 × 5) | 5 | <0.05 ms | <0.5 ms |
| medium (500 × 20) | 10 | <0.5 ms | <8 ms |
| large (5000 × 50) | 20 | <8 ms | <120 ms |

## Diagnostics
- Per-position diversification log in suggestion detail UI (`ia_select_diagnostics.pick_log`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `aspect_distribution_p_c_given_q`, `satisfaction_per_aspect_per_pick`, `marginal_utility_per_pick`, `aspect_coverage_progression` (Σ U(c) trajectory)

## Edge cases & neutral fallback
- Aspect distribution `P(c|q)` is degenerate (one aspect with probability 1) → IA-Select reduces to plain top-K by `V(d|q,c*)` — emit a flag `degenerate_single_aspect`
- Zero candidates → return empty slate
- Satisfaction matrix all zeros → emit flag `no_satisfying_documents`, return original ranking
- NaN/Inf in `V(d|q,c)` → clamp to 0; emit flag

## Minimum-data threshold
At least 2 aspects with `P(c|q) > 0.05` AND at least `2 · K` candidates; otherwise skip diversification and return original ranking.

## Budget
Disk: <1 MB  ·  RAM: <20 MB for the satisfaction matrix at 5000 × 50 in float32

## Scope boundary vs existing signals
- **FR-015 final-slate diversity reranking**: FR-015 uses generic pairwise dissimilarity (e.g. MMR-style) without explicit aspect modelling; IA-Select uses an explicit `P(c|q)` aspect distribution.
- **FR-014 near-duplicate clustering**: FR-014 deduplicates near-identical destinations before ranking; IA-Select diversifies across aspects within the already-deduplicated candidate set.
- **FR-127 xQuAD**: xQuAD is the explicit aspect-aware diversification with a `λ` interpolation between relevance and aspect coverage; IA-Select has no `λ` (pure aspect coverage).
- **FR-128 PM2**: PM2 is proportional aspect representation (assigns *quotas* per aspect); IA-Select is greedy marginal-coverage maximisation.

## Test plan bullets
- correctness test: paper's Section 4.2 toy example (3 aspects, 5 documents) → IA-Select picks match Algorithm 1 trace exactly
- approximation-bound test: brute-force optimum on small (n=10, K=3) instances → IA-Select score ≥ (1 - 1/e) · OPT
- parity test: C++ vs Python within 1e-6
- aspect-collapse test: when `P(c|q)` is uniform, IA-Select reduces to set-cover greedy
- no-crash on adversarial input: zero candidates, single aspect, all-zero satisfaction matrix, NaN aspect probs
- integration test: `ranking_weight = 0.0` (i.e. diversification disabled) leaves ranking unchanged
- determinism: tie-breaking by lower candidate index → identical slate across runs
