# FR-132 — Latent Diversity Model (LDM)

## Overview
xQuAD / IA-Select / PM2 (FR-126/127/128) need explicit aspects with known `P(c|q)` distributions. Often the aspect taxonomy is unavailable or expensive to maintain. The Latent Diversity Model uses a probabilistic latent topic model (LDA-style) to infer the aspect distribution automatically from a candidate pool, then runs aspect-aware diversification on the inferred latents. On a forum, this means we get aspect-aware diversification without ever asking operators to define aspects explicitly. Complements FR-127 because xQuAD requires explicit aspects from the host classification, while LDM infers them on-the-fly per host from the candidate pool's text — turning unsupervised latent topics into an explicit `P(c|q)` for downstream xQuAD-style picking.

## Academic source
**Ashkan, A., Clarke, C. L. A., Agichtein, E., & Guo, Q. (2015).** "Estimating Probabilistic Distributions over Latent Topics for Search Result Diversification." *Proceedings of the 24th ACM International on Conference on Information and Knowledge Management (CIKM 2015)*, Melbourne, Australia, pages 1843-1846. DOI: `10.1145/2806416.2806613`.

(Underlying topic model: **Blei, D. M., Ng, A. Y., & Jordan, M. I. (2003).** "Latent Dirichlet Allocation." *Journal of Machine Learning Research*, 3, 993-1022.)

## Formula
From Ashkan et al. (2015), Eqs. 1-3 (the LDM derivation):

```
Step 1: Run LDA on the candidate pool's text to obtain
    θ_d ∈ Δ^{T-1}    = topic distribution per document d (length T)
    P(t | d) = θ_d[t]

Step 2: Estimate aspect prior from candidate pool (Eq. 1):
    P(t | q) = (1/|D_q|) · Σ_{d ∈ D_q}  rel(d, q) · P(t | d)
    where D_q = top-N candidates retrieved for q
          rel(d, q) ∈ [0, 1] = baseline relevance of d to q
    Then renormalise: Σ_t P(t | q) = 1

Step 3: Diversification objective (Eq. 3, an xQuAD-style aspect-aware reranking):
    score_LDM(d, q, S) = (1 - λ) · rel(d, q)
                       + λ · Σ_{t=1}^{T}  P(t | q) · P(t | d) · Π_{d_j ∈ S} (1 - P(t | d_j))

Greedy selection:
    d* ← argmax_{d ∉ S}  score_LDM(d, q, S)
    S ← S ∪ {d*}

Where:
    T            = number of LDA topics (paper experiments T = 50, 100, 200)
    P(t | d)     = topic membership of d (from LDA inference)
    P(t | q)     = inferred aspect prior for q (Eq. 1)
    Π (1 - P(t|d_j)) = "topic t still uncovered by S" residual
    λ ∈ [0,1]    = relevance-vs-diversity trade-off (paper default 0.5)
```

The Eq. 1 "aspect prior" is the key contribution: it lets xQuAD machinery work without an explicit aspect taxonomy.

## Starting weight preset
```python
"ldm.enabled": "true",
"ldm.ranking_weight": "0.0",
"ldm.lda_topics_T": "100",
"ldm.lambda_diversity": "0.5",
"ldm.candidate_pool_size_N": "200",
"ldm.target_slate_size": "10",
```

## C++ implementation
- File: `backend/extensions/ldm.cpp`
- Entry: `std::vector<int> ldm_pick(const float* topic_dist_matrix, const float* relevance, int n_candidates, int n_topics, int target_k, float lambda)` (LDA inference happens in Python; C++ does only the diversification step)
- Complexity: O(K · n · T) for the diversification picks; LDA training/inference is offline and not in the hot path
- Thread-safety: stateless; SIMD over the T-dimensional topic vectors using AVX2
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/ldm.py::ldm_pick` — uses `gensim.models.LdaMulticore` for topic inference (cached, refreshed weekly), NumPy for the diversification step.

## Benchmark plan
| Candidates × topics | Slate K | C++ target | Python target |
|---|---|---|---|
| small (50 × 50) | 5 | <0.1 ms | <1.5 ms |
| medium (500 × 100) | 10 | <2 ms | <30 ms |
| large (5000 × 200) | 20 | <80 ms | <2 s |

(Note: LDA inference itself is offline, ~minutes; the 200-topic per-host inference at suggestion time is ~5 ms in `gensim` for 200 candidates.)

## Diagnostics
- Inferred aspect prior `P(t|q)` in suggestion detail UI (top-10 topics with weights)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `inferred_aspect_prior_top10`, `topic_coverage_progression`, `lda_model_version`, `lambda_used`, `effective_aspect_count` (number of topics with `P(t|q) > 0.05`)

## Edge cases & neutral fallback
- LDA model not yet trained → flag `lda_model_unavailable`, skip diversification
- Inferred prior is degenerate (one topic with prob > 0.95) → flag, fall back to xQuAD-equivalent on the dominant aspect
- Zero candidates → empty slate
- All-zero topic distributions (LDA returned empty inference) → flag, return relevance-only ranking
- NaN/Inf in topic matrix → clamp; flag

## Minimum-data threshold
LDA model trained on ≥ 1000 documents AND candidate pool size ≥ `K + 5`; otherwise skip.

## Budget
Disk: <50 MB for the LDA model file (T=100 topics × vocabulary ~ 50K terms × float32)  ·  RAM: <30 MB at n=5000, T=200 (topic distribution matrix in float32)

## Scope boundary vs existing signals
- **FR-127 xQuAD**: requires explicit aspects from host classification; LDM infers aspects from candidate pool text via LDA. Otherwise the diversification objective (Eq. 3) is the same family.
- **FR-126 IA-Select / FR-128 PM2**: also require explicit aspects.
- **FR-129 DPP**: aspect-free, uses similarity kernel; LDM uses an explicit *inferred* aspect distribution.
- **FR-130 submodular coverage**: cluster-based diversity; LDM uses soft probabilistic topic membership rather than hard cluster assignment.

## Test plan bullets
- correctness test: paper's Section 4.2 toy example (3 candidates, T=2 topics) → LDM picks match Eq. 3 trace within 1e-6
- aspect-prior test: when one document dominates the candidate pool (rel weight = 0.9), the inferred prior P(t|q) skews toward that document's topic distribution
- xquad-equivalence test: when aspects are provided externally (not inferred), LDM with `P(t|q) = external_aspects` produces identical ordering to FR-127 xQuAD
- λ-sweep test: λ=0 produces relevance-only ordering; λ=1 produces pure topic-coverage ordering
- parity test: C++ vs Python diversification step within 1e-6 (LDA inference itself is non-deterministic across runs unless seeded; we seed with `random_state=42`)
- no-crash on adversarial input: zero candidates, single-topic prior, NaN topic matrix
- integration test: `ranking_weight = 0.0` leaves ranking unchanged
- determinism: with seeded LDA + tie-breaking by lower index → identical slate across runs
