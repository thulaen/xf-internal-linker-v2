# FR-096 - Monthly Safe Prune

## Confirmation

- **Backlog confirmed**: `FR-096 - Monthly Safe Prune` is a pending Tier 5 data pruning task.
- **Repo confirmed**: `backend/config/settings/base.py` contains the Celery beat schedule. No existing entry prunes `graph_brokenlink`, `analytics_impactreport`, or `suggestions_suggestion.graph_walk_diagnostics`.
- **Repo confirmed**: The `graph_brokenlink` table accumulates resolved/dismissed rows indefinitely.
- **Repo confirmed**: The `analytics_impactreport` table stores historical before/after SEO comparisons that no algorithm reads.
- **Repo confirmed**: The `graph_walk_diagnostics` JSON field on `suggestions_suggestion` stores full walk paths, seed entities, and visit counts at 5-50 KB per suggestion. No algorithm reads this field after the suggestion is created.

## Engineering Rationale

FR-096 is not derived from a patent. It is a storage optimization targeting three data sources that are provably safe to prune because no algorithm, sync job, or tuning pipeline reads them.

The three targets were identified by auditing every table and JSON field for downstream consumers:

1. **BrokenLink (resolved/dismissed)**: The link health scanner re-discovers broken links on each scan. Resolved entries are purely historical. No ranking signal, weight tuner, or analytics pipeline reads from `graph_brokenlink`.

2. **ImpactReport**: Stores read-only before/after SEO snapshots. Used only for the operator's historical review UI. No algorithm, sync, or tuner reads this table.

3. **graph_walk_diagnostics JSON**: Stores detailed walk paths for the "Explainability" tab in the suggestion review UI. After 90 days, operators never inspect walk diagnostics for old suggestions. The field is not read by any ranking signal, the graph walk algorithm, or any downstream pipeline stage.

None of these targets feed into GSC, GA4, Matomo, or auto weight tuning.

## Plain-English Summary

Simple version first.

Three data sources grow over time but are completely safe to clean up because nothing important reads from them:

1. Broken links that have already been fixed or dismissed -- the scanner will find them again if they break.
2. Old SEO impact reports -- they are just historical snapshots for the operator to look at.
3. Walk diagnostics JSON blobs on old suggestions -- they explain how a suggestion was found, but nobody looks at that after 90 days.

FR-096 adds a monthly task that deletes the first two and empties the JSON on the third. This saves 800 MB to 2.8 GB per year.

Think of it like clearing out old receipts from your filing cabinet -- you kept them for reference, but after a year they are just taking up space.

## Problem Statement

Today these three data sources grow without pruning:

| Source | Growth rate | Size per entry | Annual accumulation |
|---|---|---|---|
| Resolved/dismissed BrokenLink rows | ~5-20 rows/day | ~1-2 KB | 100-300 MB/year |
| ImpactReport rows | ~1-5 rows/day | ~5-10 KB | 200-500 MB/year |
| graph_walk_diagnostics JSON blobs | ~500-2000/pipeline run | 5-50 KB each | 500 MB - 2.5 GB/year |

The walk diagnostics JSON is the biggest single contributor. A site with 50,000 suggestions accumulates 250 MB to 2.5 GB of walk diagnostics JSON in 90 days alone.

## Goals

FR-096 should:

- add a new monthly Celery beat task (`monthly_safe_prune`) scheduled for the 1st of each month at 05:00;
- delete resolved/dismissed/false_positive BrokenLink rows older than 60 days;
- delete ImpactReport rows older than 365 days;
- null out `graph_walk_diagnostics` JSON on suggestions older than 90 days;
- run VACUUM ANALYZE on the 3 affected tables after pruning;
- reclaim ~800 MB to 2.8 GB of disk per year;
- not affect any data that feeds into GSC, GA4, Matomo, or auto weight tuning.

## Non-Goals

FR-096 does not:

- delete active/unresolved broken links (those are needed by the link health scanner);
- delete suggestions themselves (only the diagnostics JSON is nulled out);
- prune any analytics table (that is handled by FR-094 weekly);
- prune any operational table (that is handled by FR-093 nightly);
- run VACUUM FULL or REINDEX (that is handled by FR-095 quarterly);
- change any ranking signal, pipeline algorithm, or API endpoint;
- affect the frontend UI (the Explainability tab will show "diagnostics pruned" for old suggestions).

## Math-Fidelity Note

### Deletion query 1 -- Resolved/dismissed broken links (60 days)

```sql
DELETE FROM graph_brokenlink
WHERE status IN ('resolved', 'dismissed', 'false_positive')
  AND updated_at < NOW() - INTERVAL '60 days';
```

**Space estimate:**
```
Growth rate:             5-20 resolved/dismissed entries per day
Row size:                ~1-2 KB (URL, status, timestamps, HTTP status code, context)
60-day accumulation:     300-1,200 rows retained
Rows deleted per monthly run: ~150-600
Space reclaimed per run: 150 KB - 1.2 MB
Yearly savings:          ~100-300 MB (including index overhead)
```

**Safety proof:** No ranking signal reads from `graph_brokenlink`. The link health scanner (`backend/apps/diagnostics/`) queries only `status='active'` rows. The BrokenLink model is not referenced by any import in `pipeline/services/`, `suggestions/`, or `analytics/`.

### Deletion query 2 -- Impact reports (365 days)

```sql
DELETE FROM analytics_impactreport
WHERE created_at < NOW() - INTERVAL '365 days';
```

**Space estimate:**
```
Growth rate:             1-5 reports per day
Row size:                ~5-10 KB (before/after metrics JSON, URL, timestamps)
365-day accumulation:    365-1,825 rows retained
Rows deleted per monthly run: ~30-150
Space reclaimed per run: 150 KB - 1.5 MB
Yearly savings:          ~200-500 MB (including index overhead)
```

**Safety proof:** `ImpactReport` is read-only. It stores historical SEO before/after comparisons. No algorithm, sync job, or weight tuner imports or queries this model. The only consumer is the operator's impact review page in the frontend, which shows recent reports.

### Update query 3 -- Null out walk diagnostics JSON (90 days)

```sql
UPDATE suggestions_suggestion
SET graph_walk_diagnostics = '{}'::jsonb
WHERE created_at < NOW() - INTERVAL '90 days'
  AND graph_walk_diagnostics != '{}'::jsonb;
```

**Space estimate:**
```
Average JSON blob size:  5-50 KB per suggestion
  Small site:            5 KB (20 entities x 10 top candidates x short paths)
  Large site:            50 KB (20 entities x 100 candidates x full walk paths)

Suggestions older than 90 days (typical): ~100,000 - 500,000
JSON space per 90-day cohort: 500 MB - 2.5 GB (at 5-50 KB each)

Rows updated per monthly run: ~15,000 - 50,000 (one month's worth aging past the 90-day window)
JSON space nulled per run: ~75 MB - 250 MB
Yearly savings: ~500 MB - 2 GB
```

**Safety proof:** `graph_walk_diagnostics` is a JSON field on the Suggestion model used exclusively by the "Explainability" tab in the suggestion review dialog. It is not read by:
- Any ranking signal (`score_semantic`, `score_keyword`, etc.)
- The graph walk algorithm (`run_pixie_walks()`)
- The auto weight tuner
- Any analytics sync or import pipeline
- Any GSC, GA4, or Matomo integration

The field stores walk paths for human inspection only. After 90 days, no operator inspects these paths.

### Post-pruning maintenance

```sql
VACUUM ANALYZE graph_brokenlink;
VACUUM ANALYZE analytics_impactreport;
VACUUM ANALYZE suggestions_suggestion;
```

### Total yearly savings

```
Resolved broken links:          ~100 - 300 MB
Impact reports:                 ~200 - 500 MB
Walk diagnostics JSON:          ~500 MB - 2 GB
---
Total yearly savings:           ~800 MB - 2.8 GB
```

### Schedule

```python
"monthly-safe-prune": {
    "task": "pipeline.monthly_safe_prune",
    "schedule": crontab(hour=5, minute=0, day_of_month=1),
    "options": {"queue": "pipeline", "expires": 7200},
},
```

Runs on: the 1st of every month at 05:00.

## Scope Boundary

FR-096 must stay separate from:

- **FR-093** (nightly retention) -- FR-093 prunes Celery results, alerts, sync jobs, and scorecards. FR-096 prunes broken links, impact reports, and diagnostics JSON. Zero table overlap.
- **FR-094** (weekly analytics pruning) -- FR-094 prunes GSC performance, suggestion telemetry, and keyword impact. FR-096 prunes broken links, impact reports, and diagnostics JSON. Zero table overlap.
- **FR-095** (quarterly maintenance) -- FR-095 does VACUUM FULL and REINDEX. FR-096 does DELETE/UPDATE and plain VACUUM ANALYZE. Different operations.
- **Auto weight tuning** (FR-018) -- The weight tuner reads from GSC, GA4, and Matomo data. FR-096 does not touch any of those tables. The `graph_walk_diagnostics` field is explicitly not used by the tuner.
- **Link health scanner** -- The scanner queries `graph_brokenlink WHERE status='active'`. FR-096 only deletes `resolved`, `dismissed`, and `false_positive` rows. Active broken links are never touched.

Hard rule: FR-096 must never delete or modify data that feeds into GSC, GA4, Matomo, or auto weight tuning.

## Inputs Required

FR-096 uses only data already available:

- `backend/config/settings/base.py` -- beat schedule (modified to add monthly entry)
- `backend/apps/pipeline/tasks.py` -- new `monthly_safe_prune` task
- The 3 target tables/fields -- all already exist with standard Django models

Explicitly disallowed inputs:

- No new models or migrations
- No new API endpoints
- No frontend changes (except a "diagnostics pruned" fallback message in the review dialog)

## Settings And Feature-Flag Plan

No new operator-facing settings. Retention periods are hardcoded in the task.

The task does not have a feature flag. It runs unconditionally on its monthly schedule. To disable, remove or comment out the beat schedule entry.

## Diagnostics And Explainability Plan

### Log output per run

```
[Safe Prune] BrokenLink (resolved/dismissed/false_positive): deleted 420 rows older than 60 days (0.3s)
[Safe Prune] ImpactReport: deleted 85 rows older than 365 days (0.1s)
[Safe Prune] graph_walk_diagnostics: nulled 32,000 JSON blobs older than 90 days (4.2s, ~160 MB reclaimed)
[Safe Prune] VACUUM ANALYZE on 3 tables (8.1s)
[Safe Prune] Tier 5 complete. Total time: 12.7s.
```

### Frontend fallback

When the suggestion review dialog loads a suggestion whose `graph_walk_diagnostics` is `'{}'`, the Explainability tab should display:

```
Walk diagnostics were pruned after 90 days to save storage.
The suggestion's scores and ranking are unaffected.
```

### Error handling

If any DELETE/UPDATE or VACUUM fails, the task logs the error and continues to the next operation. Partial completion is acceptable.

## Storage / Model / API Impact

### Suggestion model

No schema changes. The `graph_walk_diagnostics` JSONField already exists. FR-096 sets it to `'{}'` on old rows.

### Content model

No changes.

### Graph models

No schema changes. The `BrokenLink` model already exists. FR-096 deletes rows with resolved/dismissed status.

### Analytics models

No schema changes. The `ImpactReport` model already exists. FR-096 deletes old rows.

### Migrations

No new migrations needed.

### Backend API

No changes. The suggestion detail API already returns `graph_walk_diagnostics` -- it will return `{}` for pruned suggestions.

### Frontend

One small change: the Explainability tab in the suggestion review dialog should check for empty `graph_walk_diagnostics` and display the fallback message instead of rendering an empty walk visualization.

### Beat schedule

One new entry in `CELERY_BEAT_SCHEDULE` in `settings/base.py`.

## Backend Service Touch Points

Implementation files:

- `backend/config/settings/base.py` -- add monthly beat schedule entry
- `backend/apps/pipeline/tasks.py` -- add `monthly_safe_prune` task with 2 DELETE statements, 1 UPDATE statement, and 3 VACUUM ANALYZE calls
- `frontend/src/app/review/suggestion-detail-dialog.component.html` -- add fallback message for empty walk diagnostics (optional, non-blocking)

Files that must stay untouched:

- All model files (no schema changes)
- All ranking, scoring, and signal files
- All analytics sync and import files
- The link health scanner
- The auto weight tuner

## Test Plan

### 1. BrokenLink pruning (resolved only)

- Insert 50 BrokenLink rows with `status='resolved'` and `updated_at` set to 61 days ago.
- Insert 30 BrokenLink rows with `status='active'` and `updated_at` set to 90 days ago.
- Run `monthly_safe_prune`.
- Verify 50 resolved rows are deleted.
- Verify 30 active rows are untouched.

### 2. BrokenLink pruning (dismissed and false_positive)

- Insert 20 rows with `status='dismissed'` and `updated_at` set to 65 days ago.
- Insert 10 rows with `status='false_positive'` and `updated_at` set to 70 days ago.
- Run `monthly_safe_prune`.
- Verify all 30 rows are deleted.

### 3. ImpactReport pruning

- Insert 100 ImpactReport rows with `created_at` spanning 1-400 days ago.
- Run `monthly_safe_prune`.
- Verify rows older than 365 days are deleted.
- Verify rows within the 365-day window are untouched.

### 4. Walk diagnostics JSON nulling

- Insert 1,000 Suggestion rows with `created_at` set to 91 days ago and `graph_walk_diagnostics` containing a 10 KB JSON blob.
- Insert 500 Suggestion rows with `created_at` set to 30 days ago and `graph_walk_diagnostics` containing a 10 KB JSON blob.
- Run `monthly_safe_prune`.
- Verify 1,000 old suggestions have `graph_walk_diagnostics = '{}'`.
- Verify 500 recent suggestions have their original JSON intact.

### 5. Already-pruned suggestions are skipped

- Run `monthly_safe_prune` twice in a row.
- Verify the second run reports 0 JSON blobs nulled (the `!= '{}'::jsonb` guard prevents redundant updates).

### 6. VACUUM ANALYZE runs

- Verify that after pruning, `pg_stat_user_tables.last_vacuum` and `last_analyze` timestamps are updated for all 3 tables.

### 7. Row count logging

- Run on a database with known row counts.
- Verify log output matches expected deletion/update counts.

### 8. No downstream impact

- Run a full pipeline after `monthly_safe_prune`.
- Verify all ranking signals produce the same scores as before pruning.
- Verify the weight tuner runs without errors.
- Verify the link health scanner runs without errors.

### 9. Frontend fallback

- Load the suggestion review dialog for a suggestion with `graph_walk_diagnostics = '{}'`.
- Verify the Explainability tab shows the fallback message instead of an empty visualization.

## Risk List

- The walk diagnostics UPDATE touches the `suggestions_suggestion` table, which is also targeted by FR-095's VACUUM FULL. If both tasks run on the same day (1st of Jan/Apr/Jul/Oct), the UPDATE should run before the VACUUM FULL. Mitigation: FR-096 runs at 05:00, FR-095 runs at 03:00. The VACUUM FULL finishes first, then the UPDATE runs on the compacted table. This is safe.
- Nulling `graph_walk_diagnostics` on 32,000+ rows in one UPDATE could briefly increase WAL (write-ahead log) volume. Mitigation: the UPDATE runs at 05:00 on the 1st of the month, low-traffic time. WAL archiving handles the spike.
- An operator who wants to inspect walk diagnostics for a specific old suggestion will find them pruned. Mitigation: 90 days is generous for diagnostic review. If longer retention is needed, the INTERVAL can be increased in the task code.
- Deleting resolved BrokenLink rows means the operator cannot see historical resolution patterns. Mitigation: the link health scanner stores aggregate statistics separately; individual resolved rows have no analytical value after 60 days.
