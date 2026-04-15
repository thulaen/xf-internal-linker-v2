# FR-210 - Cross-Thread Topic Consistency

## Overview
A specialist who reliably posts about a narrow set of topics is more trustworthy in *that* topic area than a generalist who posts about everything. Conversely, an author who shifts topics constantly looks more like a content-aggregator or a low-effort poster. Cross-Thread Topic Consistency (TC) measures how concentrated an author's topic distribution is relative to the global forum distribution. Used as an additive author-trust boost when the candidate's topic falls inside the author's expertise zone.

## Academic source
**Kleinberg, Jon and Wang, Xiao-Yu (2011).** "Modeling and Mining the Dynamics of Communication in Online Communities." *Proceedings of the Fifth International AAAI Conference on Weblogs and Social Media (ICWSM 2011)*. The topic-distribution divergence approach in §4 — using KL divergence between per-user and global LDA topic mixtures to identify topic-focused users — is the basis for this signal. See also Kleinberg's earlier "Bursty and Hierarchical Structure in Streams" (KDD 2002) for the LDA-on-streams setup.

## Formula
Let `θ_u(z)` = per-author posterior topic distribution (LDA inferred from author's posts), `θ_global(z)` = corpus-mean topic distribution. Topic Consistency:
```
TC(u) = 1 − D_KL(θ_u ‖ θ_global) / D_KL_max                 (Kleinberg & Wang Eq. 5)

D_KL(θ_u ‖ θ_global) = Σ_z  θ_u(z) · log( θ_u(z) / θ_global(z) )
D_KL_max = log K                              # max possible KL between distributions over K topics
```

Higher `TC(u)` = author's topic distribution is more concentrated → more specialist. Lower `TC(u)` = author covers all topics → generalist.

Topic-conditional boost (only boost if candidate's dominant topic is in author's expertise):
```
expertise_topics(u) = { z : θ_u(z) ≥ τ_expertise },       τ_expertise = 0.10

tc_boost(u, c) = TC(u)  if  argmax_z θ_c(z) ∈ expertise_topics(u)
              else 0.0
```

Final additive boost: `tc_boost(u, c) ∈ [0, 1]`.

## Starting weight preset
```python
"topic_consistency.enabled": "true",
"topic_consistency.ranking_weight": "0.0",
"topic_consistency.lda_topic_count": "100",
"topic_consistency.tau_expertise": "0.10",
"topic_consistency.dirichlet_alpha": "0.10",
"topic_consistency.lda_passes": "20",
"topic_consistency.smoothing_eps": "1e-9",
```

## C++ implementation
- File: `backend/extensions/topic_consistency.cpp`
- Entry: `void compute_tc(const double* theta_per_author, const double* theta_global, int n_authors, int K, double* out_tc);`
- Complexity: `O(n_authors · K)` for the KL aggregation
- Thread-safety: per-author KL parallelised via OpenMP
- LDA inference itself runs in Python (gensim); C++ consumes the cached `θ_u` matrices
- SIMD: `_mm256_log_pd` for the per-topic log term
- Builds against pybind11

## Python fallback
`backend/apps/pipeline/services/topic_consistency.py::compute_tc(...)` — uses `gensim.models.LdaModel` for inference and `numpy` for the KL.

## Benchmark plan
| Authors × topics | C++ target | Python target |
|---|---|---|
| 1 K × 100 | < 5 ms | < 50 ms |
| 100 K × 100 | < 500 ms | < 6 s |
| 1 M × 100 | < 5 s | < 60 s |

## Diagnostics
- Per-author `θ_u`, `D_KL`, `TC`, and `expertise_topics`
- Histogram of `TC` across population
- Per-candidate dominant topic and whether it intersects expertise
- LDA model checksum and topic-set version
- C++ vs Python badge

## Edge cases & neutral fallback
- Author with `< 5` posts → topic distribution unreliable, neutral `0.0`, flag `too_few_posts`
- LDA model not yet trained → neutral `0.0`, flag `lda_not_ready`
- Candidate dominant topic not in any author's expertise → `tc_boost = 0`
- Zero in `θ_global(z)` → smoothed by `eps = 1e-9` to avoid `log(0)`, flag `eps_smoothed`
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 5` posts per author AND LDA trained on `≥ 1000` documents before scores are trusted; below this returns neutral `0.0`.

## Budget
Disk: <10 MB (LDA model + θ-cache)  ·  RAM: <120 MB (LDA + per-author θ)

## Scope boundary vs existing signals
FR-210 does NOT overlap with FR-048 topical authority cluster density (which is *page-level*, not author-level) or FR-203 content farm detector (which uses a *low-quality* topic set, not a per-author topic distribution). It is also distinct from FR-204 author H-index (impact, no topic conditioning) — FR-210 only fires when the candidate's topic matches the author's expertise.

## Test plan bullets
- unit tests: author with all posts on topic 7 → `θ_u` = δ-spike → `TC ≈ 1.0`; uniform author → `TC ≈ 0`
- parity test: C++ vs Python `TC` within `1e-5`
- expertise gating test: `tc_boost` is `0` when candidate topic ∉ `expertise_topics(u)`
- monotonicity test: concentrating an author's topic distribution can only increase `TC`
- integration test: ranking unchanged when `ranking_weight = 0.0`
- LDA reload test: re-training LDA must not change relative `TC` ordering by more than `±10%`
