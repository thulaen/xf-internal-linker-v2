# FR-018b — Meta-algorithm autotuner

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Meta-algorithm autotuner |
| **Settings prefix** | `pipeline.*`, `slate_diversity.*`, `click_distance.*`, `explore_exploit.*`, `field_aware_relevance.*`, `clustering.*` (the per-key list lives in `_META_PARAM_BOUNDS` in `apps/suggestions/services/meta_tuner.py`) |
| **Pipeline stage** | Out-of-band — Celery beat schedule, monthly. Mirrors FR-018's monthly weight tuner. |
| **Helper module** | `backend/apps/suggestions/services/meta_tuner.py` |
| **Related spec** | `fr018-auto-tuned-ranking-weights.md` — the original L-BFGS-B tuner over the four ranking-blend weights. This spec covers everything else (the meta-algorithm parameters). |
| **Default state** | **ON** for the V1 listed parameters. New parameters added to the dict default-on per `DEFAULT-ON-RULE.md`. |

## 2 · Motivation (ELI5)

The original autotuner (FR-018) only adjusts four numbers — the ranking-blend weights `w_semantic`, `w_keyword`, `w_node`, `w_quality`. But the project has many *other* numbers that affect quality: how many candidates to fetch (`stage1_top_k`), how aggressively to penalise long documents in BM25 (`bm25_b`), how much to favour diversity in the slate reranker (`slate_diversity.diversity_lambda`), and so on. These are called **meta-algorithm parameters** — knobs on the algorithms themselves. Until this spec, none of them were auto-tuned. This spec adds a second tuner that drifts those numbers monthly within safe per-key bounds, never zeros them, and goes through the same challenger-escrow safety gates as FR-018.

## 3 · Academic sources

| Parameter | Source | Default | Range |
|---|---|---|---|
| `pipeline.rrf_k` | Cormack, Clarke & Büttcher (2009), SIGIR'09 §3 | 60 | 20–200 |
| `pipeline.bm25_k1` | Robertson & Zaragoza (2009), F&T in IR 3(4) §3.5 | 1.2 | 0.5–3.0 |
| `pipeline.bm25_b` | Robertson & Zaragoza (2009), F&T in IR 3(4) §3.5 | 0.75 | 0.05–1.0 |
| `pipeline.stage1_mmr_lambda` | Carbonell & Goldstein (1998), SIGIR §3 | 0.7 | 0.05–0.95 |
| `slate_diversity.similarity_cap` | Drosou & Pitoura (2010), SIGMOD Record §3.1 | 0.90 | 0.5–1.0 |

The full list lives in `_META_PARAM_BOUNDS` (`backend/apps/suggestions/services/meta_tuner.py`). Every row has an inline citation comment.

## 4 · Algorithm

For each of the ~17 tunable meta-keys:

1. Read the current AppSetting value via `get_current_weights()`.
2. Sample a drift `d ~ Uniform(−5%, +5%)`.
3. Candidate = `current × (1 + d)`, clamped to the per-key bounds.
4. Floor at the per-key lower bound (never zero).

The complete candidate dict is wrapped in a `RankingChallenger` row with `kind="meta_algorithm"`, then `evaluate_meta_challenger` runs **two safety checks** before promoting:

1. **Recent-regression check.** If any meta-algorithm challenger was rolled back in the last 30 days (excluding the current one), the new challenger is rejected. Drifting further while the rollback watchdog has flagged a recent regression would compound the problem.
2. **Consecutive-failure check.** If the last 3 meta-algorithm challengers (excluding the current one) all ended in `rolled_back` or `rejected`, the gate **escalates**: the new challenger is rejected AND an `OperatorAlert` fires (`event_type="meta_tuner.consecutive_failures"`). Either the bounds in `_META_PARAM_BOUNDS` need narrowing or the tuner's optimisation strategy needs review.

If both checks pass, the candidate promotes via `apply_weights` (which writes only the listed keys, per the A3 scope fix) and records history with `source="auto_tune_meta"`. The same weekly GSC rollback watchdog that covers FR-018 will revert any regression that slips through.

## 5 · DEFAULT-ON-RULE compliance

Every tunable key has a non-zero lower bound. The tuner physically cannot drive any parameter to zero or "off" — by construction. New parameters added to `_META_PARAM_BOUNDS` must inherit the same invariant; the unit tests pin it.

## 6 · Excluded keys

`pipeline.embedding_age_half_life_days` is deliberately NOT auto-tuned. The half-life is a data-driven constant — it depends on the actual embedding refresh cadence on the live forum. Drifting it ±5% per month would damage the freshness signal unpredictably. The exclusion is documented in `_AUTOTUNER_EXCLUDED` with a one-line rationale.

If a future operator needs to widen the auto-tuned set, they:
1. Add the key to `_META_PARAM_BOUNDS` with a defensible (lo, hi) pair.
2. Verify the lo > 0.
3. Add a citation comment with the source paper.
4. Update this spec's §3 table.

## 7 · Test plan

`backend/apps/suggestions/test_meta_tuner_bounds.py` (new — TODO in implementation):

- Every key in `_META_PARAM_BOUNDS` has a positive lower bound.
- `propose_meta_parameter_drift` outputs satisfy: per-key clamping, never zero, drift ≤ 5% magnitude.
- Excluded keys are absent from the proposal output.
- Empty `current_values` → empty proposal (cold-start safe).

## 8 · Wiring (shipped 2026-05-09)

- **Celery beat:** `monthly-python-meta-tune` runs at 14:15 UTC on the first Sunday of every month — 30 minutes after the FR-018 ranking-weight tuner so the two don't contend for the same Postgres write window. Defined in `backend/config/settings/celery_schedules.py`.
- **Tasks:** `pipeline.monthly_meta_tune` builds the candidate; `pipeline.evaluate_meta_challenger` promotes it via `apply_weights` (which now writes only the listed keys per A3 — so unrelated AppSetting values are untouched). Both tasks live in `backend/apps/pipeline/tasks.py`.
- **Discriminator:** `RankingChallenger.kind` (new field added by migration `0067_rankingchallenger_kind.py`) distinguishes ranking-weight challengers (`kind="weights"`, the FR-018 originals) from meta-algorithm challengers (`kind="meta_algorithm"`, FR-018b). The same SPRT evaluator + weekly GSC rollback watchdog cover both kinds.
- **Sentient-schedule recovery:** the new beat slot is registered in `_MONTHLY_SCHEDULES` (`backend/apps/core/apps.py`) so a missed firing is recovered on the next backend boot.

## 9 · Out of scope (deferred to future sessions)

- **Bayesian / TPE optimisation over the box.** V1 is uniform-drift; future versions can use scikit-optimize's TPE over the same `_META_PARAM_BOUNDS`. The challenger-escrow gate stays the same.
- **Tuning the four ranking-blend weights.** That stays with FR-018's L-BFGS-B simplex tuner.
