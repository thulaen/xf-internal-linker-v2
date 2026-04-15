# FR-127 — xQuAD Aspect Diversification

## Overview
IA-Select (FR-126) maximises pure aspect coverage but can hurt relevance by picking a marginally-on-aspect document over a strongly-relevant one. xQuAD (eXplicit Query Aspect Diversification) interpolates between relevance and diversity via a single `λ` parameter, giving operators a tunable knob. On a forum this means operators can favour relevance for navigation links and favour diversity for "related threads" sidebars. Complements FR-126 because xQuAD adds the relevance-vs-diversity trade-off that pure IA-Select lacks.

## Academic source
**Santos, R. L. T., Macdonald, C., & Ounis, I. (2010).** "Exploiting Query Reformulations for Web Search Result Diversification." *Proceedings of the 19th International World Wide Web Conference (WWW 2010)*, Raleigh, NC, pages 881-890. DOI: `10.1145/1772690.1772780`.

## Formula
From Santos et al. (2010), Eq. 6 (the xQuAD objective) and Eq. 7 (greedy selection):

```
score_xQuAD(d, q, S) = (1 - λ) · rel(d, q)
                     + λ · Σ_{q_i ∈ Q'}  P(q_i | q) · rel(d, q_i) · Π_{d_j ∈ S} (1 - rel(d_j, q_i))
                                                                                   (Eq. 6)

Greedy selection (Eq. 7):
    d* ← argmax_{d ∉ S}  score_xQuAD(d, q, S)
    S ← S ∪ {d*}

Where:
    q                  = original query (host page)
    Q' = {q_1,...,q_m} = aspects (query reformulations / sub-topics of q)
    P(q_i | q)         ∈ [0, 1], aspect probability, Σ_i P(q_i|q) = 1
    rel(d, q)          ∈ [0, 1], relevance of d to original query q
    rel(d, q_i)        ∈ [0, 1], relevance of d to aspect q_i
    Π (1 - rel)        = aspect-coverage residual ("how uncovered is q_i still after S?")
    λ ∈ [0, 1]         = trade-off parameter (paper default 0.5)
    S                  = current selected slate
```

The first term `(1-λ)·rel(d,q)` rewards relevance; the second term rewards documents that cover aspects not yet covered by the slate. The greedy algorithm achieves the same `(1 - 1/e)` bound as IA-Select.

## Starting weight preset
```python
"xquad.enabled": "true",
"xquad.ranking_weight": "0.0",
"xquad.lambda_diversity": "0.5",
"xquad.aspect_source": "host_classified_topics",
"xquad.target_slate_size": "10",
```

## C++ implementation
- File: `backend/extensions/xquad.cpp`
- Entry: `std::vector<int> xquad_pick(const float* relevance, const float* aspect_probs, int n_aspects, const float* aspect_relevance_matrix, int n_candidates, int target_k, float lambda)`
- Complexity: O(K · n · |Q'|) — same as IA-Select
- Thread-safety: stateless; SIMD inner product over aspects with `_mm256_fmadd_ps`
- Maintains per-aspect residual `Π(1-rel)` incrementally to avoid recomputing the product each iteration (multiply by `(1 - rel(d*, q_i))` after each pick)
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/xquad.py::xquad_pick` — NumPy implementation with vectorised aspect-residual updates.

## Benchmark plan
| Candidates × aspects | Slate K | C++ target | Python target |
|---|---|---|---|
| small (50 × 5) | 5 | <0.05 ms | <0.5 ms |
| medium (500 × 20) | 10 | <0.5 ms | <8 ms |
| large (5000 × 50) | 20 | <8 ms | <120 ms |

## Diagnostics
- Per-position diversification log in suggestion detail UI (`xquad_diagnostics.pick_log`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `lambda_used`, `relevance_per_pick`, `diversity_per_pick`, `aspect_residual_progression`, `aspect_coverage_at_k`

## Edge cases & neutral fallback
- `λ = 0` → degenerates to pure relevance ranking (FR-127 disabled effectively); flag and short-circuit
- `λ = 1` → degenerates to pure aspect coverage (equivalent to IA-Select with relevance=1); flag
- Zero candidates → empty slate
- All aspect probabilities zero → fall back to relevance-only; flag
- NaN/Inf in matrices → clamp; flag

## Minimum-data threshold
At least 2 aspects with `P(q_i|q) > 0.05` AND at least `2 · K` candidates; otherwise skip and return original ranking.

## Budget
Disk: <1 MB  ·  RAM: <25 MB at 5000 × 50 aspect-relevance matrix in float32 + relevance vector + residual vector

## Scope boundary vs existing signals
- **FR-126 IA-Select**: pure aspect-coverage maximisation, no `λ`. xQuAD has the explicit relevance-vs-diversity trade-off.
- **FR-128 PM2**: PM2 enforces *proportional* aspect representation via quota allocation; xQuAD has no quotas.
- **FR-129 DPP**: DPP uses determinant-based subset sampling for diversity; xQuAD uses greedy marginal aspect coverage.
- **FR-015 final-slate diversity reranking**: generic pairwise dissimilarity; xQuAD uses explicit aspect modelling.

## Test plan bullets
- correctness test: paper's Table 2 example (5 docs, 3 aspects, λ=0.5) → xQuAD picks match Algorithm 1 trace exactly
- λ-sweep test: λ=0 produces relevance-only ordering; λ=1 produces IA-Select-equivalent ordering; intermediate λ blends predictably (Spearman ρ vs relevance decreases monotonically as λ increases from 0 to 1)
- approximation-bound test: brute-force optimum on small instances → xQuAD score ≥ (1 - 1/e) · OPT
- parity test: C++ vs Python within 1e-6
- no-crash on adversarial input: λ outside [0,1] (clamp), zero candidates, single aspect, NaN inputs
- integration test: `ranking_weight = 0.0` leaves ranking unchanged
- determinism: tie-breaking by lower index → identical slate across runs
