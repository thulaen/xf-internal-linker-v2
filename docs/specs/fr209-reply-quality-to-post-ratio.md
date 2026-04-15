# FR-209 - Reply Quality to Post Ratio

## Overview
A useful contributor doesn't just post replies — their replies tend to be acknowledged. The "Reply Quality Ratio" (RQR) is the fraction of an author's replies that earn at least one positive reaction (like / upvote / thank / mark-as-helpful). Agichtein et al. show that this signal is a strong predictor of high-quality answerers in community Q&A forums and survives controlling for total post count. Used as an additive author-trust boost.

## Academic source
**Agichtein, Eugene; Castillo, Carlos; Donato, Debora; Gionis, Aristides; Mishne, Gilad (2008).** "Finding High-Quality Content in Social Media." *Proceedings of the International Conference on Web Search and Data Mining (WSDM 2008)*, pp. 183-194. The reply-quality features in §4.2 — answer rating, total responses, and the ratio between them — form the basis for this signal. Agichtein et al. report the ratio carries the most discriminative power on Yahoo! Answers.

## Formula
For author `u` with replies `replies(u)`:
```
positive_replies(u) = | { r ∈ replies(u) : likes(r) ≥ 1 ∨ thanks(r) ≥ 1 ∨ marked_helpful(r) } |

RQR(u) = positive_replies(u) / max(1, |replies(u)|)             ∈ [0, 1]
```

Wilson lower-bound variant (more robust for small `|replies(u)|`, Wilson 1927):
```
RQR_wilson(u) = ( p + z²/(2n) − z·√(p(1−p)/n + z²/(4n²)) ) / (1 + z²/n)
```
where `p = positive_replies(u) / n`, `n = |replies(u)|`, `z = 1.96` (95% CI lower bound).

Final additive boost (already in `[0, 1]`):
```
rqr_boost(u) = RQR_wilson(u)
```

## Starting weight preset
```python
"rqr.enabled": "true",
"rqr.ranking_weight": "0.0",
"rqr.use_wilson_bound": "true",
"rqr.wilson_z": "1.96",
"rqr.positive_threshold_likes": "1",
"rqr.positive_threshold_thanks": "1",
```

## C++ implementation
- File: `backend/extensions/reply_quality_ratio.cpp`
- Entry: `void compute_rqr(const int* positive_counts, const int* total_counts, int n, double z, double* out_rqr);`
- Complexity: `O(n)` — single elementwise computation
- Thread-safety: pure function; per-author parallelism via OpenMP
- SIMD: `_mm256_sqrt_pd` for the Wilson bound term
- Builds against pybind11

## Python fallback
`backend/apps/pipeline/services/reply_quality_ratio.py::compute_rqr(...)` — `numpy` vectorised over the per-author counts.

## Benchmark plan
| Authors | C++ target | Python target |
|---|---|---|
| 1 K | < 0.1 ms | < 1 ms |
| 100 K | < 5 ms | < 50 ms |
| 10 M | < 500 ms | < 5 s |

## Diagnostics
- Per-author `positive_replies`, `total_replies`, raw `RQR`, and `RQR_wilson`
- Distribution of `RQR_wilson` across population
- Top-10 highest-RQR authors with `≥ 50` replies
- Whether Wilson bound was applied
- C++ vs Python badge

## Edge cases & neutral fallback
- Author with 0 replies → neutral `0.5`, flag `no_replies`
- Author with 1 reply, 1 positive → raw `RQR = 1.0` but `RQR_wilson ≈ 0.21` (correctly conservative)
- Author with 1 reply, 0 positive → raw `RQR = 0.0` but `RQR_wilson ≈ 0.0`
- All replies positive AND `n = 100` → `RQR_wilson ≈ 0.964` (very high confidence)
- NaN / Inf → `0.5`, flag `nan_clamped`

## Minimum-data threshold
`≥ 5` replies per author before raw `RQR` is trusted (Wilson handles smaller `n` correctly but still emits flag `low_sample` for `n < 5`).

## Budget
Disk: <1 MB  ·  RAM: <80 MB at 10 M authors (per-author int + double)

## Scope boundary vs existing signals
FR-209 does NOT overlap with FR-204 author H-index (impact-of-original-posts; FR-209 is reply quality only) or FR-208 mod endorsement (mod-only signal; FR-209 counts any positive reaction). It is also distinct from FR-013 feedback-driven explore-exploit reranking (which acts on suggestion clicks, not on author replies).

## Test plan bullets
- unit tests: 100 replies / 90 positive → `RQR_wilson ≈ 0.823`; 5 replies / 4 positive → `RQR_wilson ≈ 0.376`
- parity test: C++ vs Python `RQR_wilson` within `1e-6`
- Wilson-bound test: increasing `n` with the same `p` strictly increases `RQR_wilson`
- monotonicity test: adding a positive reply can only increase `RQR_wilson`
- integration test: ranking unchanged when `ranking_weight = 0.0`
- threshold test: changing `positive_threshold_likes` from `1` to `3` strictly decreases `positive_replies(u)` for any author
