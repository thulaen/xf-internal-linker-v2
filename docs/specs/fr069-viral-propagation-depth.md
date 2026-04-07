# FR-069 - Viral Propagation Depth

## Confirmation

- **Backlog confirmed**: `FR-069 - Viral Propagation Depth` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No sharing-hop or viral-depth signal exists in the current ranker. The closest existing signal is `score_engagement` (FR-024), which measures read-through rate. FR-069 measures how many sharing hops content travels before engagement decays -- a fundamentally different axis.
- **Repo confirmed**: GA4 referral chain data is already ingested via the analytics sync pipeline and is available at index time.

## Source Summary

### Patent: US10152544B1 -- Viral Content Propagation Depth (Meta)

**Plain-English description of the patent:**

The patent describes measuring how far a piece of content spreads through a social sharing graph before engagement drops below a meaningful threshold. Content that gets shared and reshared many times (high hop depth) has demonstrated genuine viral appeal. Content that only gets one level of sharing has limited propagation power.

**Repo-safe reading:**

The patent is social-network oriented (measuring reshare chains on Facebook). This repo is site-local and suggestion-time. The reusable core idea is:

- measure the maximum depth of sharing chains before engagement falls below a percentage of peak;
- treat deeper propagation as a positive quality signal for the destination page;
- keep it additive and bounded on top of existing relevance scores.

**What is directly supported by the patent:**

- scoring content by how many hops it travels through a sharing network;
- using an engagement floor (percentage of peak) to define the cutoff depth;
- treating deeper propagation as a quality indicator.

**What is adapted for this repo:**

- "sharing graph" maps to GA4 referral chains (page A refers traffic to page B, B refers to C, etc.);
- "engagement" maps to GA4 session metrics (pageviews, engaged sessions);
- the patent uses Facebook's internal sharing graph; this repo uses referral path data from GA4 -- simpler, deterministic, and reproducible without a live social graph.

## Plain-English Summary

Simple version first.

When a page gets shared and reshared many times -- person A shares to B, B shares to C, C shares to D -- that chain of sharing is called propagation depth.

Pages that get reshared through many hops have demonstrated genuine viral appeal. People did not just click once -- they valued the content enough to pass it along, and the next person valued it enough to pass it along again.

FR-069 rewards destination pages that have demonstrated this kind of multi-hop sharing behaviour. A page that only gets direct traffic scores lower than a page that gets shared three or four hops deep.

Think of it this way: `score_semantic` asks "is the destination on the right topic?" FR-069 asks "has this content proven it spreads organically?"

## Problem Statement

Today the ranker rewards topical similarity, anchor quality, and engagement metrics like read-through rate. It does not measure whether a destination page has demonstrated viral spreading behaviour.

This means two equally relevant pages are scored identically even when one has been organically reshared through multiple hops and the other has only received direct traffic. The page with multi-hop sharing has demonstrated genuine audience value, but the ranker cannot tell the difference.

FR-069 closes this gap with a bounded, explainable, per-page viral propagation depth signal.

## Goals

FR-069 should:

- add a separate, explainable, bounded viral depth signal;
- compute it from GA4 referral chain data at index time;
- reward destination pages whose content has demonstrated multi-hop sharing;
- keep missing or insufficient referral data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-069 does not:

- rewrite `ContentItem.distilled_text`, `ContentItem.title`, or any embedding;
- change `score_semantic`, `score_keyword`, or the core ranker weighted sum;
- change FR-006 through FR-068 logic;
- replace the relevance requirement -- a high depth score does not override a low semantic score;
- build a real-time social graph tracker;
- introduce a broad new analytics subsystem;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `depth` = maximum sharing-hop count for the destination page before engagement falls below `engagement_floor` (default 10%) of peak engagement
- `max_depth` = corpus-wide maximum observed depth across all pages (typically 5-10 for most sites)

**Raw score (logarithmic scaling):**

```text
score_viral_depth = log(depth + 1) / log(max_depth + 1)
```

This maps:

- `depth = 0` (no sharing hops, direct traffic only) -> `score = 0.0`
- `depth = max_depth` (deepest observed sharing chain) -> `score = 1.0`
- Intermediate depths are log-scaled, giving diminishing returns for each additional hop.

**Bounded final score:**

```text
score_final = 0.5 + 0.5 * score_viral_depth
```

This maps:

- `depth = 0` -> `score = 0.5` (neutral)
- `depth = max_depth` -> `score = 1.0` (maximum)
- Typical values sit in `[0.55, 0.85]` for real content.

**Neutral fallback:**

```text
score_viral_depth = 0.5
```

Used when:

- GA4 referral data is missing or below `min_sessions` threshold;
- page has no referral chain data;
- feature is disabled.

### Why logarithmic scaling

Sharing depth follows a power-law distribution. Most pages have depth 0-1, a few reach depth 3-5, and very rarely depth exceeds 7. Raw linear depth would compress most pages into a narrow band. Logarithmic scaling spreads the useful range:

```text
log(1+1)/log(8+1) = 0.315     (depth 1)
log(2+1)/log(8+1) = 0.500     (depth 2)
log(4+1)/log(8+1) = 0.732     (depth 4)
log(8+1)/log(8+1) = 1.000     (depth 8)
```

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_viral_depth_component =
  max(0.0, min(1.0, 2.0 * (score_viral_depth - 0.5)))
```

```text
score_final += viral_depth.ranking_weight * score_viral_depth_component
```

Default: `ranking_weight = 0.0` -- diagnostics run silently with no ranking impact until an operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-069 must stay separate from:

- `score_engagement` (FR-024)
  - engagement measures individual user read-through behaviour on a single page;
  - FR-069 measures multi-hop sharing chain depth across users;
  - different unit of analysis (single session vs. chain of referrals).

- `FR-074` influence score
  - influence measures the authority of content authors/sharers in a social graph;
  - FR-069 measures how deep sharing chains go regardless of who shares;
  - different axis (who shares vs. how far it spreads).

- `FR-072` trending content velocity
  - velocity measures engagement acceleration in a recent time window;
  - FR-069 measures cumulative sharing depth over the lookback period;
  - different temporal scope (recent burst vs. historical propagation).

Hard rule: FR-069 must not mutate any token set, embedding, or text field used by any other signal.

## Inputs Required

FR-069 v1 can use only data already available in the pipeline:

- GA4 referral path data -- from `AnalyticsSync` rows already ingested
- GA4 session engagement metrics -- from existing analytics tables
- page-level session counts -- already computed per `ContentItem`

Explicitly disallowed FR-069 inputs in v1:

- embedding vectors
- anchor text data
- reviewer feedback
- any data not already loaded by the analytics sync pipeline

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys (from `recommended_weights.py`):

- `viral_depth.enabled`
- `viral_depth.ranking_weight`
- `viral_depth.engagement_floor`
- `viral_depth.lookback_days`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `engagement_floor = 0.10`
- `lookback_days = 90`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `0.01 <= engagement_floor <= 0.50`
- `7 <= lookback_days <= 365`

### Feature-flag behaviour

- `enabled = false`
  - skip depth computation entirely
  - store `score_viral_depth = 0.5`
  - store `viral_depth_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute depth and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `ContentItem.viral_depth_diagnostics`

Required fields:

- `score_viral_depth`
- `viral_depth_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_no_referral_data`
  - `neutral_insufficient_sessions`
  - `neutral_processing_error`
- `max_hop_depth` -- deepest sharing chain observed for this page
- `engagement_at_max_depth` -- engagement level at the deepest hop
- `corpus_max_depth` -- corpus-wide max depth used for normalization
- `referral_chain_count` -- number of distinct referral chains analysed
- `lookback_days` -- setting value used for this run

Plain-English review helper text should say:

- `Viral depth measures how many sharing hops this page's content travels before interest drops off.`
- `A high score means the content has been reshared through multiple levels of audience, indicating genuine viral appeal.`
- `Neutral means there was not enough referral data to compute depth, or the feature is disabled.`

## Storage / Model / API Impact

### Content model

Add:

- `score_viral_depth: FloatField(default=0.5)`
- `viral_depth_diagnostics: JSONField(default=dict, blank=True)`

### Suggestion model

No new `Suggestion` field needed.

Reason:

- viral depth is a per-page property computed at index time, not a per-suggestion pair-specific score.

### PipelineRun snapshot

Add FR-069 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/viral-depth/`
- `PUT /api/settings/viral-depth/`

### Review / admin / frontend

Add one new review row:

- `Viral Propagation Depth`

Add one small diagnostics block:

- max hop depth
- engagement at max depth
- corpus max depth
- referral chain count
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- engagement floor threshold
- lookback days slider

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"viral_depth.enabled": "true",
"viral_depth.ranking_weight": "0.02",
"viral_depth.engagement_floor": "0.10",
"viral_depth.lookback_days": "90",
```

**Why these values:**

- `enabled = true` -- run diagnostics silently from day one so an operator can inspect depth distributions before enabling ranking impact.
- `ranking_weight = 0.02` -- conservative starting point for an unvalidated social signal. Acts as a light tie-breaker.
- `engagement_floor = 0.10` -- 10% of peak engagement is a reasonable cutoff for "engagement has decayed". Below this, further hops are noise.
- `lookback_days = 90` -- three months of referral data gives a stable depth estimate without being overwhelmed by stale historical patterns.
