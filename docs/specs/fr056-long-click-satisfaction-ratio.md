# FR-056 - Long-Click Satisfaction Ratio

## Confirmation

- **Backlog confirmed**: `FR-056 - Long-Click Satisfaction Ratio` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No dwell-time or session-duration-based satisfaction signal exists in the current ranker. The closest existing signal is engagement read-through rate (FR-024), which measures scroll depth. FR-056 measures whether users *stay* on the destination page (satisfaction) or *bounce back* quickly (disappointment) — a fundamentally different behavioral axis.
- **Repo confirmed**: GA4 session data is already ingested into the system via the analytics pipeline. Session timestamps and page-view durations are available per destination page.

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - `value_model.w_engagement` (FR-024) — measures scroll depth and read-through rate.
  - `value_model.w_cooccurrence` (FR-025) — measures whether pages appear in the same session.
  - No signal currently measures dwell-time-based satisfaction (long clicks vs short clicks).

- `backend/apps/analytics/` (or equivalent GA4 data pipeline)
  - GA4 session data with page-view timestamps is already ingested.
  - Session duration per page can be derived from sequential page_view events.

### Storage and settings patterns already available

- `backend/apps/suggestions/models.py` — separate `FloatField` + `JSONField` per feature signal.
- `backend/apps/core/views.py` — per-feature settings endpoints pattern.
- `backend/apps/suggestions/views.py` — `PipelineRun.config_snapshot` pattern.

## Source Summary

### Patent: US10229166B1 — Modifying Search Result Ranking Based on Implicit User Feedback

**Plain-English description of the patent:**

The patent describes a system that uses implicit user feedback signals — specifically the time users spend on a page after clicking a search result — to modify ranking. A "long click" (user stays on the page for 30+ seconds) is treated as a signal of satisfaction. A "short click" (user returns to the search results within a few seconds) is treated as a signal of disappointment. The ratio of long clicks to total clicks becomes a quality signal.

**Repo-safe reading:**

The patent is search-result-oriented. This repo adapts the idea to internal linking: if users who arrive at a destination page via internal links tend to stay (long dwell time), that destination is satisfying. If they tend to bounce quickly, it is not. The reusable core idea is:

- count sessions where the user stayed on the destination for 30+ seconds (long clicks);
- count sessions where the user left within 10 seconds (short clicks);
- the ratio of long clicks to total clicks is a satisfaction indicator;
- Laplace smoothing handles cold-start pages with few sessions.

**What is directly supported by the patent:**

- using dwell time thresholds to classify clicks as long or short;
- computing a satisfaction ratio from these counts;
- using the ratio as a ranking signal.

**What is adapted for this repo:**

- "search result clicks" map to internal link traversals visible in GA4 session data;
- dwell time is estimated from the time gap between sequential page_view events in a session;
- Laplace smoothing (pseudocounts) replaces the patent's ML-based cold-start handling.

## Plain-English Summary

Simple version first.

When a reader clicks an internal link and arrives at the destination page, one of two things typically happens: they stay and read (good — the link was useful) or they leave almost immediately (bad — the link was disappointing).

FR-056 counts how often each of these happens for each destination page. If most visitors stay for 30+ seconds, the page has a high satisfaction ratio. If most visitors leave within 10 seconds, the page has a low satisfaction ratio.

This is different from engagement read-through rate (which measures how far people scroll) and from session co-occurrence (which measures whether pages are visited together). FR-056 asks a simpler question: "when people get to this page, are they happy they went there?"

Pages with many satisfied visitors (long dwells) are better link destinations than pages that people consistently abandon.

## Problem Statement

Today the ranker uses scroll depth (FR-024) and co-occurrence (FR-025) as behavioral signals. Neither directly measures *user satisfaction* — whether the reader found what they wanted on the destination page.

Scroll depth can be high for a page that the reader scrolls through quickly looking for an answer without finding it. Co-occurrence measures that pages were visited together but not whether the visit was satisfying.

FR-056 closes this gap with a direct satisfaction proxy: the ratio of long, engaged visits to short, bounced visits.

## Goals

FR-056 should:

- add a separate, explainable, bounded long-click satisfaction signal;
- count long-click sessions (30+ seconds on page) and short-click sessions (<10 seconds);
- compute a Laplace-smoothed satisfaction ratio per destination page;
- keep pages with insufficient session data neutral at `0.5` via Laplace smoothing;
- compute the ratio at index/aggregation time (not at suggestion time) since it is a per-page property;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-056 does not:

- rewrite `ContentItem.distilled_text`, `ContentItem.title`, or any embedding;
- change `score_semantic`, `score_keyword`, or the core ranker weighted sum;
- change FR-006 through FR-055 logic;
- replace scroll depth (FR-024) or co-occurrence (FR-025) — they measure different things;
- implement real-time click tracking — it uses batch-aggregated GA4 session data;
- use source-page or link-specific session data in v1 — it aggregates across all arrivals to the destination;
- implement production code in the spec pass.

## Math-Fidelity Note

### Session classification

Let:

- `t_d` = estimated dwell time on the destination page (seconds), computed as the time between the page_view event for the destination and the next page_view event in the same session (or session end)
- `long_threshold` = `long_session_seconds` setting (default 30)
- `short_threshold` = `short_session_seconds` setting (default 10)

**Classification:**

```text
if t_d >= long_threshold:
    click_type = "long"
elif t_d <= short_threshold:
    click_type = "short"
else:
    click_type = "medium" (ignored in the ratio)
```

Medium clicks (between 10 and 30 seconds) are excluded from the ratio to avoid noise from ambiguous sessions.

### Signal definition

Let:

- `L` = count of long-click sessions for this destination page
- `S` = count of short-click sessions for this destination page
- `alpha` = `laplace_alpha` setting (default 5) — Laplace smoothing pseudocount

**Laplace-smoothed satisfaction ratio:**

```text
satisfaction_ratio = (L + alpha) / (L + S + 2 * alpha)
```

This maps:

- no data (`L=0, S=0`) -> `ratio = alpha / (2 * alpha) = 0.5` (neutral prior)
- all long clicks (`L=100, S=0`) -> `ratio = 105 / 110 = 0.955` (very satisfied)
- all short clicks (`L=0, S=100`) -> `ratio = 5 / 110 = 0.045` (very unsatisfied)
- equal mix (`L=50, S=50`) -> `ratio = 55 / 110 = 0.50` (mixed)

**Bounded score:**

```text
score_long_click_ratio = satisfaction_ratio
```

The Laplace-smoothed ratio is already naturally bounded in `(0, 1)` and centered at 0.5 with no data, so no additional mapping is needed.

**Neutral fallback:**

```text
score_long_click_ratio = 0.5
```

Used when:

- GA4 session data is not available for this destination;
- feature is disabled.

### Why Laplace smoothing is the right approach

New pages or pages with few visits should not be penalized for lack of data. Laplace smoothing with `alpha=5` acts as a Bayesian prior: it assumes 5 virtual long clicks and 5 virtual short clicks, producing a neutral 0.5 ratio. As real data accumulates, the prior is gradually overwhelmed by actual observations. With `alpha=5`:

- 10 real long clicks and 0 short clicks: `ratio = 15/20 = 0.75` (mildly positive)
- 50 real long clicks and 0 short clicks: `ratio = 55/60 = 0.917` (strongly positive)
- the signal becomes reliable after ~20 total classified sessions

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_long_click_ratio_component =
  max(0.0, min(1.0, 2.0 * (score_long_click_ratio - 0.5)))
```

```text
score_final += long_click_ratio.ranking_weight * score_long_click_ratio_component
```

Default: `ranking_weight = 0.0` — diagnostics run silently with no ranking impact until an operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-056 must stay separate from:

- engagement read-through rate (FR-024)
  - read-through measures scroll depth (how much of the page the user saw);
  - FR-056 measures dwell time (how long the user stayed);
  - a user can scroll to the bottom quickly (high read-through, short dwell) or read the top half slowly (low read-through, long dwell).

- session co-occurrence (FR-025)
  - co-occurrence measures whether two pages appear in the same session;
  - FR-056 measures whether the user was satisfied after arriving at a specific page;
  - different behavioral dimensions: session composition vs page satisfaction.

- `score_semantic`
  - semantic measures topical similarity;
  - FR-056 measures behavioral satisfaction;
  - completely different data sources and axes.

- hot-decay traffic scoring (FR-023)
  - hot-decay measures overall traffic momentum;
  - FR-056 measures per-session satisfaction quality, not volume;
  - a page can be high-traffic but low-satisfaction (many short clicks).

Hard rule: FR-056 must not mutate any token set, embedding, text field, or engagement metric used by any other signal.

## Inputs Required

FR-056 v1 needs:

- GA4 page_view session data — already ingested by the analytics pipeline
- per-session page dwell times — derived from sequential page_view timestamps within sessions
- long-click and short-click counts per destination page — aggregated at index time

Explicitly disallowed FR-056 inputs in v1:

- per-source-page or per-link satisfaction data (v1 aggregates across all arrivals)
- real-time click stream data
- embedding vectors
- any data not already available in the GA4 analytics pipeline

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `long_click_ratio.enabled`
- `long_click_ratio.ranking_weight`
- `long_click_ratio.long_session_seconds`
- `long_click_ratio.short_session_seconds`
- `long_click_ratio.laplace_alpha`

Defaults:

- `enabled = true`
- `ranking_weight = 0.04`
- `long_session_seconds = 30`
- `short_session_seconds = 10`
- `laplace_alpha = 5`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `15 <= long_session_seconds <= 120`
- `3 <= short_session_seconds <= 30`
- `1 <= laplace_alpha <= 20`
- `short_session_seconds < long_session_seconds` (enforced)

### Feature-flag behavior

- `enabled = false`
  - skip satisfaction computation entirely
  - store `score_long_click_ratio = 0.5`
  - store `long_click_ratio_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute satisfaction ratios and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.long_click_ratio_diagnostics`

Required fields:

- `score_long_click_ratio`
- `long_click_ratio_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_no_session_data`
  - `neutral_processing_error`
- `long_click_count` — number of sessions classified as long clicks
- `short_click_count` — number of sessions classified as short clicks
- `medium_click_count` — number of sessions classified as medium (excluded from ratio)
- `total_sessions` — total session count for this destination
- `satisfaction_ratio` — Laplace-smoothed ratio
- `laplace_alpha_setting` — alpha value used for this computation
- `long_session_seconds_setting` — threshold used
- `short_session_seconds_setting` — threshold used

Plain-English review helper text should say:

- `Long-click ratio means visitors to this destination page tend to stay and read rather than bounce back immediately.`
- `A high score means the page satisfies readers. A low score means readers often leave quickly.`
- `Neutral means there is not enough session data to judge, or the feature is disabled.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_long_click_ratio: FloatField(default=0.5)`
- `long_click_ratio_diagnostics: JSONField(default=dict, blank=True)`

### Content model

Add:

- `ContentItem.long_click_count: IntegerField(default=0)`
- `ContentItem.short_click_count: IntegerField(default=0)`

Reason:

- long/short click counts are per-destination-page aggregates, not pair-specific;
- caching them avoids reprocessing GA4 session data at suggestion time;
- counts are refreshed when GA4 data is re-imported.

### PipelineRun snapshot

Add FR-056 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/long-click-ratio/`
- `PUT /api/settings/long-click-ratio/`

No recalculation endpoint in v1. Counts are refreshed during the GA4 data import cycle.

### Review / admin / frontend

Add one new review row:

- `Long-Click Satisfaction`

Add one small diagnostics block:

- long click count and short click count
- satisfaction ratio
- total sessions
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- long session threshold (seconds)
- short session threshold (seconds)
- Laplace alpha input

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/long_click_ratio.py` — new service file
- `backend/apps/pipeline/services/ranker.py` — add FR-056 additive hook
- `backend/apps/pipeline/services/pipeline.py` — read cached satisfaction data at suggestion time
- `backend/apps/analytics/services.py` (or equivalent) — aggregate long/short click counts from GA4 sessions
- `backend/apps/content/models.py` — add long_click_count and short_click_count fields
- `backend/apps/suggestions/models.py` — add two new fields on Suggestion
- `backend/apps/suggestions/serializers.py` — expose new fields
- `backend/apps/suggestions/views.py` — snapshot FR-056 settings
- `backend/apps/suggestions/admin.py` — expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/content/migrations/<new migration>`
- `backend/apps/core/views.py` — add settings endpoint
- `backend/apps/api/urls.py` — wire new settings endpoint
- `backend/apps/pipeline/tests.py` — FR-056 unit tests
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-056 implementation pass:

- `backend/apps/graph/models.py` — no new graph edges
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`
- `backend/apps/pipeline/services/information_gain.py`
- FR-024 engagement read-through logic — must remain independent

## Test Plan

### 1. Session classification

- 45-second session -> classified as long click
- 5-second session -> classified as short click
- 20-second session -> classified as medium (excluded)

### 2. Satisfaction ratio computation

- L=100, S=0, alpha=5 -> `ratio = 105/110 = 0.955`
- L=0, S=100, alpha=5 -> `ratio = 5/110 = 0.045`
- L=0, S=0, alpha=5 -> `ratio = 5/10 = 0.50` (neutral prior)
- L=50, S=50, alpha=5 -> `ratio = 55/110 = 0.50`

### 3. Neutral fallback cases

- no GA4 session data -> `score = 0.5`, state `neutral_no_session_data`
- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`

### 4. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 5. Bounded score

- score is always in `(0, 1)` — Laplace smoothing ensures it never reaches exactly 0 or 1

### 6. Isolation from other signals

- changing FR-024 engagement settings does not affect `score_long_click_ratio`
- changing FR-025 co-occurrence data does not affect `score_long_click_ratio`

### 7. Serializer and frontend contract

- `score_long_click_ratio` and `long_click_ratio_diagnostics` appear in suggestion detail API response
- review dialog renders the `Long-Click Satisfaction` row
- settings page loads and saves FR-056 settings

### 8. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-056 settings and algorithm version

## Rollout Plan

### Step 1 — session aggregation

- implement GA4 session dwell-time extraction
- aggregate long/short click counts per destination page
- verify counts look reasonable

### Step 2 — diagnostics only

- implement FR-056 scoring with `ranking_weight = 0.0`
- verify that high-satisfaction pages are genuinely engaging content
- verify that low-satisfaction pages are genuinely thin or mismatched

### Step 3 — operator review

- inspect pages with extreme ratios to confirm the signal is meaningful
- check for confounding factors (e.g., exit pages naturally have short dwells)

### Step 4 — optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.03` to `0.05`

## Risk List

- GA4 dwell time is estimated from sequential page_view events and may be inaccurate for the last page in a session (no subsequent event to measure against) — mitigated by excluding sessions with only one page view;
- pages that are natural endpoints (e.g., "thank you" pages, download pages) may have short dwell times even though the user was satisfied — operators should inspect these cases;
- bot traffic can inflate short-click counts — mitigated by GA4's built-in bot filtering and the Laplace smoothing prior;
- the signal requires sufficient GA4 session volume to be reliable (~20+ classified sessions per page) — mitigated by the Laplace prior which keeps low-data pages neutral.

## Recommended Preset Integration

### `recommended_weights.py` entries (already added — forward-declared)

```python
"long_click_ratio.enabled": "true",
"long_click_ratio.ranking_weight": "0.04",
"long_click_ratio.long_session_seconds": "30",
"long_click_ratio.short_session_seconds": "10",
"long_click_ratio.laplace_alpha": "5",
```

**Why these values:**

- `enabled = true` — run diagnostics silently from day one.
- `ranking_weight = 0.04` — strong behavioral signal once sufficient data exists. Higher than structural signals because user satisfaction is a direct quality measure.
- `long_session_seconds = 30` — 30 seconds indicates the user found value and read the content.
- `short_session_seconds = 10` — under 10 seconds strongly suggests the user bounced.
- `laplace_alpha = 5` — moderate prior that requires ~10+ real sessions to move meaningfully from neutral.

### Migration note

A new data migration is needed to upsert these keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.

## Out Of Scope

- per-source-page satisfaction (tracking which links specifically led to satisfaction vs bouncing)
- real-time click-stream processing
- ML-based satisfaction prediction models
- mouse movement or cursor tracking as satisfaction indicators
- any modification to stored text, embeddings, or engagement metrics
