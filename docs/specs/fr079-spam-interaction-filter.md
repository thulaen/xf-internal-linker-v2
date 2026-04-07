# FR-079 - Spam Account Interaction Filter

## Confirmation

- **Backlog confirmed**: `FR-079 - Spam Account Interaction Filter` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No spam detection or bot-engagement filtering signal exists in the current ranker. All engagement signals (FR-024, FR-072) treat bot traffic the same as human traffic.
- **Repo confirmed**: GA4 session data with client-level metadata is already ingested via the analytics sync pipeline.

## Source Summary

### Patent: WO2013140410A1 -- Spam Account Interaction Filter

**Plain-English description of the patent:**

The patent describes detecting when engagement metrics for a piece of content are inflated by spam or bot accounts. Genuine engagement from real users should be distinguished from artificial engagement from automated accounts. Content whose engagement is dominated by flagged accounts should be penalized.

**What is adapted for this repo:**

- "spam accounts" maps to GA4 sessions flagged by bot-detection heuristics (sub-second sessions, repetitive patterns, known bot user agents);
- the penalty is proportional to the ratio of flagged interactions to total interactions;
- applied as a quality filter, not a content removal mechanism.

## Plain-English Summary

Simple version first.

Some pages have inflated engagement numbers because bots or spam accounts visited them. A page with 1000 sessions where 800 are from bots is not genuinely popular -- its engagement numbers are fake.

FR-079 detects this by measuring the ratio of flagged (bot/spam) interactions to total interactions. Pages with a high spam ratio get penalized. Pages with clean engagement are unaffected.

## Problem Statement

Today the ranker trusts all engagement data equally. Bot traffic inflates engagement signals (FR-024, FR-072, FR-075), making some pages appear more popular than they actually are.

FR-079 closes this gap by penalizing pages whose engagement is dominated by flagged interactions.

## Goals

FR-079 should:

- add a separate, explainable, bounded spam filter signal;
- compute the ratio of flagged interactions to total interactions;
- penalize pages with high spam ratios;
- require a minimum interaction count before applying the penalty;
- keep pages with clean engagement unaffected (score 1.0).

## Non-Goals

FR-079 does not:

- build a sophisticated ML-based bot detection system;
- remove or modify existing engagement data;
- block traffic;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `flagged` = count of interactions from sessions flagged as bot/spam (sub-1s duration, known bot UA, repetitive IP patterns)
- `total` = total interactions on the page in the lookback window

**Spam ratio:**

```text
spam_ratio = flagged / max(total, 1)
```

**Score:**

```text
score_spam_filter = 1 - spam_ratio
```

This maps:

- `spam_ratio = 0.0` (all clean) -> `score = 1.0` (no penalty)
- `spam_ratio = 0.5` (half spam) -> `score = 0.5`
- `spam_ratio = 1.0` (all spam) -> `score = 0.0` (maximum penalty)

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_spam_filter
```

Maps to `[0.5, 1.0]` so even heavily spammed pages are not driven below neutral.

**Neutral fallback:**

```text
score_spam_filter = 0.5
```

Used when:

- total interactions below `min_interactions` (default 10);
- bot detection data unavailable;
- feature is disabled.

### Ranking hook

```text
score_spam_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += spam_filter.ranking_weight * score_spam_component
```

## Scope Boundary Versus Existing Signals

FR-079 must stay separate from:

- `FR-024` engagement -- FR-079 filters engagement quality, not quantity.
- `FR-083` anomalous interaction -- FR-083 detects burst timing anomalies, not bot/spam account ratios.
- `FR-070` viral recipient -- FR-070 measures visitor quality (authority), not spam detection.

## Inputs Required

- GA4 session metadata (duration, user agent, IP patterns)
- Bot/spam flagging heuristics (applied at analytics sync time)

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `spam_filter.enabled`
- `spam_filter.ranking_weight`
- `spam_filter.min_interactions`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `min_interactions = 10`

## Diagnostics And Explainability Plan

Required fields:

- `score_spam_filter`
- `spam_filter_state` (`computed`, `neutral_feature_disabled`, `neutral_insufficient_data`, `neutral_processing_error`)
- `total_interactions` -- total interaction count
- `flagged_interactions` -- bot/spam flagged count
- `spam_ratio` -- raw ratio

Plain-English review helper text should say:

- `Spam interaction filter measures what proportion of this page's engagement comes from bot or spam accounts.`
- `A high score means the page's engagement is genuine. A low score means bots dominate the traffic.`

## Storage / Model / API Impact

### Content model

Add:

- `score_spam_filter: FloatField(default=0.5)`
- `spam_filter_diagnostics: JSONField(default=dict, blank=True)`

### Backend API

Add:

- `GET /api/settings/spam-filter/`
- `PUT /api/settings/spam-filter/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"spam_filter.enabled": "true",
"spam_filter.ranking_weight": "0.02",
"spam_filter.min_interactions": "10",
```
