# FR-095 - Quarterly Database Maintenance

## Confirmation

- **Backlog confirmed**: `FR-095 - Quarterly Database Maintenance` is a pending Tier 4 data maintenance task.
- **Repo confirmed**: `backend/config/settings/base.py` contains the Celery beat schedule. No existing entry performs VACUUM FULL, REINDEX CONCURRENTLY, or full entity re-extraction.
- **Repo confirmed**: The `suggestions_suggestion` table accumulates deleted and superseded rows that plain VACUUM cannot fully reclaim.
- **Repo confirmed**: The pgvector embedding indexes (`content_contentitem_embedding_idx`, `content_sentence_embedding_idx`) fragment over time as embeddings are updated.
- **Repo confirmed**: Entity nodes and article-entity edges can become stale when pages are deleted or substantially rewritten between quarterly re-extractions.

## Engineering Rationale

FR-095 is not derived from a patent. It is standard PostgreSQL maintenance practice applied to the project's heaviest tables and indexes.

Plain VACUUM (run nightly by autovacuum and weekly by FR-094) marks dead rows as reusable but does not return disk space to the operating system. Over months, the Suggestion table accumulates physical bloat from row churn (old suggestions superseded by new pipeline runs). VACUUM FULL rewrites the entire table, compacting it and returning freed space to the OS.

Similarly, HNSW and IVFFlat indexes on embedding columns fragment as vectors are updated. REINDEX CONCURRENTLY rebuilds these indexes without blocking reads, recovering 10-20% of index size.

Full entity re-extraction ensures the knowledge graph reflects current page content, not content from months ago that has since been rewritten.

These operations are too expensive to run nightly or weekly. A quarterly cadence (January, April, July, October) balances maintenance cost against cumulative bloat.

## Plain-English Summary

Simple version first.

Databases accumulate clutter over time -- deleted rows leave gaps in files, indexes get fragmented, and extracted entities go stale. Normally the database does light cleanup on its own, but it never fully compacts tables or rebuilds indexes from scratch.

FR-095 adds a quarterly task that does the heavy cleanup: it rewrites the Suggestion table to eliminate all gaps, rebuilds the embedding indexes to remove fragmentation, re-extracts all entities from page content to remove stale entries, and logs a full table size report.

Think of it like a deep clean of a house -- you do light tidying daily, but four times a year you move the furniture and clean behind it.

## Problem Statement

Today there is no scheduled heavyweight maintenance. The consequences accumulate:

| Problem | Impact after 1 year |
|---|---|
| Suggestion table bloat (dead rows from superseded suggestions) | Table 30-50% larger than necessary; sequential scans 30-50% slower |
| Embedding index fragmentation | Index 10-20% larger; approximate nearest-neighbor queries 5-10% slower |
| Stale entity nodes (from deleted/rewritten pages) | Knowledge graph contains ghost entities that generate bad walk candidates |
| No table size reporting | Operators have no visibility into which tables are growing fastest |

## Goals

FR-095 should:

- add a new quarterly Celery beat task (`quarterly_database_maintenance`) scheduled for the 1st of January, April, July, and October at 03:00;
- run VACUUM FULL on the `suggestions_suggestion` table to compact it;
- run REINDEX CONCURRENTLY on both pgvector embedding indexes;
- truncate entity edges and re-run full entity extraction;
- run a table bloat analysis query and log the top 20 tables by total size;
- reclaim ~1-3 GB of disk per year from compaction.

## Non-Goals

FR-095 does not:

- delete data rows (that is handled by FR-093, FR-094, and FR-096);
- change any database schema, model, or migration;
- change any ranking signal, pipeline algorithm, or API endpoint;
- affect the nightly or weekly schedules;
- run on any cadence more frequent than quarterly.

## Math-Fidelity Note

### Operation 1 -- VACUUM FULL on Suggestion table

```sql
-- Locks table exclusively, rewrites it to a new file, drops the old file.
-- Reclaims space from deleted/superseded rows that plain VACUUM cannot.
-- Expected lock duration: 30-120 seconds depending on table size.
VACUUM FULL suggestions_suggestion;
```

**Space estimate:**
```
Suggestion table after 1 year:
  Active rows:     ~500,000 (current suggestions)
  Dead rows:       ~1,500,000 (superseded by 365 nightly pipeline runs)
  Row size:        ~2 KB average (score fields, diagnostics JSON, foreign keys)
  Table size:      ~4 GB (active + dead)
  After VACUUM FULL: ~1 GB (active only)
  Space reclaimed: ~3 GB
```

### Operation 2 -- REINDEX CONCURRENTLY on embedding indexes

```sql
-- Defragments HNSW/IVFFlat indexes without locking reads.
-- Builds a new index alongside the old one, then swaps atomically.
-- Typical size savings: 10-20% of index size.
REINDEX INDEX CONCURRENTLY content_contentitem_embedding_idx;
REINDEX INDEX CONCURRENTLY content_sentence_embedding_idx;
```

**Space estimate:**
```
content_contentitem_embedding_idx:
  Pages: ~50,000 vectors x 1024 dims x 4 bytes = ~200 MB data
  HNSW overhead: ~2x = ~400 MB total index size
  Fragmentation after 1 year: ~10-20% = 40-80 MB wasted
  After REINDEX: ~400 MB (clean)

content_sentence_embedding_idx:
  Sentences: ~500,000 vectors x 1024 dims x 4 bytes = ~2 GB data
  HNSW overhead: ~2x = ~4 GB total index size
  Fragmentation after 1 year: ~10-20% = 400-800 MB wasted
  After REINDEX: ~4 GB (clean)

Total index space reclaimed: ~440 MB - 880 MB
```

### Operation 3 -- Full entity re-extraction

```sql
-- Drop all entity edges (the walk graph connections between articles and entities)
TRUNCATE knowledge_graph_articleentityedge CASCADE;
-- Then: re-run entity extraction pipeline on all active ContentItems
```

**Volume estimate:**
```
Active ContentItems: ~50,000
Entities per page: ~10-30
ArticleEntityEdge rows before truncate: ~500,000 - 1,500,000
Re-extraction time: ~10-30 minutes on 4 Celery workers
New edge rows: ~500,000 - 1,500,000 (same volume, but accurate)
```

### Operation 4 -- Table bloat analysis (informational only)

```sql
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size,
       pg_size_pretty(pg_table_size(schemaname || '.' || tablename)) AS data_size,
       pg_size_pretty(pg_indexes_size(schemaname || '.' || tablename)) AS index_size
FROM pg_tables WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC
LIMIT 20;
```

This query does not modify any data. It logs a snapshot of the top 20 tables by total size (data + indexes) so the operator can track growth trends.

### Total yearly savings

```
VACUUM FULL (Suggestion table):    ~3 GB reclaimed per quarter x 4 = ~3 GB/year (net)
REINDEX (embedding indexes):       ~440-880 MB reclaimed per quarter x 4 = ~880 MB/year (net)
Entity re-extraction:              0 MB net (truncate + re-insert = same volume)
---
Total yearly savings:              ~1 - 3 GB reclaimed (not prevented -- compacts existing data)
```

### Schedule

```python
"quarterly-database-maintenance": {
    "task": "pipeline.quarterly_database_maintenance",
    "schedule": crontab(hour=3, minute=0, day_of_month=1, month_of_year="1,4,7,10"),
    "options": {"queue": "pipeline", "expires": 14400},
},
```

Runs on: January 1, April 1, July 1, October 1 at 03:00.

## Scope Boundary

FR-095 must stay separate from:

- **FR-093** (nightly retention) -- FR-093 deletes rows. FR-095 compacts tables and rebuilds indexes. Different operations on mostly different tables (except both touch `suggestions_suggestion` -- FR-093 deletes stale suggestions, FR-095 compacts the remaining ones).
- **FR-094** (weekly analytics pruning) -- FR-094 deletes rows from analytics tables and runs plain VACUUM ANALYZE. FR-095 runs VACUUM FULL (heavier, returns space to OS) on the Suggestion table only.
- **FR-096** (monthly safe prune) -- FR-096 deletes broken links, impact reports, and nulls out diagnostics JSON. FR-095 does not delete data -- it compacts and reindexes.
- **Nightly autovacuum** -- PostgreSQL's autovacuum runs plain VACUUM automatically. FR-095 does VACUUM FULL, which autovacuum never does because it requires an exclusive lock.

Hard rule: FR-095 must not delete any data rows. It only compacts, reindexes, re-extracts, and reports.

## Inputs Required

FR-095 uses only data already available:

- `backend/config/settings/base.py` -- beat schedule (modified to add quarterly entry)
- `backend/apps/pipeline/tasks.py` -- new `quarterly_database_maintenance` task
- The existing entity extraction pipeline -- reused for re-extraction
- PostgreSQL system catalog tables -- for the bloat analysis query

Explicitly disallowed inputs:

- No new models or migrations
- No new API endpoints
- No frontend changes

## Settings And Feature-Flag Plan

No new operator-facing settings. The quarterly schedule is controlled by the beat configuration.

To skip a quarter, the operator can revoke the task in the Celery admin or temporarily comment out the beat entry.

## Diagnostics And Explainability Plan

### Log output per run

```
[Quarterly Maint] VACUUM FULL suggestions_suggestion: 3.2 GB -> 1.1 GB (66% reduction, 94s lock)
[Quarterly Maint] REINDEX CONCURRENTLY content_contentitem_embedding_idx: 420 MB -> 380 MB (9.5% reduction)
[Quarterly Maint] REINDEX CONCURRENTLY content_sentence_embedding_idx: 4.1 GB -> 3.6 GB (12.2% reduction)
[Quarterly Maint] Entity re-extraction: truncated 1,200,000 edges, re-extracted 1,180,000 edges (28m 14s)
[Quarterly Maint] Table bloat report (top 5):
  suggestions_suggestion:          1.1 GB (data: 900 MB, indexes: 200 MB)
  content_contentitem:             2.4 GB (data: 800 MB, indexes: 1.6 GB)
  analytics_gscdailyperformance:   340 MB (data: 120 MB, indexes: 220 MB)
  knowledge_graph_articleentityedge: 280 MB (data: 180 MB, indexes: 100 MB)
  content_sentence:                4.2 GB (data: 600 MB, indexes: 3.6 GB)
[Quarterly Maint] Complete. Total time: 34m 22s.
```

### Operator alert

If VACUUM FULL lock duration exceeds 300 seconds (5 minutes), the task creates an OperatorAlert with severity `warning` so the operator can investigate table growth.

## Storage / Model / API Impact

### Suggestion model

No changes.

### Content model

No changes.

### Knowledge graph models

No schema changes. The `ArticleEntityEdge` table is truncated and repopulated, but its schema is unchanged.

### Migrations

No new migrations.

### Backend API

No changes.

### Frontend

No changes.

### Beat schedule

One new entry in `CELERY_BEAT_SCHEDULE` in `settings/base.py`.

## Backend Service Touch Points

Implementation files:

- `backend/config/settings/base.py` -- add quarterly beat schedule entry
- `backend/apps/pipeline/tasks.py` -- add `quarterly_database_maintenance` task with VACUUM FULL, REINDEX, entity re-extraction, and bloat report

Files that must stay untouched:

- All model files (no schema changes)
- All ranking, scoring, and signal files
- All frontend files
- The existing nightly and weekly tasks

## Test Plan

### 1. VACUUM FULL reduces table size

- Insert 100,000 rows into `suggestions_suggestion`, then delete 80,000.
- Run `quarterly_database_maintenance`.
- Verify `pg_total_relation_size('suggestions_suggestion')` decreased by approximately 80%.

### 2. REINDEX CONCURRENTLY rebuilds indexes

- Verify `content_contentitem_embedding_idx` exists before and after the task.
- Verify the index is usable (run an approximate nearest-neighbor query before and after).
- Verify no read queries are blocked during REINDEX.

### 3. Entity re-extraction completeness

- Count `ArticleEntityEdge` rows before the task.
- Run `quarterly_database_maintenance`.
- Verify `ArticleEntityEdge` rows after re-extraction are within 10% of the pre-truncate count (some variance is expected if pages changed).
- Verify no active `ContentItem` is missing entity edges.

### 4. Bloat report logged

- Run `quarterly_database_maintenance`.
- Verify log output contains the top 20 tables with `total_size`, `data_size`, and `index_size` columns.

### 5. Lock duration alert

- Mock VACUUM FULL to take 310 seconds.
- Verify an OperatorAlert is created with severity `warning`.

### 6. Schedule correctness

- Verify the beat schedule fires on January 1, April 1, July 1, and October 1.
- Verify it does not fire on any other day.

## Risk List

- VACUUM FULL takes an exclusive lock on the Suggestion table for 30-120 seconds. During this time, no reads or writes to the table are possible. Mitigation: the task runs at 03:00 when traffic is near zero. The lock duration is logged and alerts fire if it exceeds 5 minutes.
- REINDEX CONCURRENTLY temporarily doubles the index's disk usage (old + new index coexist during rebuild). Mitigation: the embedding indexes are 400 MB and 4 GB; the server needs at least 4.4 GB free disk during the operation.
- Entity re-extraction TRUNCATES the edge table, causing a brief window where graph walk candidates have no backing data. Mitigation: the nightly pipeline runs hours later and will use the freshly re-extracted edges. If the pipeline runs during re-extraction, it falls back to cached walk candidates (FR-092).
- If the quarterly task fails midway (e.g., VACUUM FULL succeeds but REINDEX fails), the task logs the error and continues. Partial completion is acceptable -- each operation is independent.
