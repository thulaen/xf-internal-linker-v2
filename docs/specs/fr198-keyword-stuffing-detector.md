# FR-198 - Keyword Stuffing Detector

## Overview
Keyword stuffing is when a page repeats target keywords far more often than natural prose would. Modern variants include hidden-text stuffing, footer keyword lists, and ALT-attribute spam. This signal compares the term distribution of a page against a corpus-wide *natural-text baseline* using Kullback-Leibler divergence; pages that diverge sharply on a small handful of high-frequency terms are flagged. Used as a multiplicative penalty in the ranker.

## Academic source
**Ntoulas, Alexandros; Najork, Marc; Manasse, Mark; Fetterly, Dennis (2006).** "Detecting Spam Web Pages through Content Analysis." *Proceedings of the 15th International Conference on World Wide Web (WWW 2006)*, pp. 83-92. DOI: `10.1145/1135777.1135794`. The KL-divergence-based stuffing score and the corpus-baseline construction in §4 are the basis for this signal.

## Formula
Let `P_d(t)` = empirical term distribution of document `d` and `Q(t)` = corpus baseline distribution (smoothed Dirichlet over the entire forum). Define:

```
KL(P_d ‖ Q) = Σ_t  P_d(t) · log( P_d(t) / Q(t) )           (Eq. 6, Ntoulas et al.)

stuff_score(d) = KL(P_d ‖ Q) / log(|V_d|)                  (length-normalised)

stuff_penalty(d) = sigmoid( α · (stuff_score(d) − τ) )      α = 6.0, τ = 0.30
                = 1 / (1 + exp(−α · (stuff_score(d) − τ)))
```

Where:
- `|V_d|` = number of unique tokens in `d`
- `α` = sigmoid sharpness (paper §4.2 uses `6.0`)
- `τ` = decision threshold (paper §4.2 uses `0.30` after recall@90% calibration)

Top-`k` "stuff terms" are the `t` that maximise the per-term KL contribution `P_d(t) · log(P_d(t)/Q(t))`.

## Starting weight preset
```python
"keyword_stuffing.enabled": "true",
"keyword_stuffing.ranking_weight": "0.0",
"keyword_stuffing.alpha": "6.0",
"keyword_stuffing.tau": "0.30",
"keyword_stuffing.dirichlet_mu": "2000",
"keyword_stuffing.top_k_stuff_terms": "5",
```

## C++ implementation
- File: `backend/extensions/keyword_stuffing.cpp`
- Entry: `double stuff_score(const uint32_t* term_ids, const uint32_t* tf, int n, const CorpusBaseline& base);`
- Complexity: `O(|V_d|)` after term-id sort
- Thread-safety: pure function (baseline passed by `const` ref)
- SIMD: `#pragma omp simd reduction(+:kl_sum)` over per-term log ratios
- Builds against pybind11

## Python fallback
`backend/apps/pipeline/services/keyword_stuffing.py::stuff_score(...)` — used when extension unavailable, also exposes the top-`k` stuff terms for diagnostics.

## Benchmark plan
| Documents | C++ target | Python target |
|---|---|---|
| 100 (1KB) | < 5 ms | < 50 ms |
| 1 K (1KB) | < 50 ms | < 500 ms |
| 10 K (1KB) | < 500 ms | < 5 s |

## Diagnostics
- Raw `stuff_score` per document
- `stuff_penalty` after sigmoid
- Top-`k` stuff terms with per-term KL contribution
- Whether Dirichlet smoothing was applied to a missing-from-baseline term
- C++ vs Python badge

## Edge cases & neutral fallback
- Document < 30 tokens → neutral `0.0`, flag `text_too_short`
- Empty corpus baseline → neutral `0.0`, flag `no_baseline`
- Term not in baseline → smoothed via Dirichlet `μ = 2000`
- All-uniform document (single repeated term) → score saturates at `KL = log(1/Q(t))`, flag `single_term`
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 30` tokens in document AND `≥ 100` documents in corpus baseline before the score is trusted; below this returns neutral `0.0`.

## Budget
Disk: <2 MB (compressed baseline)  ·  RAM: <30 MB (baseline term-id → P map)

## Scope boundary vs existing signals
FR-198 does NOT duplicate FR-008 phrase matching or FR-009 anchor vocabulary — those measure relevance, not anomaly. It is distinct from FR-054 boilerplate ratio (which is structural HTML, not term distribution) and from FR-039 entity salience (which uses NER, not raw terms).

## Test plan bullets
- unit tests: natural prose, all-same-term page, hidden text stuffing
- parity test: C++ vs Python KL within `1e-5`
- regression test: legitimate glossary pages (high term repetition by design) flagged via allow-list
- integration test: ranking unchanged when `ranking_weight = 0.0`
- corpus test: baseline rebuild monotonic — adding more docs cannot increase any single-page `stuff_score` by more than `5%`
- timing test: 10 K docs scored within 500 ms in C++
