# FR-078 - Community Upvote Velocity

## Confirmation

- **Backlog confirmed**: `FR-078 - Community Upvote Velocity` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No first-hour engagement velocity or community response signal exists in the current ranker. The closest signal is `FR-072` (trending content velocity), which measures 6-hour engagement acceleration. FR-078 measures first-hour community response intensity -- a different temporal granularity and different input source.
- **Repo confirmed**: GA4 event data with timestamps is already ingested via the analytics sync pipeline.

## Source Summary

### Patent: US20140244561A1 -- Community Upvote Velocity (Reddit-derived)

**Plain-English description of the patent:**

The patent describes ranking content by the velocity of community endorsement in the first hour after publication. Content that receives rapid positive signals from an active community is likely timely and valuable. The first-hour window captures the initial community response before broader distribution effects take over.

**What is adapted for this repo:**

- "upvotes" maps to GA4 engagement events (shares, comments, likes) in the first hour after publication;
- "velocity" is normalized against the page's historical median first-hour performance;
- the score is capped to prevent viral outliers from dominating.

## Plain-English Summary

Simple version first.

When a page is first published, how quickly does the community respond? If a page gets lots of shares, comments, and engagement in its first hour -- much more than this page typically gets -- it is resonating with the audience.

FR-078 measures this first-hour community response relative to the page's own historical baseline. A page that gets 5x its normal first-hour engagement is trending with the community.

## Problem Statement

Today the ranker measures cumulative engagement and 6-hour trends but not the initial community response velocity. A page that explodes in its first hour but then levels off may be caught by FR-072, but the first-hour signal specifically captures community resonance timing.

## Goals

FR-078 should:

- add a separate, explainable, bounded first-hour velocity signal;
- normalize against the page's historical median to avoid penalizing low-traffic pages;
- cap the score to prevent extreme outliers from dominating;
- keep pages with insufficient data neutral at `0.5`.

## Non-Goals

FR-078 does not:

- provide real-time alerting;
- modify FR-072 trending velocity;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `votes_first_hour` = engagement events in the first hour after publication (or most recent update)
- `median_first_hour` = historical median first-hour engagement for pages on this site
- `velocity_cap` = maximum velocity ratio (default 5.0)

**Velocity ratio:**

```text
v = votes_first_hour / max(median_first_hour, 1)
```

**Capped and normalized score:**

```text
score_upvote_velocity = min(1.0, v / velocity_cap)
```

This maps:

- `v = 0` (no first-hour engagement) -> `score = 0.0`
- `v = velocity_cap` (5x median) -> `score = 1.0`
- `v = 2.5` (2.5x median) -> `score = 0.5`

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_upvote_velocity
```

**Neutral fallback:**

```text
score_upvote_velocity = 0.5
```

Used when:

- page has no publication timestamp;
- fewer than 3 historical comparisons available;
- feature is disabled.

### Ranking hook

```text
score_upvote_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += upvote_velocity.ranking_weight * score_upvote_component
```

## Scope Boundary Versus Existing Signals

FR-078 must stay separate from:

- `FR-072` trending velocity -- measures 6-hour windows, not first-hour specifically.
- `FR-024` engagement -- measures cumulative read-through, not publication-time response.
- `FR-023` Reddit hot/Wilson -- measures external Reddit engagement, not site-internal community response.

## Inputs Required

- GA4 event data with timestamps -- from existing analytics sync
- Page publication timestamps -- from `ContentItem.published_at`

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `upvote_velocity.enabled`
- `upvote_velocity.ranking_weight`
- `upvote_velocity.first_hour_window`
- `upvote_velocity.velocity_cap`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `first_hour_window = 1`
- `velocity_cap = 5.0`

## Diagnostics And Explainability Plan

Required fields:

- `score_upvote_velocity`
- `upvote_velocity_state` (`computed`, `neutral_feature_disabled`, `neutral_insufficient_data`, `neutral_processing_error`)
- `first_hour_events` -- raw event count in first hour
- `median_first_hour_events` -- historical median
- `velocity_ratio` -- raw ratio before capping

Plain-English review helper text should say:

- `Community upvote velocity measures how strongly the audience responded to this page in its first hour.`
- `A high score means the page received engagement well above its historical baseline.`

## Storage / Model / API Impact

### Content model

Add:

- `score_upvote_velocity: FloatField(default=0.5)`
- `upvote_velocity_diagnostics: JSONField(default=dict, blank=True)`

### Backend API

Add:

- `GET /api/settings/upvote-velocity/`
- `PUT /api/settings/upvote-velocity/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"upvote_velocity.enabled": "true",
"upvote_velocity.ranking_weight": "0.02",
"upvote_velocity.first_hour_window": "1",
"upvote_velocity.velocity_cap": "5.0",
```
