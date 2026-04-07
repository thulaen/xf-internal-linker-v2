# FR-080 - Content Freshness Decay Rate

## Confirmation

- **Backlog confirmed**: `FR-080 - Content Freshness Decay Rate` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No engagement decay or evergreen scoring signal exists in the current ranker. The closest signal is `FR-007` (link freshness), which measures when links appeared or disappeared. FR-080 measures how quickly engagement decays after publication -- a fundamentally different axis.
- **Repo confirmed**: GA4 weekly engagement data is already ingested via the analytics sync pipeline.

## Source Summary

### Patent: US8832088B1 -- Content Freshness Decay Rate (Google)

**Plain-English description of the patent:**

The patent describes measuring how quickly a document's relevance or engagement decays over time. Evergreen content (guides, reference material) maintains engagement for months or years. News-style content spikes and then drops rapidly. The decay rate itself is a quality signal -- slow-decaying content is more persistently valuable.

**What is adapted for this repo:**

- "engagement" maps to GA4 weekly session counts;
- an exponential decay model is fitted to weekly engagement data;
- the decay constant lambda determines evergreen vs. ephemeral content;
- slow decay = high score (evergreen), fast decay = low score (ephemeral).

## Plain-English Summary

Simple version first.

Some pages stay popular for months. Some pages get a burst of traffic and then fade to nothing within a week.

FR-080 fits an exponential decay curve to a page's weekly engagement over time. If engagement fades slowly (lambda is small), the page is evergreen -- it has lasting value. If engagement drops like a stone (lambda is large), the page is ephemeral news content.

Linking to evergreen content is more valuable because the link stays useful over time.

## Problem Statement

Today the ranker has no awareness of whether a destination page's engagement is durable or fleeting. A page with the same total engagement over 6 months scores identically whether the traffic was steady or a one-week spike.

FR-080 closes this gap by measuring engagement durability.

## Goals

FR-080 should:

- add a separate, explainable, bounded freshness decay signal;
- fit an exponential decay model to weekly engagement data;
- reward pages with slow decay (evergreen content);
- require sufficient history (at least `history_weeks` of data);
- keep pages with insufficient data neutral at `0.5`.

## Non-Goals

FR-080 does not:

- modify link freshness (FR-007) or trending velocity (FR-072);
- predict future traffic;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `E(t)` = engagement at week `t` after publication
- `E_0` = peak engagement
- `lambda` = decay constant (fitted via least-squares on log-transformed weekly data)

**Exponential decay model:**

```text
E(t) = E_0 * exp(-lambda * t)
```

Fitting: take `log(E(t)) = log(E_0) - lambda * t` and solve via linear regression on `(t, log(E(t)))` for weeks where `E(t) > 0`.

**Score:**

```text
score_freshness_decay = 1 / (1 + lambda)
```

This maps:

- `lambda = 0` (no decay, perfectly evergreen) -> `score = 1.0`
- `lambda = 1` (engagement halves every ~0.7 weeks) -> `score = 0.5`
- `lambda >> 1` (extremely fast decay) -> `score -> 0.0`

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_freshness_decay
```

**Neutral fallback:**

```text
score_freshness_decay = 0.5
```

Used when:

- fewer than `history_weeks` (default 26) weeks of engagement data;
- page is too new to have a decay pattern;
- feature is disabled.

### Ranking hook

```text
score_decay_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += freshness_decay_rate.ranking_weight * score_decay_component
```

## Scope Boundary Versus Existing Signals

FR-080 must stay separate from:

- `FR-007` link freshness -- measures link appearance timing, not engagement decay.
- `FR-072` trending velocity -- measures short-term acceleration, not long-term decay.
- `FR-050` seasonality -- measures cyclical patterns, not monotonic decay.
- `FR-057` content-update magnitude -- measures edit substance, not engagement durability.

## Inputs Required

- GA4 weekly engagement data per page -- from existing analytics sync
- At least 26 weeks of data for reliable fitting

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `freshness_decay_rate.enabled`
- `freshness_decay_rate.ranking_weight`
- `freshness_decay_rate.history_weeks`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `history_weeks = 26`

## Diagnostics And Explainability Plan

Required fields:

- `score_freshness_decay`
- `freshness_decay_state` (`computed`, `neutral_feature_disabled`, `neutral_insufficient_history`, `neutral_processing_error`)
- `decay_lambda` -- fitted decay constant
- `peak_engagement` -- E_0 value
- `weeks_of_data` -- number of weeks used for fitting
- `r_squared` -- goodness of fit for the exponential model

Plain-English review helper text should say:

- `Content freshness decay rate measures how quickly this page's engagement fades over time.`
- `A high score means the page is evergreen -- its traffic holds up over many weeks.`
- `A low score means the page is ephemeral -- traffic spikes and then drops.`

## Storage / Model / API Impact

### Content model

Add:

- `score_freshness_decay: FloatField(default=0.5)`
- `freshness_decay_diagnostics: JSONField(default=dict, blank=True)`

### Backend API

Add:

- `GET /api/settings/freshness-decay-rate/`
- `PUT /api/settings/freshness-decay-rate/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"freshness_decay_rate.enabled": "true",
"freshness_decay_rate.ranking_weight": "0.02",
"freshness_decay_rate.history_weeks": "26",
```

**Why these values:**

- `ranking_weight = 0.02` -- conservative. Decay rate is useful but contextual; news sites legitimately have fast decay.
- `history_weeks = 26` -- six months gives enough data to fit a reliable decay curve.
