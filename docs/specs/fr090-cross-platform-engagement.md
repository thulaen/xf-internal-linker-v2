# FR-090 - Cross-Platform Engagement Correlation

## Confirmation

- **Backlog confirmed**: `FR-090 - Cross-Platform Engagement Correlation` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No multi-platform or cross-platform engagement signal exists in the current ranker. All existing engagement signals measure single-source data (GA4 or Matomo or GSC independently). FR-090 detects simultaneous engagement spikes across multiple platforms -- a fundamentally different signal.
- **Repo confirmed**: GA4, Matomo, and GSC data are all ingested via their respective sync pipelines and are available at index time.

## Source Summary

### Patent: US20140244006A1 -- Cross-Platform Engagement Correlation (Google)

**Plain-English description of the patent:**

The patent describes detecting when content receives simultaneous engagement spikes across multiple platforms. Content that spikes on a single platform might be the result of platform-specific gaming (bot traffic, algorithmic boosting). Content that spikes on multiple platforms simultaneously is genuinely resonating with audiences -- the cross-platform correlation is a strong quality signal.

**What is adapted for this repo:**

- "platforms" maps to GA4, Matomo, and GSC (the three data sources already connected);
- "spike" is defined as a z-score above threshold (default 2.0) in a given time window;
- the score counts how many platforms show a simultaneous spike.

## Plain-English Summary

Simple version first.

When a page suddenly gets more traffic from Google Search, more direct visits tracked by GA4, and more pageviews in Matomo -- all at the same time -- it is probably genuinely popular. A spike on just one platform could be a glitch or manipulation, but simultaneous spikes across three independent platforms is strong evidence of real interest.

FR-090 counts how many platforms show a simultaneous engagement spike for each page. More platforms spiking at the same time = higher score.

## Problem Statement

Today the ranker treats engagement from each platform independently. It cannot detect the powerful signal of cross-platform resonance -- when a page simultaneously trends across GA4, Matomo, and GSC.

FR-090 closes this gap by correlating engagement spikes across all three data sources.

## Goals

FR-090 should:

- add a separate, explainable, bounded cross-platform engagement signal;
- detect simultaneous spikes (z > threshold) across GA4, Matomo, and GSC;
- score based on the fraction of platforms showing simultaneous spikes;
- keep pages without multi-platform data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-090 does not:

- combine engagement values across platforms (no summing GA4 + Matomo sessions);
- modify any individual platform's engagement signal;
- add new data source connections;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `P = {GA4, Matomo, GSC}` = set of connected data platforms
- For each platform `p`, compute the z-score of recent engagement relative to the page's baseline:

```text
z_p = (engagement_recent_p - mu_p) / max(sigma_p, 1)
```

Where:
- `engagement_recent_p` = engagement in the most recent lookback window from platform `p`
- `mu_p` = historical mean engagement from platform `p`
- `sigma_p` = historical standard deviation from platform `p`

**Spike detection per platform:**

```text
is_spiking(p) = 1 if z_p > spike_z_threshold else 0
```

Default `spike_z_threshold = 2.0`.

**Cross-platform score:**

```text
spiking_platforms = sum(is_spiking(p) for p in P)
score_cross_platform = spiking_platforms / |P|
```

This maps:

- 0 platforms spiking -> `score = 0.0`
- 1 of 3 spiking -> `score = 0.33`
- 2 of 3 spiking -> `score = 0.67`
- 3 of 3 spiking -> `score = 1.0`

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_cross_platform
```

**Neutral fallback:**

```text
score_cross_platform = 0.5
```

Used when:

- fewer than 2 platforms have data for this page;
- insufficient historical baseline for z-score computation;
- feature is disabled.

### Why z-score per platform

Each platform has different engagement scales (GA4 sessions vs. GSC clicks vs. Matomo pageviews). Z-scores normalize each platform's engagement to its own distribution, making cross-platform comparison valid.

### Ranking hook

```text
score_crossplat_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += cross_platform_engagement.ranking_weight * score_crossplat_component
```

## Scope Boundary Versus Existing Signals

FR-090 must stay separate from:

- `FR-072` trending velocity -- measures single-platform acceleration, not cross-platform correlation.
- `FR-024` engagement -- measures single-platform read-through, not multi-platform spikes.
- `FR-083` anomaly filter -- detects suspicious patterns on a single platform, not cross-platform validation.

The key insight: FR-090 uses cross-platform agreement as a *validation* signal. If engagement spikes on all platforms at once, it is almost certainly real, not artificial.

## Inputs Required

- GA4 session data with timestamps -- from existing analytics sync
- Matomo pageview data with timestamps -- from existing Matomo sync
- GSC click/impression data with dates -- from existing GSC sync
- Historical baselines per platform per page

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `cross_platform_engagement.enabled`
- `cross_platform_engagement.ranking_weight`
- `cross_platform_engagement.spike_z_threshold`
- `cross_platform_engagement.lookback_days`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `spike_z_threshold = 2.0`
- `lookback_days = 30`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `1.0 <= spike_z_threshold <= 5.0`
- `7 <= lookback_days <= 90`

## Diagnostics And Explainability Plan

Required fields:

- `score_cross_platform`
- `cross_platform_state` (`computed`, `neutral_feature_disabled`, `neutral_insufficient_platforms`, `neutral_processing_error`)
- `platform_z_scores` -- dict of {platform: z_score} for each connected platform
- `spiking_platforms` -- list of platform names currently spiking
- `spike_count` -- number of platforms spiking
- `total_platforms` -- number of platforms with data
- `spike_z_threshold` -- threshold used

Plain-English review helper text should say:

- `Cross-platform engagement measures whether this page is simultaneously trending on multiple data platforms.`
- `A high score means GA4, Matomo, and/or GSC all show engagement spikes at the same time -- strong evidence of genuine interest.`
- `A single-platform spike is less reliable; cross-platform agreement validates the signal.`

## Storage / Model / API Impact

### Content model

Add:

- `score_cross_platform: FloatField(default=0.5)`
- `cross_platform_diagnostics: JSONField(default=dict, blank=True)`

### PipelineRun snapshot

Add FR-090 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/cross-platform-engagement/`
- `PUT /api/settings/cross-platform-engagement/`

### Review / admin / frontend

Add one new review row: `Cross-Platform Engagement`

Add one settings card:

- enabled toggle
- ranking weight slider
- spike z-score threshold
- lookback days

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"cross_platform_engagement.enabled": "true",
"cross_platform_engagement.ranking_weight": "0.02",
"cross_platform_engagement.spike_z_threshold": "2.0",
"cross_platform_engagement.lookback_days": "30",
```

**Why these values:**

- `ranking_weight = 0.02` -- conservative. Cross-platform signals are powerful but need validation against real data.
- `spike_z_threshold = 2.0` -- z > 2.0 corresponds to roughly the top 2.3% of the distribution. Strict enough to avoid false positives, lenient enough to catch genuine trends.
- `lookback_days = 30` -- one month gives enough data for reliable z-score computation while staying responsive to recent trends.
