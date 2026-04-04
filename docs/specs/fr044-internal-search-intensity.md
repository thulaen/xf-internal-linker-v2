# FR-044 - Internal Search Intensity Signal

## Confirmation

- `FR-044` is a new backlog item being added to `FEATURE-REQUESTS.md` in this session.
- Repo confirmed:
  - no current ranking signal uses aggregate on-site search-box demand;
  - `FR-016` and `FR-018` collect behaviour and attribution telemetry, but they do not transform internal-search demand into a destination ranking feature;
  - `FR-019` discusses query-demand style alerting, but not destination scoring;
  - the repo already uses Matomo, which provides a practical future source for internal Site Search aggregates.

## Current Repo Map

### Existing nearby behaviour signals

- `FR-016` telemetry
  - records attribution and user-behaviour evidence;
  - it does not score destinations from search-box demand.

- `FR-018` statistical brain
  - is about learning from observed outcomes;
  - it does not introduce a direct "what users are searching for right now" signal.

- `FR-019` alerts
  - can surface demand changes to operators;
  - it does not modify destination ranking.

### Gap this FR closes

The repo cannot currently boost pages that match topics users are actively searching for inside the site right now.

That means the linker cannot react to short-term surges in demand for specific entities, products, bugs, locations, or announcements even when the site itself is clearly signaling that demand through search activity.

## Source Summary

### Product basis: Matomo Site Search

Plain-English read:

- Matomo tracks the search keywords visitors use in a site's internal search engine;
- it also tracks pages viewed after a search;
- those reports expose what users are trying to find and whether they find it.

Repo-safe takeaway:

- the repo already has a natural future data source for internal-search demand;
- the useful raw facts are search keyword counts, no-result counts, and post-search destination views;
- v1 can start with keyword volume alone and add richer attribution later.

### Math basis: Kleinberg burst detection

Plain-English read:

- burst detection treats sudden rises in event frequency as evidence of heightened interest;
- a topic is more important when recent frequency rises above its normal baseline;
- the important concept is relative lift above baseline, not just raw count.

Repo-safe takeaway:

- internal-search intensity should reward both volume and unusualness;
- a topic searched 30 times when it usually gets 2 searches matters more than a topic searched 30 times when it usually gets 28.

### Patent inspiration: US20050102259A1 - Search query processing using trend analysis

Plain-English read:

- the patent uses trend dimensions over query histories to influence retrieval and suggestion behaviour;
- changing query interest over time is treated as machine-usable ranking evidence.

Repo-safe takeaway:

- a trend-aware internal-search signal is patent-aligned and product-reasonable;
- the repo can adapt that idea locally without copying external-search infrastructure.

## Plain-English Summary

Simple version first.

If lots of users are searching for a topic inside the site right now, pages about that topic should become slightly stronger link targets.

Examples:

- a product model that suddenly gets many searches after a release;
- an error code users are urgently trying to fix;
- a city, venue, or event getting a temporary spike in attention.

FR-044 turns that search demand into a bounded ranking signal.

## Problem Statement

Today the ranker mostly evaluates pages by static content and historical behaviour. It cannot react to fresh, site-local demand visible in the site's own search box.

FR-044 adds a bounded internal-search intensity signal so destinations can receive a modest boost when they match currently elevated search demand.

## Goals

FR-044 should:

- add a separate, explainable signal based on aggregate internal-search demand;
- reward topics with both meaningful recent volume and meaningful lift above baseline;
- remain privacy-safe by using aggregate counts only;
- stay neutral when no search telemetry exists;
- fit the repo's existing analytics and settings architecture.

## Non-Goals

FR-044 does not:

- use per-user or personally identifying search history;
- replace `FR-016`, `FR-018`, or `FR-019`;
- require live-streaming analytics in v1;
- rewrite destination titles or anchors;
- infer intent from external search engines.

## Data Inputs

### Proposed aggregate table

Add a new daily aggregate model:

```python
class SiteSearchQueryDaily(models.Model):
    query = models.CharField(max_length=255, db_index=True)
    day = models.DateField(db_index=True)
    search_count = models.IntegerField(default=0)
    no_result_count = models.IntegerField(default=0)
    source = models.CharField(max_length=32, default="matomo")
```

This table stores only aggregate counts.

No user identifier, session identifier, or raw IP address is stored here.

### Future data sources

Initial target:

- Matomo Site Search daily reports

Possible later sources:

- native XenForo search logs aggregated into daily counts
- WordPress search plugin aggregates

## Math-Fidelity Note

### Step 1 - collect recent versus baseline counts

For each normalized query `q`:

- `recent_count(q)` = total searches over the last `recent_days`
- `baseline_count(q)` = total searches over the prior `baseline_days`
- `baseline_mean(q) = baseline_count(q) / baseline_days`

Defaults:

- `recent_days = 3`
- `baseline_days = 28`

### Step 2 - compute burst-aware query intensity

Use additive smoothing to avoid divide-by-zero spikes:

```text
lift(q) = (recent_count(q) + 1.0) / (baseline_mean(q) + 1.0)
volume(q) = log(1.0 + recent_count(q))
query_intensity_raw(q) = volume(q) * lift(q)
```

Interpretation:

- `volume` rewards topics with real search volume;
- `lift` rewards topics whose recent demand is unusually high versus normal.

### Step 3 - normalize across active queries

Across queries seen in the active window:

```text
query_intensity_norm(q) =
    query_intensity_raw(q) / max_query_intensity_raw
```

Fallback:

- if there are no active queries, there is no signal.

### Step 4 - match active queries to each destination

For each destination `d`, compute overlap against the destination title and body tokens using the repo's existing tokenizer.

Definitions:

```text
title_overlap(d, q) =
    matched_query_tokens_in_title / max(query_token_count, 1)

body_overlap(d, q) =
    matched_query_tokens_in_body / max(query_token_count, 1)
```

Weighted match:

```text
query_match(d, q) =
    0.7 * title_overlap(d, q) + 0.3 * body_overlap(d, q)
```

### Step 5 - derive destination-level raw intensity

For each destination:

```text
destination_raw(d) =
    max over active q of (query_intensity_norm(q) * query_match(d, q))
```

Optional later extension:

- use the top 3 matching queries instead of only the max if operators want broader coverage.

### Final bounded score

```text
internal_search_intensity_score =
    0.5,                                if no active queries or no telemetry
    0.5 + 0.5 * destination_raw(d),     otherwise
```

Interpretation:

- `0.5` = neutral
- `1.0` = destination strongly matches the most search-intense active query

## Proposed Data Model

### New field on `ContentItem`

Add:

```python
internal_search_intensity_score = models.FloatField(
    null=True,
    blank=True,
    default=None,
    help_text="Bounded internal search intensity score in [0.5, 1.0].",
)
```

### New fields on `Suggestion`

Add:

```python
score_internal_search_intensity = models.FloatField(
    null=True,
    blank=True,
    default=None,
    help_text="Bounded internal-search intensity score copied from destination analysis.",
)

internal_search_diagnostics = models.JSONField(
    null=True,
    blank=True,
    default=None,
    help_text="Internal-search diagnostics for reviewer and operator inspection.",
)
```

### Suggested diagnostics shape

```json
{
  "matched_query": "oled burn in fix",
  "recent_count": 37,
  "baseline_mean": 4.21,
  "lift": 7.29,
  "query_intensity_norm": 0.92,
  "title_overlap": 0.75,
  "body_overlap": 1.0,
  "query_match": 0.825,
  "destination_raw": 0.759
}
```

## Ranking Hook

This is an additive boost signal.

### Default-safe rule

- compute and store the score;
- keep `internal_search.ranking_weight = 0.0` by default;
- do not alter ordering until operators validate the signal.

### When enabled

Convert the bounded score to a `0..1` component:

```text
internal_search_component =
    max(0.0, min(1.0, 2.0 * (score_internal_search_intensity - 0.5)))
```

Then:

```text
score_final =
    score_final + (internal_search.ranking_weight * internal_search_component)
```

Default:

- `internal_search.ranking_weight = 0.0`

## Settings Contract

Add new settings:

```json
{
  "internal_search": {
    "enabled": true,
    "ranking_weight": 0.0,
    "recent_days": 3,
    "baseline_days": 28,
    "max_active_queries": 200,
    "min_recent_count": 3
  }
}
```

Rules:

- ignore queries with `recent_count < min_recent_count`;
- keep only the top `max_active_queries` by `query_intensity_raw` for scoring;
- if telemetry is missing or stale, return neutral `0.5`.

## Pipeline Placement

### Stage 1 - analytics aggregation

Import or aggregate daily site-search counts into `SiteSearchQueryDaily`.

### Stage 2 - destination enrichment

During pipeline setup, compute the active query-intensity table once and score each destination against it.

### Stage 3 - suggestion assembly

Copy the destination score and diagnostics onto each `Suggestion`.

### Hard boundaries

- no per-user query histories in the ranking path;
- no direct dependency on live search APIs during a suggestion run;
- no cross-contamination with `FR-016` attribution event logs.

## Backend Touch Points

- `backend/apps/analytics/models.py`
  - add `SiteSearchQueryDaily`

- `backend/apps/analytics/migrations/`
  - add schema migration

- `backend/apps/analytics/`
  - add importer or aggregation task for Matomo Site Search daily data

- `backend/apps/content/models.py`
  - add `internal_search_intensity_score`

- `backend/apps/pipeline/models.py`
  - add suggestion score + diagnostics fields

- `backend/apps/pipeline/services/`
  - add the destination scoring logic

- `backend/apps/api/`
  - expose settings and diagnostics in existing ranking/settings endpoints

- `frontend/src/app/settings/`
  - add enable toggle and weight slider in the advanced ranking section

## Native Runtime Plan

Per `docs/NATIVE_RUNTIME_POLICY.md`:

- Python reference implementation first;
- optional hot-path native scorer later at `backend/extensions/internalsearch.cpp`;
- analytics import remains outside the native layer.

Reuse the existing diagnostics surfaces rather than adding a new operator-only subsystem.

## Verification Plan

### Unit tests

- query with low baseline and high recent count produces higher intensity than steady-volume query
- destination with strong title/body overlap scores above weakly matching destination
- missing telemetry returns neutral `0.5`
- low-volume query below `min_recent_count` is ignored

### Integration tests

- Matomo aggregate import populates `SiteSearchQueryDaily`
- pipeline computes `internal_search_intensity_score` deterministically from those aggregates
- suggestions copy score + diagnostics correctly
- `ranking_weight = 0.0` leaves ordering unchanged
- enabling the weight modestly promotes destinations matching active high-demand queries

## Rollout Guidance

Recommended rollout:

1. land daily aggregate storage and importer
2. compute scores in shadow mode with `ranking_weight = 0.0`
3. review which queries are being matched and whether they produce noisy boosts
4. add no-result query diagnostics later if operators want gap-detection features

## Acceptance Criteria

FR-044 is complete when:

- the repo can store aggregate internal-search query counts by day;
- destinations can receive a bounded internal-search intensity score from those aggregates;
- suggestions expose score and diagnostics;
- the signal runs safely in shadow mode by default and becomes additive only when operators enable its weight.
