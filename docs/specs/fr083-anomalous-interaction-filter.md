# FR-083 - Anomalous Interaction Pattern Filter

## Confirmation

- **Backlog confirmed**: `FR-083 - Anomalous Interaction Pattern Filter` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No engagement anomaly detection signal exists in the current ranker. The closest signal is FR-079 (spam interaction filter), which detects bot accounts. FR-083 detects anomalous engagement timing patterns (one-burst-then-silence) regardless of account type -- a fundamentally different detection axis.
- **Repo confirmed**: GA4 engagement data with timestamps is already ingested via the analytics sync pipeline.

## Source Summary

### Patent: EP3497609B1 -- Anomalous Interaction Pattern Filter

**Plain-English description of the patent:**

The patent describes detecting statistical anomalies in engagement timing patterns. Genuine engagement tends to follow organic patterns (gradual growth, steady interest, natural decay). Artificial engagement tends to appear as sudden bursts followed by complete silence -- a signature of coordinated boosting campaigns.

**What is adapted for this repo:**

- "engagement pattern" maps to GA4 session and event timestamps aggregated into daily buckets;
- a z-score of the largest engagement burst relative to the page's baseline detects anomalous spikes;
- pages with anomalous patterns are penalized.

## Plain-English Summary

Simple version first.

Genuine page popularity looks natural -- traffic grows gradually, stays for a while, and decays slowly. Artificial boosting looks different -- a huge spike of engagement appears out of nowhere and then drops to zero.

FR-083 detects this pattern using z-scores. If a page's biggest engagement spike is statistically unusual compared to its own baseline (z-score above threshold), the engagement is probably artificial.

This is different from FR-079 (which looks at who is visiting) because FR-083 looks at when they visit.

## Problem Statement

Today the ranker trusts all engagement patterns equally. A page that received 10,000 sessions in one day and then zero for the next 30 days appears well-engaged, but the pattern is suspicious.

FR-083 closes this gap by detecting anomalous timing patterns in engagement data.

## Goals

FR-083 should:

- add a separate, explainable, bounded anomaly detection signal;
- compute z-scores of engagement bursts relative to the page's baseline;
- penalize pages with anomalous burst patterns;
- keep pages with organic engagement patterns unaffected;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-083 does not:

- identify specific bad actors;
- modify FR-079 (spam account filter);
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `E = [e_1, e_2, ..., e_n]` = daily engagement counts for the page over the lookback window
- `mu` = mean(E)
- `sigma` = std(E)
- `burst_magnitude` = max(E)

**Burst z-score:**

```text
z = (burst_magnitude - mu) / max(sigma, 1)
```

**Anomaly score via inverse sigmoid:**

```text
score_anomaly_filter = 1 - sigmoid(z - burst_z_threshold)
                     = 1 - 1 / (1 + exp(-(z - burst_z_threshold)))
```

Where `burst_z_threshold` = 3.0 (default).

This maps:

- `z << 3` (normal engagement pattern) -> `score ~ 1.0` (no penalty)
- `z = 3` (at threshold) -> `score = 0.5`
- `z >> 3` (extremely anomalous burst) -> `score ~ 0.0` (maximum penalty)

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_anomaly_filter
```

**Neutral fallback:**

```text
score_anomaly_filter = 0.5
```

Used when:

- fewer than 14 days of engagement data;
- standard deviation is near zero (no variation to measure against);
- feature is disabled.

### Why z-score

Z-scores are the standard statistical measure for "how unusual is this observation." They are unit-free, comparable across pages with different traffic levels, and have well-understood thresholds (z > 3 is conventionally "highly unusual").

### Ranking hook

```text
score_anomaly_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += anomaly_filter.ranking_weight * score_anomaly_component
```

## Scope Boundary Versus Existing Signals

FR-083 must stay separate from:

- `FR-079` spam filter -- detects bot accounts by identity, not timing patterns.
- `FR-072` trending velocity -- measures 6-hour acceleration, not burst anomaly detection.
- `FR-080` freshness decay -- measures long-term decay curve, not individual burst events.

## Inputs Required

- GA4 daily engagement counts per page -- from existing analytics sync
- At least 14 days of data for reliable z-score computation

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `anomaly_filter.enabled`
- `anomaly_filter.ranking_weight`
- `anomaly_filter.burst_z_threshold`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `burst_z_threshold = 3.0`

## Diagnostics And Explainability Plan

Required fields:

- `score_anomaly_filter`
- `anomaly_filter_state` (`computed`, `neutral_feature_disabled`, `neutral_insufficient_data`, `neutral_processing_error`)
- `burst_z_score` -- z-score of largest burst
- `mean_daily_engagement` -- baseline mean
- `std_daily_engagement` -- baseline standard deviation
- `max_daily_engagement` -- peak day engagement
- `days_of_data` -- number of days analysed

Plain-English review helper text should say:

- `Anomalous interaction filter detects engagement patterns that look artificially inflated.`
- `A high score means engagement patterns look organic. A low score means a suspicious burst was detected.`

## Storage / Model / API Impact

### Content model

Add:

- `score_anomaly_filter: FloatField(default=0.5)`
- `anomaly_filter_diagnostics: JSONField(default=dict, blank=True)`

### Backend API

Add:

- `GET /api/settings/anomaly-filter/`
- `PUT /api/settings/anomaly-filter/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"anomaly_filter.enabled": "true",
"anomaly_filter.ranking_weight": "0.02",
"anomaly_filter.burst_z_threshold": "3.0",
```
