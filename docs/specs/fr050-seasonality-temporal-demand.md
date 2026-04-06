# FR-050 — Seasonality & Temporal Demand Matching

**Status:** Pending
**Requested:** 2026-04-06
**Target phase:** TBD
**Priority:** Medium
**Depends on:** FR-016 (GA4 integration for historical traffic), FR-017 (GSC integration for query impressions)

---

## Confirmation

- `FR-050` is a new backlog item being added to `FEATURE-REQUESTS.md` in this session.
- Repo confirmed:
  - no ranking signal currently models seasonal or cyclical demand patterns;
  - `FR-023` (hot decay) measures recent traffic trending but cannot distinguish seasonal peaks from permanent growth;
  - `FR-016` / `FR-017` aggregate historical GA4/GSC metrics but do not decompose them into seasonal components;
  - `FR-044` (internal search intensity) detects short-term search demand bursts but not predictable annual cycles;
  - GA4 daily pageview data and GSC weekly impression data already flow into the system, providing at least 12 months of historical signal for seasonal curve fitting.

## Current Repo Map

### Existing nearby signals

- `FR-023` hot decay
  - measures whether traffic is trending up or down recently;
  - it cannot tell whether a traffic drop is seasonal (expected, will return) or permanent (declining content).

- `FR-016` / `FR-017` GA4/GSC content value
  - aggregates pageviews and impressions over a lookback window;
  - it does not decompose traffic into trend + seasonal + residual components.

- `FR-044` internal search intensity
  - detects short-term burst demand for specific queries;
  - it does not model predictable annual cycles.

- `FR-007` link freshness
  - measures when links were added or removed;
  - it has no relationship to seasonal content demand.

### Gap this FR closes

The repo cannot currently distinguish between a destination page that is universally relevant year-round and one that is seasonally relevant right now. A "best winter coats" page and a "best summer dresses" page might have identical trailing-90-day traffic, but in October the winter coats page is about to spike while the summer dresses page is about to drop. Without seasonal awareness, the ranker treats them equally.

## Source Summary

### Patent: US9081857B1 — Freshness and Seasonality-Based Content Determinations

Plain-English read:

- the patent describes methods for determining whether a document's relevance is seasonal or perennial;
- seasonal documents have demand that peaks and troughs on a predictable annual cycle;
- the system uses historical query volume patterns to detect seasonality and adjusts ranking accordingly;
- documents matching a seasonal peak receive a temporary boost; documents in a seasonal trough receive a temporary reduction.

Repo-safe takeaway:

- seasonality can be detected from historical traffic patterns already in the system;
- the useful decomposition is "is this page seasonal, and if so, are we near a peak or trough right now?";
- a simple sinusoidal fit is sufficient for v1 — no complex time-series library required.

### Academic basis: Classical time-series seasonal decomposition

Plain-English read:

- classical decomposition splits a time series into three components: trend, seasonal, and residual;
- the seasonal component captures predictable repeating patterns (annual cycles, weekly cycles);
- seasonal strength measures how much of the variance is explained by the seasonal component versus the residual.

Repo-safe takeaway:

- the math for extracting seasonal patterns from monthly traffic data is well-established;
- the key output is a seasonal index for each month (or week) of the year;
- pages with strong seasonal patterns should be scored by where the current date falls on their seasonal curve.

### Concept: Google's Query Deserves Freshness (QDF)

Plain-English read:

- QDF temporarily boosts results for queries experiencing a sudden spike in search volume;
- QDF is a reactive signal — it responds to current demand surges.

Repo-safe takeaway:

- FR-050 is the *predictive* complement to QDF-style reactive signals;
- instead of waiting for a spike to happen, seasonal scoring anticipates it;
- this pairs well with FR-023 (hot decay, reactive) and FR-044 (search intensity, reactive).

## Plain-English Summary

Simple version first.

Some pages are popular in winter but not summer.
Some pages are popular around holidays but not the rest of the year.

FR-050 learns each page's seasonal pattern from last year's traffic.
Then it checks where we are in the calendar right now.
If a page's busy season is coming up, it gets a boost as a link target.
If its busy season just ended, it stays neutral.

Example:

- "Best Winter Coats 2026" had a traffic spike in November-January last year.
- Today is October. FR-050 detects that this page's seasonal peak is 1 month away.
- The page gets a boost as a link destination because it is about to become very relevant.
- In May, the same page gets no boost because its peak is 6 months away.

## Problem Statement

Today the ranker evaluates destinations based on their current or recent metrics — recent traffic, recent engagement, recent link changes. None of these signals can predict that a page is *about to become* highly relevant because its annual demand cycle is approaching a peak.

This means the linker misses opportunities to pre-position internal links toward seasonally relevant content before the traffic arrives, and it over-links to seasonally declining content after its peak has passed.

FR-050 adds a forward-looking seasonal signal so the ranker can anticipate cyclical demand.

## Goals

FR-050 should:

- detect whether each page has a significant seasonal traffic pattern using 12+ months of GA4 or GSC historical data;
- compute a seasonal index for each month (or week) of the year per page;
- produce a bounded suggestion-level score that boosts destinations whose seasonal peak is approaching;
- stay neutral for pages with no seasonal pattern, insufficient history, or flat year-round demand;
- update seasonal models periodically (monthly), not on every pipeline run;
- use simple decomposition math in v1 — no external time-series libraries required.

## Non-Goals

FR-050 does not:

- replace or modify FR-023 (hot decay remains a separate reactive signal);
- predict absolute traffic volumes — only relative seasonal patterns;
- model weekly or daily micro-cycles (e.g., "traffic spikes on Mondays") — annual cycles only in v1;
- require real-time data — monthly recomputation is sufficient;
- modify GA4/GSC data ingestion — it consumes existing imported data.

## Math-Fidelity Note

### Input data

Use monthly aggregated traffic for each page over the most recent `history_months` (minimum 12, recommended 24).

Let:

- `y_m` = total pageviews (or impressions) for page `p` in month `m`
- `M` = number of months of available data
- `months_of_year` = month index 1-12

### Step 1 — compute monthly seasonal index

Average the traffic for each calendar month across all available years:

```text
avg_month(k) = mean(y_m)  for all m where month_of_year(m) == k
               m
```

Compute the grand mean:

```text
grand_mean = mean(y_m)  for all m
             m
```

Seasonal index for month `k`:

```text
seasonal_index(k) = avg_month(k) / max(grand_mean, ε)
```

Where `ε = 1.0` (minimum 1 pageview to prevent division by zero).

A seasonal index of 1.0 means average demand. Above 1.0 means above-average (approaching peak). Below 1.0 means below-average (off-season).

### Step 2 — measure seasonal strength

Not all pages are seasonal. Measure how much of the variance is explained by the seasonal pattern:

```text
SS_seasonal = Σ  count_years(k) * (avg_month(k) - grand_mean)^2
              k=1..12
```

```text
SS_total = Σ (y_m - grand_mean)^2
           m
```

```text
seasonal_strength = SS_seasonal / max(SS_total, ε)
```

Where `ε = 1e-9`.

`seasonal_strength` ranges from 0.0 (no seasonal pattern — flat demand) to 1.0 (all variance explained by seasonal cycle).

Pages with `seasonal_strength < min_seasonal_strength` are classified as perennial and receive the neutral fallback.

Recommended default:

- `min_seasonal_strength = 0.3`

### Step 3 — compute current seasonal position score

Look up the seasonal index for the current month and the upcoming month:

```text
current_month = month_of_year(today)
next_month = (current_month % 12) + 1
```

Blend current and upcoming month for smooth transitions:

```text
day_fraction = day_of_month(today) / days_in_month(current_month)

blended_index = (1 - day_fraction) * seasonal_index(current_month)
              + day_fraction * seasonal_index(next_month)
```

### Step 4 — anticipation bonus

Boost pages whose peak is approaching (within `anticipation_window_months`). Detect the peak month:

```text
peak_month = argmax  seasonal_index(k)
             k=1..12
```

Compute months until peak (wrapping around December → January):

```text
months_to_peak = (peak_month - current_month) mod 12
```

Anticipation bonus when peak is approaching:

```text
if months_to_peak <= anticipation_window_months and months_to_peak > 0:
    anticipation = 1.0 - (months_to_peak / anticipation_window_months)
else:
    anticipation = 0.0
```

Recommended default:

- `anticipation_window_months = 3`

### Step 5 — combined seasonal score

Combine the current seasonal index with the anticipation bonus:

```text
seasonal_raw = w_current * min(blended_index, index_cap)
             + w_anticipation * anticipation
```

Where:

- `w_current = 0.7` — current seasonal relevance is the primary signal
- `w_anticipation = 0.3` — upcoming peak is a secondary boost
- `index_cap = 3.0` — cap extreme seasonal spikes to prevent domination

Normalize:

```text
seasonal_norm = min(1.0, seasonal_raw / index_cap)
```

### Step 6 — bounded score with seasonal strength gating

```text
score_seasonality = 0.5 + 0.5 * seasonal_strength * seasonal_norm
```

The `seasonal_strength` multiplier ensures that pages with weak seasonal patterns stay close to neutral even during their "peak" month.

Score range:

- `0.5` = perennial page (no seasonal pattern) or off-season
- `1.0` = strongly seasonal page at peak with high anticipation

Neutral fallback:

```text
score_seasonality = 0.5
```

Used when:

- feature disabled;
- page has fewer than `min_history_months` of traffic data;
- `seasonal_strength < min_seasonal_strength`;
- no GA4/GSC data available for the page.

### Ranking hook

```text
score_seasonality_component =
  max(0.0, min(1.0, 2.0 * (score_seasonality - 0.5)))
```

```text
score_final += seasonality.ranking_weight * score_seasonality_component
```

Default:

- `ranking_weight = 0.0`

## Scope Boundary Versus Existing Signals

FR-050 must stay separate from:

- `FR-023` hot decay
  - FR-023 is reactive — it measures recent traffic momentum;
  - FR-050 is predictive — it forecasts seasonal demand from historical annual patterns.

- `FR-016` / `FR-017` GA4/GSC content value
  - FR-016/017 aggregate raw traffic metrics;
  - FR-050 decomposes traffic into seasonal patterns and scores by calendar position.

- `FR-044` internal search intensity
  - FR-044 detects short-term burst demand for queries;
  - FR-050 detects predictable annual cycles, not sudden bursts.

- `FR-007` link freshness
  - FR-007 measures when links were added or removed;
  - FR-050 has no relationship to link timing.

Hard rule:

- FR-050 must not mutate GA4/GSC import data, traffic records, or other feature caches.

## Inputs Required

FR-050 v1 can use:

- GA4 daily pageview aggregates per URL (already imported by FR-016), grouped into monthly buckets
- GSC weekly impression aggregates per URL (already imported by FR-017), grouped into monthly buckets
- `ContentItem.url` for mapping traffic data to content items
- Current date for calendar position

Explicitly disallowed in v1:

- external seasonal forecasting APIs;
- sub-monthly cycle detection (weekly patterns);
- real-time traffic streaming;
- complex time-series libraries (Prophet, ARIMA) — simple seasonal decomposition only.

## Data Model Plan

Add to `ContentItem`:

- `seasonal_index_data` — JSON field storing the 12-month seasonal index array
- `seasonal_strength` — float measuring how seasonal the page is
- `seasonal_peak_month` — integer (1-12) of the peak demand month
- `seasonal_model_computed_at` — datetime of last model recomputation

Add to `Suggestion`:

- `score_seasonality`
- `seasonality_diagnostics`

## Settings And Feature-Flag Plan

Recommended keys:

- `seasonality.enabled`
- `seasonality.ranking_weight`
- `seasonality.min_history_months`
- `seasonality.min_seasonal_strength`
- `seasonality.anticipation_window_months`
- `seasonality.w_current`
- `seasonality.w_anticipation`
- `seasonality.index_cap`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `min_history_months = 12`
- `min_seasonal_strength = 0.3`
- `anticipation_window_months = 3`
- `w_current = 0.7`
- `w_anticipation = 0.3`
- `index_cap = 3.0`

## Diagnostics And Explainability Plan

Diagnostics should include:

- `seasonal_index` (12-element array)
- `seasonal_strength`
- `peak_month` and `peak_month_label` (e.g., "November")
- `current_month` and `blended_index`
- `months_to_peak`
- `anticipation`
- `seasonal_raw`
- `history_months_available`
- `classification` ("seasonal", "perennial", or "insufficient_data")
- `fallback_state`

Plain-English helper text:

- "Seasonality scoring boosts destinations whose annual traffic peak is approaching, so internal links point to content that is about to become highly relevant."

## Native Performance Plan

This is a later ranking-affecting FR, so it must plan a native fast path.

### C++ default path

Add a native batch scorer that reads cached seasonal index arrays and computes calendar-position-based scores across all suggestions.

Suggested file:

- `backend/extensions/seasonality.cpp`

### Python fallback

Add:

- `backend/apps/pipeline/services/seasonality.py`

The Python and C++ paths must produce the same bounded scores for the same seasonal index data and current date.

### Visibility requirement

Expose:

- native enabled / fallback enabled;
- why fallback is active;
- whether native batch scoring is materially faster;
- when seasonal models were last recomputed and how many pages are classified as seasonal.

## Backend Touch Points

- `backend/apps/content/models.py`
- `backend/apps/suggestions/models.py`
- `backend/apps/core/views.py`
- `backend/apps/pipeline/services/seasonality.py`
- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/tasks.py`
- `backend/extensions/seasonality.cpp`

## Verification Plan

Later implementation must verify at least:

1. strongly seasonal pages near their peak month score higher than the same pages 6 months away from peak;
2. perennial pages (low seasonal_strength) receive the neutral 0.5 fallback regardless of month;
3. pages with fewer than `min_history_months` of data receive neutral fallback;
4. anticipation bonus correctly boosts pages whose peak is 1-3 months away;
5. `ranking_weight = 0.0` leaves ranking unchanged;
6. seasonal_strength gating prevents weakly-seasonal pages from receiving large boosts;
7. C++ and Python paths produce identical scores;
8. diagnostics explain the seasonal classification, peak month, and current position for each page.
