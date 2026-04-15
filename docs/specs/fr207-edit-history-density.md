# FR-207 - Edit-History Density

## Overview
Authors who frequently revise their own posts — to correct typos, add citations, expand answers — exhibit higher craft and care than authors who only ever post-and-forget. But edits can also indicate vandalism or content removal; high *revert rate* on someone's edits is a negative. Adler & de Alfaro's content-driven reputation system on Wikipedia formalises this with edit-density and revert-survival metrics. This signal computes a per-author Edit-History Density (EHD) score with a revert penalty. Used as an additive author-trust boost.

## Academic source
**Adler, B. T. and de Alfaro, L. (2007).** "A Content-Driven Reputation System for the Wikipedia." *Proceedings of the 16th International Conference on World Wide Web (WWW 2007)*, pp. 261-270. DOI: `10.1145/1242572.1242608`. The edit-density and survival-based reputation in §4 are the basis for this signal.

## Formula
For author `u` with posts `posts(u)` and edits `edits(u)`:
```
EHD(u) = edits(u) / (posts(u) + ε)                    ε = 1.0  (Laplace smoothing)
```

Adler & de Alfaro's revert penalty:
```
revert_rate(u) = reverts(u) / max(1, edits(u))
EHD_penalised(u) = EHD(u) − γ · revert_rate(u),       γ = 0.50
```

Survival-weighted variant (Adler & de Alfaro Eq. 6):
```
EHD_survival(u) = (1 / |edits(u)|) · Σ_{e ∈ edits(u)}  surviving_chars_after_T(e) / total_chars(e)
```
with `T = 10` follow-up edits or 30 days, whichever comes first.

Final additive boost via squashing to `[0, 1]`:
```
ehd_boost(u) = sigmoid(λ · (EHD_penalised(u) − μ)),  λ = 1.5, μ = 0.30
```

## Starting weight preset
```python
"edit_history_density.enabled": "true",
"edit_history_density.ranking_weight": "0.0",
"edit_history_density.epsilon": "1.0",
"edit_history_density.gamma_revert": "0.50",
"edit_history_density.use_survival_weighting": "true",
"edit_history_density.lambda_sigmoid": "1.5",
"edit_history_density.mu_decision": "0.30",
"edit_history_density.survival_followup_T": "10",
"edit_history_density.survival_window_days": "30",
```

## C++ implementation
- File: `backend/extensions/edit_history_density.cpp`
- Entry: `void compute_ehd(const AuthorEditStats* stats, int n, double gamma, double lambda, double mu, double* out_boost);`
- Complexity: `O(n)` for the basic ratio, `O(n · k_edits)` for the survival variant with `k_edits` average edits per author
- Thread-safety: per-author computation parallelised via OpenMP
- Survival window built from a sorted edit timeline (binary-searched)
- Builds against pybind11

## Python fallback
`backend/apps/pipeline/services/edit_history_density.py::compute_ehd(...)` — pandas group-by over the edit log.

## Benchmark plan
| Authors / edits | C++ target | Python target |
|---|---|---|
| 1 K / 10 K | < 5 ms | < 100 ms |
| 10 K / 200 K | < 100 ms | < 2 s |
| 100 K / 5 M | < 3 s | < 60 s |

## Diagnostics
- Per-author `EHD`, `revert_rate`, `EHD_penalised`, `ehd_boost`
- Top-10 highest-density authors
- Histogram of `EHD` and `revert_rate` across population
- Whether survival weighting was enabled
- C++ vs Python badge

## Edge cases & neutral fallback
- Author with 0 posts → neutral `0.5` (sigmoid centre), flag `no_posts`
- Author with 0 edits → `EHD = 0`, `boost = sigmoid(−λ·μ)` (small negative)
- Edit log missing → neutral `0.5`, flag `no_edit_log`
- Survival window edits not yet matured → exclude from survival average, flag `partial_survival_data`
- NaN / Inf → `0.5`, flag `nan_clamped`

## Minimum-data threshold
`≥ 5` posts AND `≥ 10` total edits across the corpus before per-author scores are trusted; below this returns neutral `0.5`.

## Budget
Disk: <2 MB  ·  RAM: <60 MB at 100 K authors with full edit timelines

## Scope boundary vs existing signals
FR-207 does NOT overlap with FR-204 author H-index (impact, not maintenance) or FR-205 co-authorship PageRank (graph, not edit). It is *complementary* to FR-208 mod endorsement (which depends on others' actions; FR-207 depends only on the author's own behaviour). It also does not overlap with FR-014 near-duplicate clustering (which acts on content, not on authors).

## Test plan bullets
- unit tests: 10 posts / 50 edits / 0 reverts → high `EHD` and high `boost`
- parity test: C++ vs Python within `1e-5` for both `EHD` and `boost`
- revert penalty test: same `EHD` with `revert_rate ∈ {0, 0.3, 0.7}` produces strict descending boost
- monotonicity test: adding a non-reverted edit can only increase `boost`
- integration test: ranking unchanged when `ranking_weight = 0.0`
- survival test: edit that survives `T = 10` follow-ups gets full credit; one reverted within `T = 1` gets near-zero credit
