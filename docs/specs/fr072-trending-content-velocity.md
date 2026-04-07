# FR-072 - Trending Content Velocity

## Confirmation

- **Backlog confirmed**: `FR-072 - Trending Content Velocity` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No engagement acceleration or trending signal exists in the current ranker. The closest signal is `score_engagement` (FR-024), which measures cumulative read-through rate. FR-072 measures the rate of change of engagement -- a fundamentally different axis.
- **Repo confirmed**: GA4 engagement data (sessions, events) is already ingested and available at index time via the analytics sync pipeline.

## Source Summary

### Patent: US20150169587A1 -- Trending Content Velocity (Meta/CrowdTangle)

**Plain-English description of the patent:**

The patent describes measuring content popularity not by total engagement but by engagement acceleration -- how quickly engagement is increasing in a recent time window compared to the previous window. Content that is gaining momentum (trending upward) is more timely and relevant than content with flat or declining engagement.

**Repo-safe reading:**

The patent is social-media oriented (measuring Facebook post virality trends). This repo applies the concept to site pages using GA4 engagement data. The reusable core idea is:

- compare engagement in a recent window to a preceding window;
- positive acceleration (current > previous) indicates trending content;
- use sigmoid to bound the velocity score.

**What is adapted for this repo:**

- "engagement" maps to GA4 engaged sessions, pageviews, and events;
- "time window" defaults to 6 hours (configurable);
- computed every 6 hours via Celery beat task, not real-time.

## Plain-English Summary

Simple version first.

Some pages are gaining popularity right now. Some pages had their moment and are fading. Some have steady, unchanging traffic.

FR-072 measures whether a page's engagement is accelerating (trending up), stable, or decelerating (trending down). Pages that are currently trending upward get a boost because they are likely timely and relevant.

Think of it this way: FR-024 asks "does this page get good engagement?" FR-072 asks "is this page getting more engagement now than it was 6 hours ago?"

## Problem Statement

Today the ranker uses cumulative engagement metrics that treat steady pages the same as trending pages. A page that had 1000 sessions over the past month scores the same whether those sessions are spread evenly or concentrated in the last 6 hours.

FR-072 closes this gap by measuring engagement velocity -- the rate of change, not just the level.

## Goals

FR-072 should:

- add a separate, explainable, bounded trending velocity signal;
- compute it from GA4 engagement data over consecutive time windows;
- reward pages with positive engagement acceleration;
- update every `refresh_hours` (default 6 hours) via Celery beat;
- keep missing or insufficient data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-072 does not:

- provide real-time trending detection;
- rewrite any existing engagement signal;
- change any embedding or content field;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `E_current` = total engagement (sessions + events) in the most recent `window_hours` (default 6h)
- `E_previous` = total engagement in the preceding `window_hours` window

**Velocity ratio:**

```text
v = (E_current - E_previous) / max(E_previous, 1)
```

This gives:

- `v > 0` -- engagement is accelerating
- `v = 0` -- engagement is flat
- `v < 0` -- engagement is decelerating

**Bounded score via sigmoid:**

```text
score_trending_velocity = 1 / (1 + exp(-v))
```

This maps:

- `v << 0` (strong deceleration) -> `score ~ 0.0`
- `v = 0` (flat) -> `score = 0.5`
- `v >> 0` (strong acceleration) -> `score ~ 1.0`

**Final score with neutral centering:**

```text
score_final = score_trending_velocity
```

The sigmoid naturally centers at 0.5 for flat engagement, so no additional centering is needed.

**Neutral fallback:**

```text
score_trending_velocity = 0.5
```

Used when:

- fewer than `min_sessions` (default 5) sessions in either window;
- GA4 data is stale or unavailable;
- feature is disabled.

### Why sigmoid

The velocity ratio `v` is unbounded (a page going from 1 session to 100 sessions has `v = 99`). Sigmoid maps any real number to `(0, 1)`, naturally handling extreme values without arbitrary capping.

### Ranking hook

```text
score_velocity_component =
  max(0.0, min(1.0, 2.0 * (score_trending_velocity - 0.5)))
```

```text
score_final += trending_velocity.ranking_weight * score_velocity_component
```

Default: `ranking_weight = 0.0` -- diagnostics only until validated.

## Scope Boundary Versus Existing Signals

FR-072 must stay separate from:

- `score_engagement` (FR-024) -- measures cumulative engagement level, not rate of change.
- `FR-050` seasonality -- measures cyclical demand patterns over weeks/months, not 6-hour acceleration.
- `FR-069` viral depth -- measures sharing chain depth, not engagement velocity.
- `FR-080` freshness decay -- measures long-term decay rate over weeks, not short-term acceleration.

Hard rule: FR-072 must not mutate any engagement metric used by FR-024 or FR-050.

## Inputs Required

- GA4 session and event data -- already ingested via analytics sync
- Time-windowed aggregation (6-hour buckets) -- computed at refresh time

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `trending_velocity.enabled`
- `trending_velocity.ranking_weight`
- `trending_velocity.window_hours`
- `trending_velocity.refresh_hours`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `window_hours = 6`
- `refresh_hours = 6`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `1 <= window_hours <= 48`
- `1 <= refresh_hours <= 24`

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `ContentItem.trending_velocity_diagnostics`

Required fields:

- `score_trending_velocity`
- `trending_velocity_state` (`computed`, `neutral_feature_disabled`, `neutral_insufficient_data`, `neutral_processing_error`)
- `engagement_current_window` -- engagement count in current window
- `engagement_previous_window` -- engagement count in previous window
- `velocity_ratio` -- raw `v` value before sigmoid
- `window_hours` -- window size used
- `last_computed_at` -- timestamp of last computation

Plain-English review helper text should say:

- `Trending velocity measures whether this page's engagement is accelerating or decelerating.`
- `A high score means the page is currently gaining momentum. A low score means it is losing interest.`
- `Neutral means there was not enough recent data to measure a trend.`

## Storage / Model / API Impact

### Content model

Add:

- `score_trending_velocity: FloatField(default=0.5)`
- `trending_velocity_diagnostics: JSONField(default=dict, blank=True)`

### PipelineRun snapshot

Add FR-072 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/trending-velocity/`
- `PUT /api/settings/trending-velocity/`

### Review / admin / frontend

Add one new review row: `Trending Content Velocity`

Add one settings card:

- enabled toggle
- ranking weight slider
- window hours
- refresh hours

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"trending_velocity.enabled": "true",
"trending_velocity.ranking_weight": "0.02",
"trending_velocity.window_hours": "6",
"trending_velocity.refresh_hours": "6",
```

**Why these values:**

- `ranking_weight = 0.02` -- conservative. Trending signals are noisy and should be validated before increasing weight.
- `window_hours = 6` -- 6-hour windows balance responsiveness with stability. Shorter windows are too noisy; longer windows miss short-lived trends.
- `refresh_hours = 6` -- matches the window size so each refresh sees a fresh window.
