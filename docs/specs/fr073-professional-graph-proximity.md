# FR-073 - Professional Graph Proximity

## Confirmation

- **Backlog confirmed**: `FR-073 - Professional Graph Proximity` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No audience-overlap or co-engagement signal exists in the current ranker. The closest signal is `FR-025` (session co-occurrence), which measures pages visited in the same session. FR-073 measures whether the same users visit both pages across sessions -- a fundamentally different axis.
- **Repo confirmed**: GA4 user-level session data (anonymized `client_id`) is already ingested via the analytics sync pipeline.

## Source Summary

### Patent: US20140244561A1 -- Professional Graph Proximity (LinkedIn)

**Plain-English description of the patent:**

The patent describes measuring content relatedness through the professional network graph -- two pieces of content are related if they are consumed by people in similar professional circles. The co-engagement pattern reveals topical and audience alignment that content-based similarity cannot capture.

**Repo-safe reading:**

The patent uses LinkedIn's professional graph. This repo uses GA4 user-ID sets as a proxy for audience overlap. The reusable core idea is:

- measure audience overlap between source and destination pages;
- pages with high audience overlap are more likely to be relevant to the same readers;
- Jaccard similarity on user-ID sets quantifies this overlap.

**What is adapted for this repo:**

- "professional graph" maps to GA4 `client_id` sets per page;
- "proximity" maps to Jaccard similarity of user sets;
- computed at index time from existing analytics data.

## Plain-English Summary

Simple version first.

If the same people who read page A also read page B, those pages are probably related in a way that matters to readers.

FR-073 measures this audience overlap. If a source page and a destination page share many of the same visitors, the link between them is likely to be valuable -- those readers have already demonstrated interest in both topics.

This is different from topical similarity (which compares text) and from session co-occurrence (which requires same-session visits). FR-073 captures cross-session audience alignment.

## Problem Statement

Today the ranker measures content similarity (text, embeddings) and same-session co-occurrence. It does not measure whether the same audience visits both pages across different sessions.

Two pages might cover different topics in different words but be consumed by the exact same audience -- a valuable linking signal the ranker currently misses.

## Goals

FR-073 should:

- add a separate, explainable, bounded audience proximity signal;
- compute it as Jaccard similarity of GA4 user-ID sets between source and destination;
- reward source-destination pairs with high audience overlap;
- keep pairs with insufficient user data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-073 does not:

- track individual user identities or store PII;
- build a social graph or professional network;
- change any existing co-occurrence logic;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `U_src` = set of GA4 anonymized `client_id`s that visited the source page in the lookback window
- `U_dst` = set of GA4 anonymized `client_id`s that visited the destination page in the lookback window

**Jaccard similarity of user sets:**

```text
J = |U_src intersection U_dst| / |U_src union U_dst|
```

When `|U_src union U_dst| = 0`, `J = 0`.

**Bounded final score:**

```text
score_professional_proximity = 0.5 + 0.5 * J
```

This maps:

- `J = 0.0` (no shared users) -> `score = 0.5` (neutral)
- `J = 1.0` (identical user sets) -> `score = 1.0` (maximum)

**Neutral fallback:**

```text
score_professional_proximity = 0.5
```

Used when:

- either page has fewer than `min_shared_users` (default 5) visitors;
- GA4 user data is unavailable;
- feature is disabled.

### Why Jaccard

Jaccard similarity is the standard set-overlap measure. It is symmetric, bounded in `[0, 1]`, and handles sets of different sizes naturally. A source page with 1000 visitors and a destination with 50 visitors can still have meaningful overlap if many of those 50 are in the 1000.

### Ranking hook

```text
score_proximity_component =
  max(0.0, min(1.0, 2.0 * (score_professional_proximity - 0.5)))
```

```text
score_final += professional_proximity.ranking_weight * score_proximity_component
```

Default: `ranking_weight = 0.0` -- diagnostics only until validated.

## Scope Boundary Versus Existing Signals

FR-073 must stay separate from:

- `FR-025` session co-occurrence
  - co-occurrence requires both pages in the same session;
  - FR-073 counts shared users across all sessions;
  - different temporal scope (single session vs. cross-session).

- `score_semantic`
  - semantic measures text similarity;
  - FR-073 measures audience similarity;
  - orthogonal information sources.

- `FR-070` viral recipient ranking
  - recipient ranking measures visitor quality for a single page;
  - FR-073 measures visitor overlap between two pages;
  - different unit (single page vs. page pair).

Hard rule: FR-073 must not mutate any user data or analytics table used by other signals.

## Inputs Required

- GA4 anonymized `client_id` sets per page -- from existing analytics sync
- Page-level visitor counts -- already computed

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `professional_proximity.enabled`
- `professional_proximity.ranking_weight`
- `professional_proximity.min_shared_users`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `min_shared_users = 5`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `1 <= min_shared_users <= 50`

## Diagnostics And Explainability Plan

Required fields:

- `score_professional_proximity`
- `professional_proximity_state` (`computed`, `neutral_feature_disabled`, `neutral_insufficient_users`, `neutral_processing_error`)
- `source_visitor_count` -- distinct users visiting source page
- `destination_visitor_count` -- distinct users visiting destination page
- `shared_visitor_count` -- users visiting both pages
- `jaccard_similarity` -- raw Jaccard value

Plain-English review helper text should say:

- `Professional graph proximity measures how much the source and destination pages share the same audience.`
- `A high score means many of the same users visit both pages, suggesting strong audience alignment.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_professional_proximity: FloatField(default=0.5)`
- `professional_proximity_diagnostics: JSONField(default=dict, blank=True)`

Note: This is a pair-specific score (source x destination), so it lives on the Suggestion model, not ContentItem.

### PipelineRun snapshot

Add FR-073 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/professional-proximity/`
- `PUT /api/settings/professional-proximity/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"professional_proximity.enabled": "true",
"professional_proximity.ranking_weight": "0.02",
"professional_proximity.min_shared_users": "5",
```

**Why these values:**

- `ranking_weight = 0.02` -- conservative. Audience overlap can be noisy on low-traffic pages.
- `min_shared_users = 5` -- requires at least 5 shared visitors to compute a meaningful Jaccard; below this, random overlap dominates.
