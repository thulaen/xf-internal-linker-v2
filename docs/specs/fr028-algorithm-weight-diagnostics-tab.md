# FR-028 - Algorithm Weight Diagnostics Tab

## Confirmation

- `FR-028` is a real backlog item in `FEATURE-REQUESTS.md`.
- It is queued for `Phase 31`.
- This spec is written before implementation because the user explicitly requested the build blueprint in advance.
- Repo confirmed:
  - `ranker.py` contains 16 named scoring signals contributing to `score_final`;
  - FR-021 adds 7 value model signals in a pre-ranking pass;
  - every signal has configurable weights stored in `AppSetting`;
  - `ErrorLog` already stores background job failures per `job_type`;
  - no single view exists today showing all signals together with their enabled state, weights, storage footprint, errors, and live settings;
  - `pg_total_relation_size()` is available in PostgreSQL for per-table byte counts;
  - `Suggestion` rows store per-signal diagnostic JSON for every suggestion.

## Scope Statement

This FR adds one new tab — **Diagnostics** — to the existing Settings page in Angular.

It contains one card per scoring signal. Each card answers four questions at a glance:

1. **Running?** — is the signal enabled, and is its weight above zero?
2. **Space used?** — how many rows and bytes does this signal's data occupy in the database?
3. **Errors?** — has this signal's computation task logged a recent error?
4. **Settings?** — what values are the configurable parameters set to right now?
5. **C++ active?** — is the compiled fast path running right now?
6. **Fallback used?** — did the signal fall back to Python instead?
7. **Helping?** — is the C++ path giving a real speed benefit, or not enough to matter?

**Hard boundaries:**

- This FR is read-only. It does not add any new settings controls.
- It does not modify any signal computation, ranking formula, or weight.
- Existing settings cards (one per FR) are not changed.
- `score_final` and all signal computations are unchanged.

## Current Repo Map

### All scoring signals (from `ranker.py` and FR-021)

#### `score_final` signals (16 total)

| # | Signal key | FR | Ranking weight param | Default |
|---|---|---|---|---|
| 1 | `semantic` | core | `w_semantic` | 0.6 |
| 2 | `keyword` | core | `w_keyword` | 0.15 |
| 3 | `node_affinity` | core | `w_node` | 0.1 |
| 4 | `quality` | core | `w_quality` | 0.15 |
| 5 | `weighted_authority` | FR-006 | `weighted_authority_ranking_weight` | 0.0 |
| 6 | `link_freshness` | FR-007 | `link_freshness_ranking_weight` | 0.0 |
| 7 | `phrase_relevance` | FR-008 | `phrase_matching_settings.ranking_weight` | 0.0 |
| 8 | `learned_anchor` | FR-009 | `learned_anchor_settings.ranking_weight` | 0.0 |
| 9 | `rare_term_propagation` | FR-010 | `rare_term_settings.ranking_weight` | 0.0 |
| 10 | `field_aware_relevance` | FR-011 | `field_aware_settings.ranking_weight` | 0.0 |
| 11 | `ga4_gsc` | FR-016/R | `ga4_gsc_ranking_weight` | 0.0 |
| 12 | `click_distance` | FR-012 | `click_distance_ranking_weight` | 0.0 |
| 13 | `silo_affinity` | FR-005 | `same_silo_boost` / `cross_silo_penalty` | 0.0 / 0.0 |
| 14 | `cluster_suppression` | FR-014 | `suppression_penalty` | 0.5 |
| 15 | `explore_exploit` | FR-013 | internal feedback reranker | 0.0 |
| 16 | `slate_diversity` | FR-015 | diversity reranker weight | 0.0 |

#### FR-021 value model signals (7 total, pre-ranking pass)

| # | Signal key | FR | Weight param | Default |
|---|---|---|---|---|
| 1 | `vm_relevance` | FR-021 | `w_relevance` | 0.4 |
| 2 | `vm_traffic` | FR-021/FR-023 | `w_traffic` | 0.3 |
| 3 | `vm_freshness` | FR-021 | `w_freshness` | 0.1 |
| 4 | `vm_authority` | FR-021 | `w_authority` | 0.1 |
| 5 | `vm_engagement` | FR-024 | `w_engagement` | 0.1 |
| 6 | `vm_cooccurrence` | FR-025 | `w_cooccurrence` | 0.15 |
| 7 | `vm_penalty` | FR-021 | `w_penalty` | 0.5 |

### Data sources for each card

- **Weights / settings**: `AppSetting` rows via existing settings APIs.
- **Storage**: PostgreSQL `pg_total_relation_size()` per table.
- **Errors**: `ErrorLog` rows filtered by `job_type` for the relevant background task.
- **Signal coverage and average value**: aggregated from `Suggestion` score columns and diagnostic JSON fields.
- **Last computation timestamp**: `AppSetting` rows that store `_last_run_at` or `_last_built_at` keys.

### Existing settings APIs (read — not modified)

Every signal already has a `GET /api/settings/<signal>/` endpoint. The diagnostics endpoint calls these internally or reads `AppSetting` directly.

## Problem Definition

Simple version first.

There are 23 scoring signals across two layers of the pipeline. Each one has its own settings page, its own database tables, and its own background task. Today there is no single place to see all of them at once. If a signal's weight is accidentally set to zero, or its background task silently stopped running, or its data table ballooned in size, there is no way to know without opening each settings card individually.

The Diagnostics tab puts all 23 signals on one screen. One glance tells the operator what is active, what is taking up space, and what has errors.

For C++-accelerated ranking signals, one glance must also tell the operator whether C++ is active, whether Python fallback is being used, and whether the fast path is actually helping.

---

## Backend Design

### New backend app

Add: `backend/apps/diagnostics/`

Files:

- `backend/apps/diagnostics/views.py`
- `backend/apps/diagnostics/services.py`
- `backend/apps/diagnostics/serializers.py`
- `backend/apps/diagnostics/urls.py`

### Data model for a single signal card

No new DB model is needed. Everything is read from existing tables.

```python
@dataclass
class SignalDiagnostic:
    signal_key: str           # e.g. "weighted_authority"
    display_name: str         # e.g. "Weighted Link Graph Authority"
    fr_reference: str         # e.g. "FR-006"
    layer: str                # "score_final" or "value_model"
    enabled: bool             # signal is configured on (not just weight > 0)
    ranking_weight: float     # current weight value
    weight_is_active: bool    # weight > 0.0 (signal actually affects score_final)
    settings: dict            # all configurable params and their current values
    storage: list[TableStorage]  # per-table row count and byte size
    total_storage_bytes: int
    last_computation_at: datetime | None
    last_error_message: str | None
    last_error_at: datetime | None
    signal_coverage_pct: float | None  # % of recent suggestions with non-fallback value
    avg_signal_value: float | None     # mean score across recent suggestions
    recent_diagnostics_sample: dict    # latest diagnostics JSON from one recent suggestion
    cpp_runtime_status: str | None     # "C++ ACTIVE", "PYTHON FALLBACK", "C++ NOT HELPING"
    cpp_status_reason: str | None      # plain-English explanation for operators
    cpp_fallback_used_recently: bool | None
    cpp_speedup_ratio: float | None    # optional benchmark ratio, >1 means C++ faster

@dataclass
class TableStorage:
    table_name: str
    row_count: int
    size_bytes: int
    size_human: str           # e.g. "12.3 MB"
```

### Storage queries

Use PostgreSQL system functions. Run at request time (or cached for 5 minutes):

```sql
SELECT
    relname AS table_name,
    n_live_tup AS row_count,
    pg_total_relation_size(relid) AS size_bytes
FROM pg_stat_user_tables
WHERE relname = ANY(%s);
```

Per-signal table registry (which tables belong to which signal):

| Signal | Tables |
|---|---|
| `semantic` | `pipeline_pipelinerun`, `pipeline_sentence` (embedding vectors) |
| `keyword` | *(tokens stored in-memory, no dedicated table)* |
| `node_affinity` | `sync_scopeitem` |
| `quality` | `graph_existinglink` |
| `weighted_authority` | `graph_existinglink`, `content_contentitem` (pagerank column) |
| `link_freshness` | `graph_linkfreshnessedge` |
| `phrase_relevance` | *(computed at pipeline time, no dedicated table)* |
| `learned_anchor` | `pipeline_learnedanchorvocabulary` (or equivalent) |
| `rare_term_propagation` | `pipeline_raretermprofile` (or equivalent) |
| `field_aware_relevance` | *(computed at pipeline time, no dedicated table)* |
| `ga4_gsc` | `analytics_searchmetric`, `content_contentitem` (content_value_score) |
| `click_distance` | `pipeline_clickdistancescore` (or equivalent) |
| `silo_affinity` | `content_silogroup`, `content_scopeitem` |
| `cluster_suppression` | `content_contentcluster` |
| `explore_exploit` | `pipeline_feedbackrerank` (or equivalent) |
| `slate_diversity` | *(computed at pipeline time, no dedicated table)* |
| `vm_traffic` | `analytics_searchmetric` |
| `vm_cooccurrence` | `cooccurrence_sessioncooccurrencepair` (FR-025) |
| `knowledge_graph` | `knowledge_graph_entitynode`, `knowledge_graph_articleentityedge` |

Note: the AI implementing this FR must verify exact table names against the live migration files, as they may differ slightly from the names above.

### Signal coverage query

For each signal that has a dedicated score column on `Suggestion`, compute coverage as the percentage of recent suggestions where the signal returned a non-fallback value (i.e. not exactly 0.5 for signals with 0.5 fallback, or not 0.0 for signals with 0.0 default).

```sql
SELECT
    COUNT(*) FILTER (WHERE score_phrase_relevance != 0.0)::float
    / NULLIF(COUNT(*), 0) * 100 AS phrase_coverage_pct,
    AVG(score_phrase_relevance) AS phrase_avg
FROM suggestions_suggestion
WHERE created_at > NOW() - INTERVAL '7 days';
```

Run per-signal for the past 7 days of suggestions.

### Last error query

```sql
SELECT error_message, created_at
FROM audit_errorlog
WHERE job_type = %s
ORDER BY created_at DESC
LIMIT 1;
```

Each signal maps to the `job_type` string used by its background task:

| Signal | job_type |
|---|---|
| `weighted_authority` | `recalculate_pagerank` |
| `link_freshness` | `recalculate_link_freshness` |
| `ga4_gsc` | `sync_analytics` |
| `click_distance` | `recalculate_click_distance` |
| `cluster_suppression` | `cluster_content` |
| `explore_exploit` | `feedback_rerank` |
| `knowledge_graph` | `build_entity_graph` |
| `vm_cooccurrence` | `compute_session_cooccurrence` |
| *(pipeline-time signals)* | `run_pipeline` |

### REST API

Add one endpoint:

```
GET /api/diagnostics/weights/
```

Returns:

```json
{
  "generated_at": "2026-03-28T15:00:00Z",
  "score_final_signals": [ ... array of SignalDiagnostic ... ],
  "value_model_signals": [ ... array of SignalDiagnostic ... ],
  "summary": {
    "total_signals": 23,
    "active_signals": 8,
    "signals_with_errors": 1,
    "total_storage_bytes": 45678901,
    "total_storage_human": "43.6 MB"
  }
}
```

Response is cached for 5 minutes (configurable). A `?refresh=true` query param busts the cache and re-runs all queries.

Single signal card example:

```json
{
  "signal_key": "weighted_authority",
  "display_name": "Weighted Link Graph Authority",
  "fr_reference": "FR-006",
  "layer": "score_final",
  "enabled": true,
  "ranking_weight": 0.2,
  "weight_is_active": true,
  "settings": {
    "weighted_authority_ranking_weight": 0.2,
    "pagerank_damping_factor": 0.85,
    "pagerank_iterations": 50,
    "recalculation_schedule": "weekly"
  },
  "storage": [
    {
      "table_name": "graph_existinglink",
      "row_count": 45230,
      "size_bytes": 12345678,
      "size_human": "11.8 MB"
    }
  ],
  "total_storage_bytes": 12345678,
  "total_storage_human": "11.8 MB",
  "last_computation_at": "2026-03-27T02:15:00Z",
  "last_error_message": null,
  "last_error_at": null,
  "signal_coverage_pct": 94.2,
  "avg_signal_value": 0.42,
  "cpp_runtime_status": "C++ ACTIVE",
  "cpp_status_reason": "C++ extension loaded and faster than Python on recent batches.",
  "cpp_fallback_used_recently": false,
  "cpp_speedup_ratio": 2.8,
  "recent_diagnostics_sample": {
    "pagerank_score": 0.0034,
    "normalized_score": 0.42,
    "pagerank_min": 0.0001,
    "pagerank_max": 0.091
  }
}
```

---

## Frontend Design

### New tab on the Settings page

Add a **Diagnostics** tab to the existing `SettingsComponent` tab group.

Route: `/settings` with `tab=diagnostics` query param (or Angular Material tab index).

### Page layout

**Top summary bar:**

```
23 signals total   |   8 active   |   1 error   |   43.6 MB total storage
                                            [Refresh]
```

**Two sections:**

1. **Pipeline Signals** — the 16 `score_final` signals.
2. **Value Model Signals** — the 7 FR-021 pre-ranking signals.

Each section is a responsive grid of signal cards.

### Signal card design

Each card shows:

```
┌─────────────────────────────────────────────────────┐
│  [●] ACTIVE   Weighted Link Graph Authority   FR-006 │
│  ──────────────────────────────────────────────────  │
│  Weight: 0.20          Coverage: 94.2%               │
│  Avg value: 0.42       Last run: 18 hours ago        │
│  C++: ACTIVE           Speedup: 2.8x                 │
│  Reason: C++ loaded and faster on recent runs        │
│                                                      │
│  Storage: 11.8 MB across 1 table (45,230 rows)       │
│                                                      │
│  [▼ View current settings]                           │
└─────────────────────────────────────────────────────┘
```

**Status badge variants:**

| State | Badge | Condition |
|---|---|---|
| Active | `● ACTIVE` (green) | enabled = true AND weight > 0 |
| Enabled, no weight | `○ ENABLED` (blue) | enabled = true AND weight = 0 |
| Disabled | `✕ DISABLED` (grey) | enabled = false |
| Error | `⚠ ERROR` (red) | last_error_message is not null |
| Not yet built | `– NOT BUILT` (amber) | last_computation_at is null |
| C++ active | `⚡ C++ ACTIVE` (green) | compiled extension loaded and used |
| Python fallback | `↺ PYTHON FALLBACK` (amber) | Python path used instead of C++ |
| C++ not helping | `◌ C++ NOT HELPING` (blue) | C++ exists but no meaningful speed benefit is seen |

A signal can be both `ACTIVE` and have an `ERROR` badge — show both.
A signal with a C++ accelerator can also show one C++ runtime badge at the same time.

**Expandable settings panel:**

Clicking "View current settings" expands a read-only key-value list of every configurable parameter for that signal, pulled from the API response. Each key is shown in human-readable form.

Example for Phrase Matching (FR-008):

```
Ranking weight:          0.15
Min phrase length:       3
Max phrase length:       8
Exact match bonus:       0.3
Partial match threshold: 0.6
Enabled:                 Yes
```

**No edit controls** — this tab is read-only. To change a setting, the user goes to the signal's own settings card in the normal settings page.

**Link to signal settings:**

Each card has a "Go to settings →" link that navigates to the relevant settings tab/card.

### Error state

When `last_error_message` is not null, the card gains a red left border and shows:

```
⚠ Last error: 2026-03-26T09:12:00Z
  "Embedding job failed: model not loaded"
  [View in Error Log →]
```

"View in Error Log" navigates to `/alerts` filtered to that signal's error events.

### Signals not yet implemented

For signals belonging to FRs not yet built (e.g. FR-021 value model signals before FR-021 lands), the card shows:

```
– NOT BUILT
This signal is specced but not yet implemented.
Available from: FR-021 (Phase 24)
```

This is determined by checking whether the expected `AppSetting` key exists.

### Storage size formatting

```
< 1 KB     → "< 1 KB"
1 KB–1 MB  → "X.X KB"
1 MB–1 GB  → "X.X MB"
> 1 GB     → "X.X GB"
```

Zero storage (pipeline-time computed signals with no dedicated table) shows:

```
Storage: computed at pipeline time — no dedicated table
```

### Refresh behaviour

- Page loads with a cached response (up to 5 minutes old).
- "Refresh" button calls `GET /api/diagnostics/weights/?refresh=true`.
- A spinner shows while refreshing.
- Last refreshed timestamp shown in the summary bar.
- Auto-refreshes every 5 minutes while the tab is open.

---

## Settings API

Add to `GET /api/settings/diagnostics/` (new):

- `cache_ttl_seconds` (int, default: `300`) — how long to cache the diagnostics response.
- `coverage_lookback_days` (int, default: `7`) — how many days of suggestions to use for coverage and average calculations.
- `error_lookback_days` (int, default: `30`) — how far back to look in `ErrorLog` for signal errors.

---

## Test Plan

### Backend tests

- `GET /api/diagnostics/weights/` returns a card for every registered signal.
- A signal with `ranking_weight = 0.0` has `weight_is_active = false`.
- A signal with a recent `ErrorLog` row shows correct `last_error_message` and `last_error_at`.
- A signal with no `ErrorLog` row shows `last_error_message = null`.
- Storage query returns correct bytes for a known table.
- `?refresh=true` bypasses the cache and re-runs queries.
- `signal_coverage_pct` is `null` when there are no suggestions in the lookback window.
- Cards for not-yet-implemented signals show `enabled = false` and `last_computation_at = null`.

### Frontend tests

- All 23 signal cards render.
- `ACTIVE` badge shown when weight > 0 and enabled.
- `ERROR` badge shown when `last_error_message` is not null.
- `NOT BUILT` badge shown when signal has no `AppSetting` key.
- Expandable settings panel opens and shows key-value pairs.
- "Go to settings →" link navigates to correct settings tab.
- Refresh button triggers the `?refresh=true` request.
- Summary bar shows correct active count and error count.

### Manual verification

- Set `weighted_authority_ranking_weight = 0.0` — card shows `ENABLED` not `ACTIVE`.
- Seed an `ErrorLog` row for `recalculate_pagerank` — card shows `ERROR` badge with message.
- Open page — confirm storage sizes are plausible for the current DB state.
- Click "View current settings" on phrase matching — confirm all FR-008 parameters shown.

---

## Dependencies

- No other FR is required before this one can be built.
- The tab gracefully shows `NOT BUILT` for signals belonging to future FRs (FR-021 through FR-027).
- FR-019 (Operator alerts) — "View in Error Log" links use the FR-019 `/alerts` page; if FR-019 is not yet implemented, the link is omitted.

---

## Acceptance Criteria

- A Diagnostics tab exists on the Settings page.
- Every registered scoring signal has a card.
- Each card correctly shows: enabled state, weight, active state, storage size and row count, last computation time, last error (if any), signal coverage %, and average value.
- Expandable settings panel shows all current configurable parameters for each signal.
- Summary bar shows total signals, active count, error count, and total storage.
- Read-only — no editing from this tab.
- Refresh button re-fetches live data.
- Cards for not-yet-built signals show a clear "not implemented yet" state.

---

## Out-of-Scope Follow-Up

- Inline weight editing from this tab (belongs to each signal's own settings card).
- Historical weight change timeline (belongs to FR-018 auto-tuning history).
- Per-signal performance benchmarks (computation time, memory usage).
- Signal correlation analysis (how correlated are the signal values across suggestions).
- Export diagnostics to CSV or JSON for offline analysis.
