# FR-077 - Geographic Engagement Concentration

## Confirmation

- **Backlog confirmed**: `FR-077 - Geographic Engagement Concentration` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No geographic diversity or concentration signal exists in the current ranker. No existing signal measures how geographically spread or concentrated a page's engagement is.
- **Repo confirmed**: GA4 geographic session data (country-level) is already ingested via the analytics sync pipeline.

## Source Summary

### Patent: US20080086264A1 -- Geographic Engagement Concentration (Google)

**Plain-English description of the patent:**

The patent describes measuring the geographic diversity of content engagement. Content that appeals to a broad geographic audience is generally more universally relevant than content that only resonates in one specific region.

**Repo-safe reading:**

The patent is search-oriented. This repo applies the concept to internal linking. The reusable core idea is:

- measure how geographically concentrated or spread a page's engagement is;
- prefer linking to broadly appealing pages when the source page itself has a broad audience;
- use the Herfindahl-Hirschman Index (HHI) as the concentration measure.

**What is adapted for this repo:**

- "geographic distribution" maps to GA4 country-level session shares;
- HHI is computed from country engagement proportions;
- score = 1 - HHI (high score = broad appeal).

## Plain-English Summary

Simple version first.

Some pages are popular worldwide. Some pages are only popular in one country. When a source page has a global audience, linking to a destination that only appeals to one region is suboptimal.

FR-077 uses the Herfindahl index to measure geographic concentration. A page with evenly spread engagement across many countries scores high (broad appeal). A page where 90% of engagement comes from one country scores low (hyper-local).

## Problem Statement

Today the ranker has no awareness of geographic audience patterns. A globally popular source page might link to a destination that only resonates with a single-country audience, reducing the link's value for most readers.

FR-077 closes this gap by measuring geographic engagement spread.

## Goals

FR-077 should:

- add a separate, explainable, bounded geographic concentration signal;
- compute it as 1 minus the Herfindahl index of country engagement shares;
- reward pages with geographically diverse engagement;
- keep pages with insufficient geographic data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-077 does not:

- perform language detection or translation;
- modify any existing engagement signal;
- use IP-level geolocation beyond GA4 country data;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `s_c` = share of total engagement from country `c` (proportion, sums to 1.0)
- `C` = set of countries with non-zero engagement

**Herfindahl-Hirschman Index (HHI):**

```text
H = sum(s_c^2 for c in C)
```

HHI ranges from `1/|C|` (perfectly even distribution) to `1.0` (all engagement from one country).

**Geographic diversity score:**

```text
score_geo_concentration = 1 - H
```

This maps:

- `H = 1.0` (single country) -> `score = 0.0` (hyper-local)
- `H = 0.1` (10 countries, evenly split) -> `score = 0.9` (broad appeal)
- `H = 0.5` (moderately concentrated) -> `score = 0.5`

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_geo_concentration
```

Maps to `[0.5, 1.0]` so hyper-local pages are neutral, not penalized.

**Neutral fallback:**

```text
score_geo_concentration = 0.5
```

Used when:

- page has fewer than 20 sessions with country data;
- GA4 geographic data is unavailable;
- feature is disabled.

### Why Herfindahl

HHI is the standard econometric measure of market concentration. It handles any number of categories (countries), is bounded, and has well-understood statistical properties. It naturally captures both the number of countries and the evenness of distribution.

### Ranking hook

```text
score_geo_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += geo_concentration.ranking_weight * score_geo_component
```

Default: `ranking_weight = 0.0` -- diagnostics only until validated.

## Scope Boundary Versus Existing Signals

FR-077 must stay separate from:

- `score_engagement` (FR-024) -- measures engagement depth, not geographic spread.
- `FR-072` trending velocity -- measures engagement acceleration, not geography.
- `FR-050` seasonality -- measures temporal patterns, not geographic patterns.

## Inputs Required

- GA4 country-level session data per page -- from existing analytics sync

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `geo_concentration.enabled`
- `geo_concentration.ranking_weight`
- `geo_concentration.lookback_days`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `lookback_days = 90`

## Diagnostics And Explainability Plan

Required fields:

- `score_geo_concentration`
- `geo_concentration_state` (`computed`, `neutral_feature_disabled`, `neutral_insufficient_data`, `neutral_processing_error`)
- `herfindahl_index` -- raw HHI value
- `country_count` -- number of countries with engagement
- `top_country_share` -- proportion from the top country
- `total_sessions_with_geo` -- sessions used for computation

Plain-English review helper text should say:

- `Geographic engagement concentration measures how broadly this page's audience is spread across countries.`
- `A high score means the page appeals to a geographically diverse audience.`

## Storage / Model / API Impact

### Content model

Add:

- `score_geo_concentration: FloatField(default=0.5)`
- `geo_concentration_diagnostics: JSONField(default=dict, blank=True)`

### PipelineRun snapshot

Add FR-077 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/geo-concentration/`
- `PUT /api/settings/geo-concentration/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"geo_concentration.enabled": "true",
"geo_concentration.ranking_weight": "0.02",
"geo_concentration.lookback_days": "90",
```

**Why these values:**

- `ranking_weight = 0.02` -- conservative. Geographic diversity is contextual; some sites legitimately serve a single market.
- `lookback_days = 90` -- three months smooths seasonal geographic variation.
