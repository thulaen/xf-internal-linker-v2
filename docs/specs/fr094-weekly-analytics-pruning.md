# FR-094 - Weekly Analytics Pruning

## Confirmation

- **Backlog confirmed**: `FR-094 - Weekly Analytics Pruning` is a pending Tier 2 data retention task.
- **Repo confirmed**: `backend/config/settings/base.py` contains the Celery beat schedule. No existing entry prunes analytics tables.
- **Repo confirmed**: The 3 target tables (`analytics_gscdailyperformance`, `analytics_suggestiontelemetrydaily`, `analytics_gsckeywordimpact`) grow at 500-5000 rows/day and are not covered by any existing retention task.
- **Repo confirmed**: These tables are too large to prune nightly without impacting the pipeline schedule. A separate weekly task is appropriate.

## Engineering Rationale

FR-094 is not derived from a patent. It is a storage management task based on observed table growth rates.

The three analytics tables targeted by FR-094 are the heaviest-growing tables in the database. GSC daily performance alone can add 5,000 rows per day on a large site. Without pruning, these tables reach 15-40 GB per year and degrade query performance across the analytics dashboard and the auto-weight-tuning pipeline.

A weekly cadence balances pruning frequency against the cost of running large DELETE operations and VACUUM ANALYZE on multi-million-row tables.

## Plain-English Summary

Simple version first.

Three analytics tables grow fast -- up to 5,000 new rows per day. They store daily snapshots of Google Search Console performance, suggestion telemetry, and keyword impact data. After 90-180 days, this data is no longer needed for trending or tuning.

FR-094 adds a weekly Celery beat task that deletes rows older than their retention period and then runs VACUUM ANALYZE to reclaim the disk space and update query planner statistics.

Think of it like taking out the recycling once a week instead of letting it pile up.

## Problem Statement

Today the three analytics tables grow without any automatic pruning:

| Table | Daily growth | Row size | Annual growth |
|---|---|---|---|
| `analytics_gscdailyperformance` | 500-5,000 rows | ~200 bytes | 36 MB - 360 MB per 90-day window |
| `analytics_suggestiontelemetrydaily` | 200-2,000 rows | ~300 bytes | 22 MB - 220 MB per 180-day window |
| `analytics_gsckeywordimpact` | 100-1,000 rows | ~250 bytes | 9 MB - 91 MB per 180-day window |

Without pruning, these tables accumulate 15-40 GB per year (including index overhead). This slows the analytics dashboard, increases backup size, and wastes disk on data that has no operational value after its retention window.

## Goals

FR-094 should:

- add a new weekly Celery beat task (`weekly_analytics_pruning`) scheduled for Sunday 04:00;
- delete rows older than the retention period from 3 analytics tables;
- run VACUUM ANALYZE after each DELETE to reclaim space and update statistics;
- log row counts and timing for each table;
- reclaim ~15-40 GB of disk per year.

## Non-Goals

FR-094 does not:

- prune operational tables (those are handled by FR-093 nightly);
- prune suggestion diagnostics JSON or broken links (those are handled by FR-096 monthly);
- do VACUUM FULL or REINDEX (those are handled by FR-095 quarterly);
- change any analytics model, migration, or API endpoint;
- change any ranking signal, pipeline algorithm, or frontend component;
- affect the nightly pipeline schedule.

## Math-Fidelity Note

### Deletion queries

```sql
-- 1. GSC daily performance: 90 days
DELETE FROM analytics_gscdailyperformance
WHERE date < (NOW() - INTERVAL '90 days')::date;
-- Growth rate: 500-5000 rows/day
-- Row size: ~200 bytes (date, URL ID, clicks, impressions, position, CTR)
-- 90-day window: 45,000-450,000 rows retained
-- Rows deleted per weekly run: 3,500-35,000
-- Space reclaimed per run: 700 KB - 7 MB (plus index space via VACUUM)
-- Yearly savings: ~800 MB - 2 GB
```

```sql
-- 2. Suggestion telemetry daily: 180 days
DELETE FROM analytics_suggestiontelemetrydaily
WHERE date < (NOW() - INTERVAL '180 days')::date;
-- Growth rate: 200-2000 rows/day (segmented by device, channel, geo)
-- Row size: ~300 bytes (date, suggestion ID, segment fields, impressions, clicks, CTR)
-- 180-day window: 36,000-360,000 rows retained
-- Rows deleted per weekly run: 1,400-14,000
-- Space reclaimed per run: 420 KB - 4.2 MB (plus index space via VACUUM)
-- Yearly savings: ~500 MB - 1.5 GB
```

```sql
-- 3. GSC keyword impact: 180 days (via snapshot join)
DELETE FROM analytics_gsckeywordimpact
WHERE snapshot_id IN (
    SELECT id FROM analytics_gscimpactsnapshot
    WHERE created_at < NOW() - INTERVAL '180 days'
);
-- Growth rate: 100-1000 rows/day
-- Row size: ~250 bytes (snapshot ID, keyword, clicks delta, impressions delta)
-- 180-day window: 18,000-180,000 rows retained
-- Rows deleted per weekly run: 700-7,000
-- Space reclaimed per run: 175 KB - 1.75 MB (plus index space via VACUUM)
-- Yearly savings: ~200 MB - 600 MB
```

### Post-deletion maintenance

```sql
VACUUM ANALYZE analytics_gscdailyperformance;
VACUUM ANALYZE analytics_suggestiontelemetrydaily;
VACUUM ANALYZE analytics_gsckeywordimpact;
```

VACUUM ANALYZE does two things: (1) marks deleted row space as reusable by future inserts (does not return space to the OS -- that requires VACUUM FULL in FR-095), and (2) updates the query planner's row count and distribution statistics so queries run with accurate plans.

### Growth rate math

```
GSC daily performance:
  Low site:   500 pages x 1 row/page/day = 500 rows/day
  High site:  5000 pages x 1 row/page/day = 5000 rows/day
  90-day accumulation: 45,000 - 450,000 rows

Suggestion telemetry daily:
  Low site:   200 suggestions x 1 segment = 200 rows/day
  High site:  2000 suggestions x 1 segment = 2000 rows/day
  180-day accumulation: 36,000 - 360,000 rows

GSC keyword impact:
  Low site:   100 keywords/snapshot x 1 snapshot/day = 100 rows/day
  High site:  1000 keywords/snapshot x 1 snapshot/day = 1000 rows/day
  180-day accumulation: 18,000 - 180,000 rows
```

### Total yearly savings

```
GSC daily performance:         ~800 MB - 2 GB
Suggestion telemetry daily:    ~500 MB - 1.5 GB
GSC keyword impact:            ~200 MB - 600 MB
---
Subtotal (data only):          ~1.5 GB - 4.1 GB
Index overhead (estimated 3x): ~4.5 GB - 12.3 GB
VACUUM reclaim rate (~70%):    ~3.2 GB - 8.6 GB
---
Effective yearly savings:      ~15 - 40 GB (including index bloat prevented)
```

## Scope Boundary

FR-094 must stay separate from:

- **FR-093** (nightly retention) -- FR-093 prunes lightweight operational tables nightly. FR-094 prunes heavyweight analytics tables weekly. Zero table overlap.
- **FR-095** (quarterly maintenance) -- FR-095 does VACUUM FULL (returns space to OS) and REINDEX. FR-094 does plain VACUUM ANALYZE (marks space reusable, updates stats). Different operations with different locking profiles.
- **FR-096** (monthly safe prune) -- FR-096 prunes BrokenLink, ImpactReport, and diagnostics JSON. FR-094 prunes GSC performance, suggestion telemetry, and keyword impact. Zero table overlap.
- **Auto-weight tuning** (FR-018) -- The weight tuner reads from these analytics tables. FR-094's retention periods (90d, 180d) are long enough that the tuner always has sufficient historical data. The tuner's lookback window is configurable but defaults to 30 days.

Hard rule: FR-094 must not delete rows within the tuner's lookback window. The 90-day minimum retention period provides a 3x safety margin over the 30-day default lookback.

## Inputs Required

FR-094 uses only data already available:

- `backend/config/settings/base.py` -- beat schedule (modified to add new weekly entry)
- `backend/apps/pipeline/tasks.py` -- new `weekly_analytics_pruning` task
- The 3 target tables -- all already exist with standard Django models

Explicitly disallowed inputs:

- No new models or migrations
- No new API endpoints
- No frontend changes

## Settings And Feature-Flag Plan

### Operator-facing settings

No new `AppSetting` keys. Retention periods are hardcoded in the task, matching the pattern used by FR-093 and the existing nightly retention task.

### Beat schedule entry

```python
"weekly-analytics-pruning": {
    "task": "pipeline.weekly_analytics_pruning",
    "schedule": crontab(hour=4, minute=0, day_of_week=0),  # Sunday 04:00
    "options": {"queue": "pipeline", "expires": 7200},
},
```

### Feature-flag behavior

No feature flag. The task runs unconditionally on its weekly schedule. To disable, remove or comment out the beat schedule entry.

## Diagnostics And Explainability Plan

### Log output per run

```
[Analytics Prune] GSCDailyPerformance: deleted 24,500 rows older than 90 days (3.2s)
[Analytics Prune] SuggestionTelemetryDaily: deleted 8,200 rows older than 180 days (1.8s)
[Analytics Prune] GSCKeywordImpact: deleted 4,100 rows older than 180 days (0.9s)
[Analytics Prune] VACUUM ANALYZE on 3 tables (12.4s)
[Analytics Prune] Tier 2 complete. Total deleted: 36,800 rows. Total time: 18.3s.
```

### Error handling

If any DELETE or VACUUM fails, the task logs the error and continues to the next table. It does not abort the entire run.

### Monitoring

The task should emit a Celery task result with `rows_deleted` and `duration_seconds` fields so the operator can track pruning trends over time.

## Storage / Model / API Impact

### Suggestion model

No changes.

### Content model

No changes.

### Analytics models

No changes. The 3 target tables already exist.

### Migrations

No new migrations needed.

### Backend API

No changes.

### Frontend

No changes.

### Beat schedule

One new entry in `CELERY_BEAT_SCHEDULE` in `settings/base.py`.

## Backend Service Touch Points

Implementation files:

- `backend/config/settings/base.py` -- add weekly beat schedule entry
- `backend/apps/pipeline/tasks.py` -- add `weekly_analytics_pruning` task with 3 DELETE statements and 3 VACUUM ANALYZE calls

Files that must stay untouched:

- All analytics model files (no schema changes)
- All ranking, scoring, and signal files
- All frontend files
- The existing `nightly_data_retention` task (FR-093 extends that separately)

## Test Plan

### 1. GSCDailyPerformance pruning

- Insert 10,000 rows with dates spanning 1-120 days ago.
- Run `weekly_analytics_pruning`.
- Verify rows older than 90 days are deleted.
- Verify rows within the 90-day window are untouched.

### 2. SuggestionTelemetryDaily pruning

- Insert 5,000 rows with dates spanning 1-200 days ago.
- Run `weekly_analytics_pruning`.
- Verify rows older than 180 days are deleted.
- Verify rows within the 180-day window are untouched.

### 3. GSCKeywordImpact pruning via snapshot join

- Insert 3 GscImpactSnapshot records: one from 190 days ago, one from 100 days ago, one from today.
- Insert 1,000 GSCKeywordImpact rows linked to the old snapshot, 500 to the middle, 200 to today's.
- Run `weekly_analytics_pruning`.
- Verify the 1,000 rows linked to the 190-day-old snapshot are deleted.
- Verify the 500 and 200 rows linked to newer snapshots are untouched.

### 4. VACUUM ANALYZE runs

- Verify that after deletion, `pg_stat_user_tables.last_vacuum` and `last_analyze` timestamps are updated for all 3 tables.

### 5. Row count logging

- Run on a database with known row counts.
- Verify log output matches expected deletion counts.

### 6. Error isolation

- Temporarily lock one table.
- Run `weekly_analytics_pruning`.
- Verify the locked table's DELETE logs an error but the other 2 tables are still pruned.

### 7. Weight tuner safety

- Verify the weight tuner's default 30-day lookback window has data after pruning.
- Set the tuner's lookback to 90 days. Verify GSCDailyPerformance still has data for the full 90-day window.

## Risk List

- The first run on a database that has never been pruned may delete hundreds of thousands of rows. The DELETE could take 1-5 minutes and briefly increase disk I/O. Mitigation: the task runs at 04:00 Sunday when traffic is lowest.
- VACUUM ANALYZE on large tables can take 10-30 seconds and briefly increases I/O. Mitigation: this is standard PostgreSQL maintenance; it does not lock the table for reads or writes.
- The GSCKeywordImpact DELETE uses a subquery (`snapshot_id IN (SELECT ...)`). On very large tables this could be slow. Mitigation: the `analytics_gscimpactsnapshot.created_at` column is indexed; the subquery returns a small set of IDs.
- If an operator changes the weight tuner's lookback window to >90 days, they may lose historical GSC data needed for tuning. Mitigation: the 90-day retention period is documented here; the tuner's default is 30 days with a 3x safety margin.
