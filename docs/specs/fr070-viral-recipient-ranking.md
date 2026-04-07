# FR-070 - Viral Content Recipient Ranking

## Confirmation

- **Backlog confirmed**: `FR-070 - Viral Content Recipient Ranking` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No recipient authority or share-quality signal exists in the current ranker. The closest signal is FR-069 (viral propagation depth), which measures how far content spreads. FR-070 measures who it spreads to -- a fundamentally different axis.
- **Repo confirmed**: GA4 referral and user-level session data is already ingested via the analytics sync pipeline.

## Source Summary

### Patent: US9323850B1 -- Viral Content Recipient Ranking (Google/YouTube)

**Plain-English description of the patent:**

The patent describes scoring content not just by how widely it is shared, but by the authority of the people it is shared with. Content shared with influential recipients (people who themselves have large audiences or high engagement) is more valuable than content shared with inactive accounts or bots.

**Repo-safe reading:**

The patent is YouTube-oriented (measuring video sharing to influential viewers). This repo is site-local and suggestion-time. The reusable core idea is:

- score destinations by the cumulative authority of users who engage with them;
- authority is derived from the user's own engagement footprint (session count, pages viewed, return frequency);
- treat high-authority recipient engagement as a quality signal.

**What is directly supported by the patent:**

- scoring content by recipient influence rather than raw share count;
- computing recipient authority from engagement data;
- using the signal as an additive quality layer.

**What is adapted for this repo:**

- "recipients" maps to GA4 user IDs (client_id) that visit the destination page;
- "authority" maps to the user's overall site engagement (total sessions, pages per session, return frequency);
- the patent uses YouTube sharing; this repo uses GA4 user-level engagement data.

## Plain-English Summary

Simple version first.

Not all page visits are equal. A page visited by highly engaged, returning users is more valuable than a page visited only by one-time bouncers.

FR-070 scores destination pages by the authority of the users who engage with them. If a page attracts users who are frequent visitors, read many pages per session, and return often -- that page is probably high quality. If a page only attracts drive-by visitors who never come back -- it is probably less valuable.

Think of it this way: FR-069 asks "how far does this content spread?" FR-070 asks "does this content attract quality audiences?"

## Problem Statement

Today the ranker measures engagement volume (how many sessions, how much read-through) but not engagement quality. A page with 1000 visits from bouncing users scores the same as a page with 1000 visits from deeply engaged returning users.

FR-070 closes this gap by scoring pages based on the authority of their visitors.

## Goals

FR-070 should:

- add a separate, explainable, bounded recipient authority signal;
- compute it from GA4 user-level engagement data at index time;
- reward destination pages whose visitors are high-authority (frequent, engaged, returning);
- keep missing or insufficient user data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-070 does not:

- rewrite `ContentItem.distilled_text`, `ContentItem.title`, or any embedding;
- change FR-006 through FR-069 logic;
- track individual user identities or store PII;
- build a real-time user authority graph;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `R` = set of GA4 user IDs (anonymized `client_id`) who visited the destination page in the lookback window
- `authority(u)` = engagement-based authority score for user `u`, computed as a weighted combination of their site-wide behaviour

**User authority score:**

```text
authority(u) = 0.4 * min(1, sessions(u) / 20)
             + 0.3 * min(1, pages_per_session(u) / 10)
             + 0.3 * min(1, return_visits(u) / 5)
```

Each component is capped at 1.0 so authority is bounded in `[0, 1]`.

**Page recipient authority:**

```text
mean_authority = (1 / |R|) * sum(authority(u) for u in R)
```

**Bounded final score:**

```text
score_viral_recipient = 0.5 + 0.5 * mean_authority
```

This maps:

- `mean_authority = 0.0` (all visitors are low-engagement one-timers) -> `score = 0.5` (neutral)
- `mean_authority = 1.0` (all visitors are highly engaged returners) -> `score = 1.0` (maximum)

**Neutral fallback:**

```text
score_viral_recipient = 0.5
```

Used when:

- fewer than `min_visitors` (default 10) distinct users visited the page in the lookback window;
- GA4 user-level data is unavailable;
- feature is disabled.

### Ranking hook

```text
score_viral_recipient_component =
  max(0.0, min(1.0, 2.0 * (score_viral_recipient - 0.5)))
```

```text
score_final += viral_recipient.ranking_weight * score_viral_recipient_component
```

Default: `ranking_weight = 0.0` -- diagnostics only until validated.

## Scope Boundary Versus Existing Signals

FR-070 must stay separate from:

- `score_engagement` (FR-024)
  - engagement measures individual read-through rate on a page;
  - FR-070 measures the quality of the page's visitor base;
  - different unit (page behaviour vs. visitor profile).

- `FR-069` viral propagation depth
  - depth measures how far content spreads through sharing chains;
  - FR-070 measures who the content reaches;
  - orthogonal axes (spread distance vs. audience quality).

- `FR-074` influence score
  - influence measures author/sharer authority in a social reshare graph;
  - FR-070 measures visitor authority based on engagement data;
  - different input data (reshare graph vs. GA4 sessions).

Hard rule: FR-070 must not mutate any token set, embedding, or text field used by any other signal.

## Inputs Required

FR-070 v1 can use only data already available in the pipeline:

- GA4 user-level session data (anonymized `client_id`, session count, pages per session)
- GA4 page-level visit data (which users visited which pages)

Explicitly disallowed FR-070 inputs in v1:

- embedding vectors
- social media API data
- PII or email addresses

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `viral_recipient.enabled`
- `viral_recipient.ranking_weight`
- `viral_recipient.lookback_days`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `lookback_days = 90`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `7 <= lookback_days <= 365`

### Feature-flag behaviour

- `enabled = false` -> `score = 0.5`, state `neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0` -> compute and store diagnostics, no ranking impact

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `ContentItem.viral_recipient_diagnostics`

Required fields:

- `score_viral_recipient`
- `viral_recipient_state` (`computed`, `neutral_feature_disabled`, `neutral_insufficient_visitors`, `neutral_processing_error`)
- `visitor_count` -- distinct user count in lookback window
- `mean_authority` -- average authority of visitors
- `authority_distribution` -- histogram buckets (low/medium/high) for operator review
- `lookback_days` -- setting value used

Plain-English review helper text should say:

- `Recipient ranking measures the quality of the users who visit this page.`
- `A high score means the page attracts engaged, returning visitors -- not just drive-by traffic.`
- `Neutral means there were not enough visitors to compute a reliable authority score.`

## Storage / Model / API Impact

### Content model

Add:

- `score_viral_recipient: FloatField(default=0.5)`
- `viral_recipient_diagnostics: JSONField(default=dict, blank=True)`

### PipelineRun snapshot

Add FR-070 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/viral-recipient/`
- `PUT /api/settings/viral-recipient/`

### Review / admin / frontend

Add one new review row: `Viral Recipient Ranking`

Add one settings card:

- enabled toggle
- ranking weight slider
- lookback days slider

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"viral_recipient.enabled": "true",
"viral_recipient.ranking_weight": "0.02",
"viral_recipient.lookback_days": "90",
```

**Why these values:**

- `ranking_weight = 0.02` -- conservative starting point. Recipient authority is derived data, not directly observed quality.
- `lookback_days = 90` -- three months gives a stable visitor profile without counting stale historical traffic.
