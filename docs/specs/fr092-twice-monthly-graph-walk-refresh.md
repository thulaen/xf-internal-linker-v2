# FR-092 - Twice-Monthly Graph Walk Refresh

## Confirmation

- **Backlog confirmed**: `FR-092 - Twice-Monthly Graph Walk Refresh` is a pending operational optimization task.
- **Repo confirmed**: `backend/apps/pipeline/services/pipeline.py` currently runs graph walk candidate generation on every nightly pipeline pass.
- **Repo confirmed**: `backend/config/settings/base.py` contains the Celery beat schedule that triggers the nightly pipeline.
- **Repo confirmed**: FR-021 (graph-based link candidate generation) defines the Pixie random walk algorithm. FR-092 does not modify the algorithm -- only the schedule.

## Engineering Rationale

FR-092 is not derived from a patent. It is a compute-optimization decision based on observed pipeline behavior.

The knowledge graph changes slowly. Entity nodes and article-entity edges update only when content is re-crawled (typically weekly) or when new pages are imported. Running 1 billion random walk steps every night produces nearly identical candidate sets night after night when the underlying graph has not changed.

Moving graph walks to the 1st and 15th of each month saves 7-14 hours of CPU time per month while keeping candidate sets fresh enough to track bimonthly content changes.

## Plain-English Summary

Simple version first.

The pipeline finds link candidates by doing random walks across the knowledge graph -- hopping from entity to entity across pages. Right now it does this every night, even though the graph barely changes between runs.

FR-092 changes the schedule so the walks only run on the 1st and 15th of each month. On all other nights, the pipeline reuses the walk results from the most recent run. The walk algorithm itself stays exactly the same.

Think of it like a bus map: you do not redraw the route map every day unless the roads have actually changed.

## Problem Statement

Today the nightly pipeline spends 15-30 minutes (on 4 Celery workers) executing Pixie random walks across the full knowledge graph. This produces a candidate set per source article. On 28 out of 30 nights per month, the graph has not materially changed, so the candidate sets are nearly identical to the previous night.

This wastes ~7-14 hours of CPU per month on redundant computation and delays the nightly pipeline completion by 15-30 minutes every night.

## Goals

FR-092 should:

- move graph walk execution from the nightly pipeline to a dedicated bimonthly Celery beat task (1st and 15th at 02:00);
- make the nightly pipeline load cached walk results on non-walk nights;
- keep the Pixie random walk algorithm unchanged (20 entities x 1000 steps = 20,000 walks per article);
- save ~7-14 hours of CPU per month;
- ensure freshness: if the graph changes mid-month (large import), an operator can trigger a manual walk refresh.

## Non-Goals

FR-092 does not:

- modify the Pixie random walk algorithm, step count, entity selection, or visit threshold;
- change the walk parameters (`walk_steps_per_entity`, `min_visit_threshold`, `top_k_candidates`);
- change any other nightly pipeline stage (embedding, scoring, ranking, retention);
- add new database models or migrations;
- change any ranking signal or score computation;
- affect the frontend UI.

## Math-Fidelity Note

### Walk algorithm (unchanged -- Pixie random walk)

```
For each source article A:
  E = top_n_entities(A, n=20)       # top 20 entities by TF-IDF weight
  For each entity e in E:
    visits = {}                      # candidate visit counter
    current = e
    For step = 1..S:                # S = walk_steps_per_entity = 1000
      neighbours = ArticleEntityEdge.filter(entity=current)
      next_article = weighted_random_choice(neighbours, weight=edge.weight)
      visits[next_article] += 1
      current = random_entity(next_article)  # jump to entity of visited article
    candidates = {a: count for a, count in visits.items() if count >= min_visit_threshold}
  Return top_k_candidates(candidates, k=100) sorted by visit count
```

### Walk volume math

```
Walks per article:     |E| x S = 20 x 1000 = 20,000 steps
Walks per full site:   50,000 articles x 20,000 steps = 1,000,000,000 steps (1 billion)
Runtime:               ~15-30 minutes on 4 Celery workers
```

### Schedule change

```python
# NEW -- replaces graph walk on every nightly run
"bimonthly-graph-walk-refresh": {
    "task": "pipeline.rebuild_graph_walks",
    "schedule": crontab(hour=2, minute=0, day_of_month="1,15"),
    "options": {"queue": "pipeline"},
},
```

### Nightly pipeline change

```python
# In pipeline.py, at graph walk stage:
if not should_run_graph_walks():  # True only on 1st and 15th
    logger.info("Skipping graph walks -- reusing last walk results")
    candidates = load_cached_walk_candidates(source_id)
else:
    candidates = run_pixie_walks(source_id, settings)
    cache_walk_candidates(source_id, candidates)
```

### Compute savings

```
Nights per month:          ~30
Walk nights per month:     2 (1st and 15th)
Skipped nights per month:  ~28
Time saved per skip:       15-30 minutes
Monthly CPU savings:       28 x 15-30 min = 7-14 hours
```

## Scope Boundary

FR-092 must stay separate from:

- **FR-021** (graph-based link candidate generation)
  - FR-021 defines the walk algorithm (Pixie walks, entity selection, visit thresholds, candidate extraction).
  - FR-092 only changes when the walks run, not how they run.
  - FR-092 does not modify any walk parameter or the `run_pixie_walks()` function.

- **Nightly pipeline stages** (embedding, scoring, ranking, retention)
  - FR-092 only modifies the graph walk invocation in `pipeline.py`.
  - All other stages continue to run nightly as before.

- **FR-093 through FR-096** (data retention tasks)
  - These manage database row deletion. FR-092 manages compute scheduling.
  - No overlap in tables touched or code paths modified.

Hard rule: FR-092 must not modify the walk algorithm, its parameters, or its output format.

## Inputs Required

FR-092 uses only data already available in the pipeline:

- `backend/config/settings/base.py` -- beat schedule (modified to add new entry)
- `backend/apps/pipeline/services/pipeline.py` -- graph walk invocation (modified to check schedule)
- `backend/apps/pipeline/tasks.py` -- new task wrapper for bimonthly walks
- Cached walk results -- stored per source article in the existing `GraphWalkCandidate` table

Explicitly disallowed inputs:

- No new database models
- No new API endpoints
- No changes to the walk algorithm code itself

## Settings And Feature-Flag Plan

### Operator-facing settings

No new `AppSetting` keys. The schedule is controlled by the Celery beat configuration in `settings/base.py`.

### Manual trigger

An operator can force a walk refresh outside the schedule by calling the existing `rebuild_graph_walks` task manually via the Django admin or Celery CLI:

```
celery -A config call pipeline.rebuild_graph_walks
```

### Feature-flag behavior

There is no feature flag. The schedule change is unconditional. If the operator wants nightly walks back, they change `day_of_month="1,15"` to `day_of_month="*"` in the beat schedule.

## Diagnostics And Explainability Plan

### Pipeline log messages

On non-walk nights:
```
[Pipeline] Skipping graph walks -- reusing last walk results (last run: 2026-04-01 02:00 UTC)
```

On walk nights:
```
[Pipeline] Running bimonthly graph walk refresh (1,000,000,000 steps across 50,000 articles)
[Pipeline] Graph walks complete in 18m 32s. Cached 50,000 candidate sets.
```

### PipelineRun snapshot

Add one field to `PipelineRun.config_snapshot`:

- `graph_walks_reused: bool` -- `true` when cached walks were used, `false` when fresh walks were computed.

### Health check

The system health page should show a warning if the most recent walk results are older than 20 days (indicates a missed bimonthly run).

## Storage / Model / API Impact

### Suggestion model

No changes.

### Content model

No changes.

### GraphWalkCandidate model

No changes to the model. Walk results are already cached in this table. FR-092 just reads them more often (28 nights/month) and writes them less often (2 nights/month).

### PipelineRun snapshot

Add `graph_walks_reused` boolean to `config_snapshot` JSON.

### Backend API

No new endpoints. The manual trigger uses the existing Celery task invocation path.

### Frontend

No changes. The walk schedule is a backend-only operational concern.

### Database / migrations

No new migrations. The `GraphWalkCandidate` table already exists and already stores walk results.

## Backend Service Touch Points

Implementation files for the code pass:

- `backend/config/settings/base.py` -- add bimonthly beat schedule entry
- `backend/apps/pipeline/tasks.py` -- add `rebuild_graph_walks` task wrapper
- `backend/apps/pipeline/services/pipeline.py` -- modify graph walk stage to check schedule and load cache
- `backend/apps/pipeline/services/graph_walks.py` -- add `should_run_graph_walks()` and `load_cached_walk_candidates()` helpers

Files that must stay untouched:

- `backend/apps/graph/models.py` -- graph models unchanged
- `backend/apps/graph/services/graph_walks.py` -- walk algorithm unchanged
- All ranking, scoring, and signal computation files
- All frontend files

## Test Plan

### 1. Walk results cached correctly

- Run `rebuild_graph_walks` once. Verify `GraphWalkCandidate` rows are populated for all source articles.
- Run the nightly pipeline on a non-walk night. Verify it loads cached candidates without running walks.
- Compare loaded candidates to the original walk output -- they must be identical.

### 2. Walk results refresh on schedule

- Simulate the 1st of the month. Verify `should_run_graph_walks()` returns `True`.
- Simulate the 15th. Verify `should_run_graph_walks()` returns `True`.
- Simulate the 2nd through 14th. Verify `should_run_graph_walks()` returns `False` for all.

### 3. Manual trigger works

- Call `celery call pipeline.rebuild_graph_walks` on a non-walk day.
- Verify walks execute and cache is updated.

### 4. Pipeline timing improvement

- Measure nightly pipeline wall-clock time with and without graph walks.
- Confirm 15-30 minute reduction on non-walk nights.

### 5. PipelineRun snapshot

- On a walk night: `config_snapshot.graph_walks_reused` is `false`.
- On a non-walk night: `config_snapshot.graph_walks_reused` is `true`.

### 6. Stale walk warning

- Set the most recent walk timestamp to 21 days ago.
- Verify the health check reports a warning.

## Risk List

- If a large content import happens mid-month (e.g., 5000 new pages on the 10th), walk candidates will be stale until the 15th. Mitigation: the manual trigger lets an operator force a refresh immediately.
- If the bimonthly beat task fails silently, the nightly pipeline will keep reusing increasingly stale walks. Mitigation: the 20-day staleness warning in health checks catches this.
- Walk results consume database rows (one row per source article per candidate). These rows were already being written nightly; FR-092 writes them less often, so storage impact is neutral or reduced.
