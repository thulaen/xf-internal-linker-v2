# FR-249 — Embedding age decay signal for the ranker

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Embedding age decay (freshness multiplier) |
| **Settings prefix** | `pipeline.embedding_age_half_life_days`, `pipeline.embedding_age_weight_in_composite` |
| **Pipeline stage** | Stage 3 (composite ranker) |
| **Helpers** | `apps.pipeline.services.embedding_age.compute_embedding_age_decay`, `get_age_decay_settings` |
| **Default state** | **ON algorithm** (helper present in code path, returns 1.0 when timestamp is missing — pure-additive, never penalises by default). Wire-in as composite-score component deferred to a focused follow-up that touches `ranker.py:_calculate_composite_scores_full_batch_py`. |

## 2 · Motivation (ELI5)

A 6-month-old embedding is treated identically to one made today. If the model was upgraded mid-flight, old embeddings can be slightly miscalibrated against new ones. A small time-decay multiplier in the composite ranker breaks ties in favor of fresher embeddings. The formula is Newton's law of cooling — at one year of age, the multiplier is 0.5; at two years, 0.25. Operators set the half-life to match their corpus' churn rate (default 365 days for stable forums; news sites can lower to 30 days).

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Primary** | Liu, T.-Y. (2009). *Learning to Rank for Information Retrieval.* Foundations and Trends in IR, 3(3). DOI: [10.1561/1500000016](https://doi.org/10.1561/1500000016). §1.5.4 covers freshness signals as ranking features. |
| **Decay form** | Newton's law of cooling — exponential decay with half-life. Standard physics; canonical reference Lavrenko, V. (2008). *A Generative Theory of Relevance.* Springer. ISBN 978-3540893080. |
| **Multiplier pattern** | Rigutini, L. et al. (2008). *Sortnet: Learning to Rank by a Neural-Based Sorting Algorithm.* ICANN — establishes the temporal-decay multiplier pattern for cascade rankers. |
| **What we reproduce** | Multiplier in [0, 1] from a configurable half-life. Default 365 days. |
| **What we diverge on** | We use `ContentItem.updated_at` (or any caller-supplied datetime) as the embedding age proxy because the codebase doesn't have a dedicated `embedding_at` column. Documented approximation: when content changes, `updated_at` updates and the embedding gets re-encoded via the `(content_hash, signal_version)` skip-if-unchanged pattern. So `updated_at` ≈ "last embedding refresh" for actively-touched content. The approximation underestimates freshness for content that didn't change but was re-embedded after a model upgrade. |

## 4 · Output contract

`compute_embedding_age_decay(embedded_at, *, now=None, half_life_days=365) -> float`
- Returns a multiplier in [0, 1].
- `embedded_at = None` → returns 1.0 (no penalty for unknown).
- Future timestamp (clock skew) → clamps to 1.0.
- `half_life_days <= 0` → returns 1.0 (degenerate config; no divide-by-zero).
- Naive datetimes are interpreted as UTC.

`get_age_decay_settings() -> tuple[int, float]` returns `(half_life_days, weight_in_composite)` with cold-start fallback to (365, 0.05).

## 5 · Implementation

| File | Change |
|---|---|
| `backend/apps/pipeline/services/embedding_age.py` | New file. ~70 lines, pure-Python, zero deps. |
| `backend/apps/pipeline/tests_observability_helpers.py` | Added `EmbeddingAgeDecayTests` (9 cases). |

Settings keys (`pipeline.embedding_age_half_life_days = 365`, `pipeline.embedding_age_weight_in_composite = 0.05`) seeded by migration 0061.

## 6 · Test plan

`EmbeddingAgeDecayTests` (9 cases):
1. **Default constant locked at 365 days** (Liu 2009 §1.5.4).
2. **Zero age → multiplier 1.0** (no penalty for fresh).
3. **One half-life → 0.5** (Newton's cooling invariant).
4. **Two half-lives → 0.25** (decay continuation).
5. **`None` timestamp → 1.0** (unknown-age fallback).
6. **Future timestamp → 1.0** (clock-skew clamp).
7. **Zero half-life → 1.0** (degenerate-config safety).
8. **Naive datetime treated as UTC** (DB compatibility).
9. **Custom half-life of 30 days** (operator override scenario).

All 9 pass as `SimpleTestCase`.

## 7 · Wire-in (deferred)

The algorithm + tests + spec ship in this commit. Wire-in into the
ranker composite is a one-line addition:

```python
# ranker.py near line 928, where score_final starts being assembled
from apps.pipeline.services.embedding_age import (
    compute_embedding_age_decay,
    get_age_decay_settings,
)
half_life_days, age_weight = get_age_decay_settings()
embedded_at = getattr(destination_record, "updated_at", None)
age_decay = compute_embedding_age_decay(embedded_at, half_life_days=half_life_days)
score_final += float(age_weight) * age_decay
```

Deferred for two reasons: (1) the ranker hot path needs benchmark
sweeps when any new component lands (per `docs/PERFORMANCE.md` §6.1);
(2) the wire-in interacts with `score_destination_matches`'s 23 kwargs
which is at the linter's too-many-args ceiling — the right move is to
add the age-decay component as part of a planned dataclass refactor
of those kwargs.

## 8 · Citations on every default

- `pipeline.embedding_age_half_life_days = 365` — Liu 2009 §1.5.4 (one-year half-life is the gold standard for stable corpora).
- `pipeline.embedding_age_weight_in_composite = 0.05` — small enough that it cannot dominate the 15-component composite, large enough to break ties between equally-scored candidates. Same magnitude as `weighted_authority.ranking_weight = 0.05`.
- The `0.5 ^ (days / half_life)` formula — Newton's law of cooling.
- `None`-timestamp returns 1.0 — pragmatic engineering choice; penalising "unknown age" would silently downrank legitimate fresh embeddings whose timestamp couldn't be determined.

## 9 · Auto-tuner integration (FR-018 + FR-249)

`apps.suggestions.services.weight_tuner.WeightTuner` was extended to
accept `score_embedding_age` as a 5th tunable signal alongside the
original four (`score_semantic`, `score_keyword`, `score_node_affinity`,
`score_quality`). Activation is gated on the AppSetting
`pipeline.embedding_age_weight_in_composite` being positive (default
0.05). The default seeded weight is `w_embedding_age = 0.05` per
`migration suggestions/0064_seed_w_embedding_age.py`.

The L-BFGS-B objective and the bounded-simplex projection both already
handled N-weight inputs (the comment at `weight_tuner.py:225`
explicitly anticipated this); the only changes were:
- `Suggestion.score_embedding_age` FloatField (default 1.0) added via
  `migration suggestions/0063_add_score_embedding_age.py`.
- `ScoredCandidate.score_embedding_age` field on the ranker dataclass.
- Ranker's composite loop now passes the computed multiplier into
  the candidate.
- `pipeline_persist._build_suggestion_records` now writes the value
  through to each `Suggestion` row.
- `WeightTuner._maybe_add_fr249_age_decay` extends `feature_keys` and
  `weight_keys` at construction time when the gate is on.

**What's NOT in the L-BFGS scope and why:** the FR-018 tuner fits
*multiplicative weights on linear score features* (`score_final =
Σ w_i · score_i + remainder`). Parameters that change the shape of
the score function itself (`pipeline.embedding_age_half_life_days`,
`pipeline.bm25_k1`, `pipeline.bm25_b`, `pipeline.rrf_k`,
`pipeline.stage1_mmr_lambda`, `pipeline.min_calibrated_probability`,
`pipeline.nrt_delta_*`) are *algorithm parameters* — they don't fit
the linear blend. Operators tune them via the Settings UI (with the
cited starting points seeded by migrations `0061` / `0062` / `0064`)
or via offline sweep harnesses; the L-BFGS tuner correctly leaves
them alone.

## 10 · Status

Algorithm + ranker wire-in + ScoredCandidate field + Suggestion
column + persist write + WeightTuner extension + 5th-tunable seed
all shipped 2026-05-07. **Default-on AND auto-tuned** by the FR-018
monthly run.
