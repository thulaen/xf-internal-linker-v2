# FR-076 - Dwell-Time Interest Profile Match

## Confirmation

- **Backlog confirmed**: `FR-076 - Dwell-Time Interest Profile Match` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No audience attention-span or dwell-time matching signal exists in the current ranker. The closest signal is `FR-024` (read-through rate), which measures individual engagement depth. FR-076 compares audience-level dwell-time patterns between source and destination -- a fundamentally different axis.
- **Repo confirmed**: GA4 session-level dwell-time data is already ingested via the analytics sync pipeline.

## Source Summary

### Patent: US20150127662A1 -- Dwell-Time Interest Profile Match (Google)

**Plain-English description of the patent:**

The patent describes matching content to users based on their attention-span profiles. Users who spend long periods reading detailed content are different from users who skim headlines. Content that matches the audience's typical attention span is more likely to satisfy them.

**Repo-safe reading:**

The patent is user-profile oriented. This repo adapts it to page-level audience profiles. The reusable core idea is:

- compute the typical dwell time of each page's audience;
- prefer linking between pages whose audiences have similar attention spans;
- a reader who spends 5 minutes on the source page expects a destination of similar depth.

**What is adapted for this repo:**

- "user profile" maps to mean dwell time of GA4 sessions on a page;
- "match" maps to exponential decay of the dwell-time difference between source and destination;
- computed at index time from existing GA4 session data.

## Plain-English Summary

Simple version first.

A reader spending 8 minutes on a detailed guide expects the linked destination to be similarly substantial. If the link leads to a 30-second FAQ page, the reader is likely to feel the link was not useful.

FR-076 matches the attention-span profile of the source page's audience with the destination page's audience. When both pages attract readers who spend similar amounts of time, the link is a better match.

## Problem Statement

Today the ranker has no awareness of reading depth expectations. It can link a long-form guide (where readers spend 8 minutes) to a thin stub page (where readers spend 15 seconds), creating a mismatch in content depth.

FR-076 closes this gap by measuring audience attention-span alignment.

## Goals

FR-076 should:

- add a separate, explainable, bounded dwell-time matching signal;
- compute it from GA4 session-level dwell-time data at index time;
- reward source-destination pairs where audiences have similar attention spans;
- keep pages with insufficient session data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-076 does not:

- track individual users;
- modify read-through rate (FR-024) or any engagement signal;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `mu_src` = mean dwell time (seconds) of GA4 sessions on the source page
- `mu_dst` = mean dwell time (seconds) of GA4 sessions on the destination page
- `tau` = `decay_seconds` parameter (default 60)

**Exponential decay of dwell-time difference:**

```text
score_dwell_profile_match = exp(-|mu_src - mu_dst| / tau)
```

This maps:

- `|mu_src - mu_dst| = 0` (identical attention spans) -> `score = 1.0`
- `|mu_src - mu_dst| = tau` (60-second difference) -> `score = 0.368`
- `|mu_src - mu_dst| = 2 * tau` (120-second difference) -> `score = 0.135`

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_dwell_profile_match
```

This maps the range to `[0.5, 1.0]` so mismatched attention spans are neutral, not penalizing.

**Neutral fallback:**

```text
score_dwell_profile_match = 0.5
```

Used when:

- either page has fewer than 10 sessions with valid dwell-time data;
- feature is disabled.

### Why exponential decay

Exponential decay is the natural model for "how much do we care about a difference." Small differences (10 seconds) should barely matter. Large differences (3 minutes) should matter a lot. The `tau` parameter controls the sensitivity.

### Ranking hook

```text
score_dwell_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += dwell_profile_match.ranking_weight * score_dwell_component
```

Default: `ranking_weight = 0.0` -- diagnostics only until validated.

## Scope Boundary Versus Existing Signals

FR-076 must stay separate from:

- `FR-024` engagement read-through -- measures individual scroll depth, not audience-level dwell time.
- `FR-075` watch-time completion -- measures video completion, not text reading time.
- `FR-052` readability matching -- measures text complexity (grade level), not observed reading time.

## Inputs Required

- GA4 session-level dwell-time data per page -- from existing analytics sync

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `dwell_profile_match.enabled`
- `dwell_profile_match.ranking_weight`
- `dwell_profile_match.decay_seconds`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `decay_seconds = 60`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `10 <= decay_seconds <= 300`

## Diagnostics And Explainability Plan

Required fields:

- `score_dwell_profile_match`
- `dwell_profile_state` (`computed`, `neutral_feature_disabled`, `neutral_insufficient_data`, `neutral_processing_error`)
- `source_mean_dwell_seconds` -- mean dwell time on source page
- `destination_mean_dwell_seconds` -- mean dwell time on destination page
- `dwell_difference_seconds` -- absolute difference
- `source_session_count` -- number of sessions used for source
- `destination_session_count` -- number of sessions used for destination

Plain-English review helper text should say:

- `Dwell-time profile match measures whether the source and destination pages attract readers with similar attention spans.`
- `A high score means both pages' audiences spend similar amounts of time reading.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_dwell_profile_match: FloatField(default=0.5)`
- `dwell_profile_diagnostics: JSONField(default=dict, blank=True)`

Note: This is pair-specific (source x destination), so it lives on the Suggestion model.

### PipelineRun snapshot

Add FR-076 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/dwell-profile-match/`
- `PUT /api/settings/dwell-profile-match/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"dwell_profile_match.enabled": "true",
"dwell_profile_match.ranking_weight": "0.02",
"dwell_profile_match.decay_seconds": "60",
```

**Why these values:**

- `ranking_weight = 0.02` -- conservative. Dwell-time matching is a soft signal that complements relevance.
- `decay_seconds = 60` -- a 60-second difference halves the score. This allows moderate variation while penalizing extreme mismatches.
