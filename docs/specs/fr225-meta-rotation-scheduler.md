# FR-225 — Meta Rotation Scheduler

## Overview

Coordinates the 249 meta-algorithms (META-01..META-249) so they run sequentially without fighting each other. Within each "stage slot" (optimiser, loss function, calibrator, learning-rate scheduler, etc.) only one meta is the active driver at a time; alternates wait their turn in a rotation queue. Operators see which meta won the most recent tournament and can pin a winner manually if needed.

This is the orchestration layer that makes the user's intent realistic: "all metas on, but they don't fight, run one after another, complement each other."

## Academic source

Combines two well-established techniques:
- **Tournament hyperparameter selection** — Olson & Moore, "TPOT: A Tree-Based Pipeline Optimization Tool for Automating Machine Learning", Springer 2016 (chapter on tournament-style alternative selection).
- **Multi-armed bandit alternation for ML pipelines** — Li, Jamieson, DeSalvo, Rostamizadeh, Talwalkar, "Hyperband", JMLR 18(185), 2017, DOI [10.5555/3122009.3242042](https://dl.acm.org/doi/10.5555/3122009.3242042) (the bandit-style budget allocation pattern, generalised here from HPO to meta-algorithm rotation).

## Problem this fixes

The Phase 2 research library (FR-099..FR-224 + META-40..META-249) introduces 249 meta-algorithms across 36 "stage slots" (optimisers, losses, calibrators, etc.). For most slots, only one meta can be the active driver at a time without producing contradictory output (two optimisers tuning the same weight vector = thrashing; two calibrators mapping the same scores = ambiguous). Without a coordinator, operators must hand-pick one and ignore the rest — wasting the research investment.

FR-225 adds a Celery-beat-driven scheduler that:
1. Maintains a registry of which meta belongs to which stage slot
2. Knows which slots allow only one active driver vs which allow many to coexist
3. Rotates alternates through the active slot on a configurable cadence (default: monthly)
4. Records win/loss outcomes against a holdout metric (NDCG@10 by default)
5. Persists the current winner per slot in `WeightPreset`

## Design

### Stage slot registry

A new module `backend/apps/suggestions/services/meta_slot_registry.py` defines:

```python
META_SLOT_REGISTRY: dict[str, MetaSlotConfig] = {
    "second_order_optimizer": MetaSlotConfig(
        members=["newton", "gauss_newton", "levenberg_marquardt", "lbfgs_b", "bfgs", "fletcher_reeves_cg"],
        active_default="lbfgs_b",  # winner per FR-225 winner table
        rotation_mode="single_active",  # only one drives at a time
    ),
    "feature_attribution": MetaSlotConfig(
        members=["permutation_importance", "shap_kernel", "lime", "integrated_gradients", "mdi_importance"],
        active_default="all",  # complementary, all can run
        rotation_mode="all_active",
    ),
    # ... 34 more slots (one per stage)
}
```

### Rotation modes

- **`single_active`** (most slots): one meta is the active driver. The scheduler runs the active one on production data; alternates run on a holdout shadow once per rotation cycle and the best-NDCG result becomes the new active.
- **`all_active`** (complementary slots like attribution, anomaly detection, augmentation): every member runs sequentially. No fight, just sequential execution under the heavy/medium/light task lock (already enforced by `with_weight_lock` decorator from ISS-016).

### Scheduling

A new Celery beat task `meta_rotation_tournament` runs nightly:
1. For each `single_active` slot, dispatch the next alternate to a holdout-evaluation Celery task
2. After all alternates have been tested in the slot, compare NDCG@10 results and promote the highest-scoring meta to active
3. Persist winner to `WeightPreset.meta_winners` JSON column
4. Emit a notification ("New winner in optimiser slot: META-49 AMSGrad replaced META-43 L-BFGS-B based on +1.2% NDCG@10 over 28 days")

### Resource budget honesty

Sequential execution means peak RAM at any moment = max single meta RAM (≤ 256 MB per the budget set in earlier specs). Total disk for state-tracking ≤ 50 MB (one row per meta per cycle in the new `MetaTournamentResult` table, pruned after 90 days via FR-094).

## Starting weight preset

```python
"meta_rotation.enabled": "true",
"meta_rotation.tournament_cadence_days": "30",  # rotate alternates monthly
"meta_rotation.holdout_metric": "ndcg_at_10",
"meta_rotation.min_holdout_queries": "100",
"meta_rotation.promotion_threshold_pct": "1.0",  # +1% NDCG required to dethrone
"meta_rotation.notification_on_promotion": "true",
"meta_rotation.shadow_evaluation_concurrent": "false",  # sequential, no resource fight
```

## C++ implementation

Pure orchestration code — no hot-path C++ extension needed. The metas themselves are C++ extensions; this scheduler is Python-only.

- File: `backend/apps/suggestions/services/meta_rotation_scheduler.py`
- Entry: `def run_meta_tournament(slot_id: str | None = None) -> TournamentResult`
- Complexity: O(N) per slot where N = number of alternates (max 8 per slot)
- Runs inside Celery worker; protected by `with_weight_lock("medium")` per FR-016 task-lock convention

## Python implementation outline

```python
@shared_task(bind=True)
@with_weight_lock("medium")
def meta_rotation_tournament(self):
    for slot_id, config in META_SLOT_REGISTRY.items():
        if config.rotation_mode == "single_active":
            _run_single_active_tournament(slot_id, config)
        elif config.rotation_mode == "all_active":
            _run_all_active_pass(slot_id, config)

def _run_single_active_tournament(slot_id: str, config: MetaSlotConfig):
    holdout_queries = HoldoutQuery.objects.filter(stage_slot=slot_id, since=now() - timedelta(days=30))
    if holdout_queries.count() < int(RECOMMENDED_PRESET_WEIGHTS["meta_rotation.min_holdout_queries"]):
        return  # not enough evidence yet
    results = []
    for member in config.members:
        ndcg = _evaluate_meta_on_holdout(member, holdout_queries)
        results.append((member, ndcg))
    results.sort(key=lambda r: -r[1])
    new_winner = results[0][0]
    if _should_promote(current=config.active_default, candidate=new_winner, results=results):
        _promote_winner(slot_id, new_winner, results)
```

## Benchmark plan

| Slot count | Alternates per slot | Eval queries | Target completion |
|---|---|---|---|
| 5 single_active slots | 4 alternates each | 100 holdout queries | < 30 min |
| 10 single_active slots | 6 alternates each | 100 | < 60 min |
| 36 slots (full registry) | 8 alternates each | 100 | < 4 hours |

Sequential execution honours the existing Heavy task lock — the tournament runs after midnight when the system is idle.

## Diagnostics

Adds a new "Meta Tournament" tab to the Diagnostics page showing:
- Current winner per slot (with NDCG@10 score)
- Last tournament date
- Promotion history (last 10 promotions per slot)
- Manual override toggle ("Pin winner — disable rotation for this slot")
- Per-meta resource budget visible (RAM/disk peak from last run)

## Edge cases & neutral fallback

- No holdout data → tournament skipped, current winner stays active, log "insufficient evidence"
- Meta crash during evaluation → meta auto-disabled for 7 days, alert raised
- Tournament running when operator pins a winner → tournament aborts gracefully, pinned winner respected
- All members of a slot fail → revert to `active_default` (the original winner per the winner table)

## Minimum-data threshold

≥ 100 holdout queries per slot before any tournament runs. Below that, the default winner stays active and no rotation occurs.

## Budget

Disk: ~50 MB (rolling 90-day tournament result history, ~30K rows × 1.6 KB)  
RAM: ~256 MB peak (bounded by the heaviest single meta running in shadow eval)

## Scope boundary vs existing FRs

- **FR-018 Auto-tuned weights**: tunes individual signal weights via L-BFGS. FR-225 picks WHICH meta drives the tuning — different layer of the stack.
- **FR-013 Feedback reranker (UCB1)**: bandit over individual SUGGESTIONS at serve time. FR-225 is bandit over META-ALGORITHMS at training time.
- **FR-067 Markov-chain rank aggregation (META-02)**: aggregates ranking results from multiple rankers. FR-225 picks WHICH rankers participate.
- **META-58 Hyperband / META-38 Successive halving**: bandit over hyperparameter configurations within a single meta. FR-225 is bandit across metas.

## Test plan

- Unit: `_should_promote` correctly applies the 1% NDCG threshold; ties resolve to current winner (no churn)
- Unit: `_run_single_active_tournament` skips slots with `< min_holdout_queries`
- Integration: tournament runs end-to-end against a fixture with 5 alternates and produces a deterministic winner ordering
- Integration: meta crash during eval leaves slot in valid state (current winner preserved)
- Integration: operator-pinned slot is not touched by the next scheduled tournament
- Resource: peak RAM during a 36-slot tournament stays under 256 MB
- Diagnostics: tournament results visible in `/diagnostics/meta-tournament` Angular tab

## Implementation notes

- Add `MetaTournamentResult` model: `(slot_id, meta_id, evaluated_at, ndcg_at_10, queries_evaluated, was_winner)`
- Add `WeightPreset.meta_winners: JSONField` for per-slot active selections
- Add Celery beat entry `meta_rotation_tournament` running daily at 03:00 UTC (off-peak)
- Add the meta-slot registry as data, not hard-code — operators can edit it via Django admin
- Add a "manual run" button to the diagnostics tab so operators can trigger a tournament on demand without waiting for the schedule

## Why this is good for the project

Without FR-225, the 249 metas in the recipe are static — operators have to read all the spec files to understand what's available, manually pick winners, and never benefit from the alternates again. FR-225 turns the library into a self-tuning system: every month the scheduler asks "is there a better optimiser than the current one?" and promotes the answer based on real holdout data. The forum operator never has to think about it; they just see a notification when something improves.
