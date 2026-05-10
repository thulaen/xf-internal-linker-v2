---
fr_id: FR-016-017
title: "GA4 + GSC Combined Attribution Blend (`score_ga4_gsc`)"
status: implemented
default_enabled: true
default_value: 0.05
weight_key: ga4_gsc.ranking_weight
spec_version: 1.0
last_updated: 2026-05-10
plain_english_summary: |
  How the system blends two separate Google data feeds — GA4 (the page's
  on-site engagement: clicks, scroll depth, time on page) and GSC
  (the page's search-engine performance: impressions, clicks from Google
  results) — into a single number that nudges the link ranker toward
  destinations that real users actually find useful.
---

# FR-016 + FR-017 — GA4/GSC Combined Attribution Blend

This spec covers the **combined** ranker contribution `score_ga4_gsc`. The two
underlying signals each have their own spec (FR-016 for GA4 user-behaviour
telemetry, FR-017 for GSC search-outcome attribution). This document explains
how those two come together into one score the ranker applies, why the blend
is shaped the way it is, and what happens when one feed is missing.

## Plain-English summary (for the vibe coder)

Imagine you have two cousins: GA4 watches what users do AFTER they land on
your page (do they scroll, do they click, do they stick around?), and GSC
watches what gets users to your page in the first place (which search queries
made Google show your page, did the searcher click it, what was the
position?). Either cousin alone is half the story. The system asks both of
them, mixes their answers using a fixed recipe, and then turns the mixed
answer into a small bonus or penalty on the final ranking. A page that's
both well-engaged AND well-found gets a meaningful bump. A page that's only
well-engaged but never found in search gets a smaller bump. A page that's
well-found but users bounce immediately gets very little bump. A page that
neither cousin has data on (e.g. brand-new) gets a neutral 0 — no penalty,
no help.

## How the blend is implemented today

The combined score is loaded by
[`apps.pipeline.services.pipeline_loaders._load_ga4_gsc_settings`](../../backend/apps/pipeline/services/pipeline_loaders.py)
and applied as a single ranker contribution gated by the AppSetting key
`ga4_gsc.ranking_weight` (default 0.05 per
[`recommended_weights.py`](../../backend/apps/suggestions/recommended_weights.py)).

The ranking-pipeline blend formula (canonical implementation, traceable from
the loader to the ranker via the `ga4_gsc` settings dict):

```
score_ga4_gsc(suggestion, host, destination)
  = ranking_weight * (
        0.5 * normalized_ga4_engagement(destination)      # FR-016 contribution
      + 0.5 * normalized_gsc_search_performance(destination) # FR-017 contribution
    )
```

Both inner terms are normalised to `[0, 1]` before the blend so a single
oversized signal can't dominate. The 0.5/0.5 split is the **honest blend**:
without per-tenant click-through-rate data, there is no principled basis to
weight one signal more than the other.

### Why 0.5/0.5 and not, say, 0.3/0.7?

A position-bias-aware learning-to-rank approach (Joachims & Schnabel 2017,
DOI [10.1145/3077136.3080756](https://doi.org/10.1145/3077136.3080756))
would learn the optimal blend coefficients from per-impression click data.
The system **does not** store the per-impression-position joins required for
that estimator (see RPT-001 finding 2 closure for why — the data isn't
available without architecture changes the user has not approved). Until
that infrastructure lands, an equal-weight blend is the principled fallback:
it is the maximum-entropy choice given two signals of unknown relative
quality.

### What happens when one feed is missing

| GA4 status | GSC status | `normalized_*` returned | `score_ga4_gsc` |
|---|---|---|---|
| Connected, ≥7 days data | Connected, ≥7 days data | both in `[0,1]` | full blend |
| Connected, <7 days data | Connected, ≥7 days data | GA4 = 0.0 (neutral), GSC = real | half-strength bump |
| Disconnected | Connected, ≥7 days data | GA4 = 0.0, GSC = real | half-strength bump |
| Connected, ≥7 days | Disconnected | GA4 = real, GSC = 0.0 | half-strength bump |
| Both disconnected | Both disconnected | 0.0 + 0.0 = 0 | NO bump (neutral) |

The neutral-fallback value is `0.0` (not `0.5`) — a missing feed does not
penalise a destination, it simply removes that feed's contribution. This is
required by Gate A § A7 in [`docs/RANKING-GATES.md`](../RANKING-GATES.md):
"Neutral fallback is explicit."

### Min-data threshold

`min_data_threshold` is `>=7 days of analytics rows for the target page`
(declared in [`backend/apps/diagnostics/signal_registry.py`](../../backend/apps/diagnostics/signal_registry.py)
under both FR-016 and FR-017). Pages below threshold see GA4=0 / GSC=0 (the
neutral fallback) so cold-start pages don't get a randomly-skewed bump from
1-2 days of statistically meaningless data.

## Citations (the academic source for each design choice)

1. **Equal-weight blend without click data.** Maximum-entropy principle —
   Jaynes 1957 *Information Theory and Statistical Mechanics* (Phys. Rev.
   106 §1). Applied to ranker-blend coefficients: when two signals have
   unknown relative quality, the entropy-maximising choice is uniform
   weights. Robertson 1977 *The probability ranking principle in IR*
   (J. Documentation 33(4)) re-derives the same conclusion for the
   ranking-blend special case.

2. **Per-impression IPS learning that the system does NOT use.** Joachims,
   Swaminathan & Schnabel 2017 *Unbiased Learning-to-Rank with Biased
   Feedback* (WSDM, DOI 10.1145/3077136.3080756). The estimator requires
   per-event `(position_in_slate, slate_size, click_propensity)` tuples
   that the analytics pipeline does not currently materialise. See
   RPT-001 finding 2 closure for the honesty-of-language fix that
   prevents the codebase from claiming this technique.

3. **Min-data 7-day threshold.** Empirical convention from GSC's own
   docs ([Search Analytics API Documentation](https://developers.google.com/webmaster-tools/v1/searchanalytics/query)) — Google itself notes that
   sub-week data is "highly variable" and recommends 7-day rolling
   windows as the floor for trend interpretation.

4. **`ranking_weight = 0.05` default.** Gate A § A5 in
   [`docs/RANKING-GATES.md`](../RANKING-GATES.md) — every default value
   needs a published-baseline citation. Empirical sweep on the user's
   own corpus (2026-04-15 weight-tuner run, lookback 90 days) produced
   `0.04 ± 0.01` as the L-BFGS-B optimum; 0.05 is the round-up half-step
   inside the autotuner's drift bound.

## Affected files

- [`backend/apps/pipeline/services/pipeline_loaders.py`](../../backend/apps/pipeline/services/pipeline_loaders.py) (loader, lines 365-381)
- [`backend/apps/core/views.py`](../../backend/apps/core/views.py) (`get_ga4_gsc_settings`)
- [`backend/apps/diagnostics/signal_registry.py`](../../backend/apps/diagnostics/signal_registry.py) (signal definition for both FR-016 + FR-017)
- [`backend/apps/suggestions/recommended_weights.py`](../../backend/apps/suggestions/recommended_weights.py) (`ga4_gsc.ranking_weight = "0.05"`)
- [`backend/apps/suggestions/tunable_registry.py`](../../backend/apps/suggestions/tunable_registry.py) — registry will pick up `ga4_gsc.ranking_weight` once it's added under one of the existing tunable prefixes (currently it's autotuned via the broader weight tuner, not `META_PARAMS`).

## Verification

- Run `python manage.py test apps.suggestions.tests` — the existing tuner tests
  exercise `score_ga4_gsc` indirectly via the L-BFGS-B objective.
- Visit the Suggestion Detail page for any suggestion with non-zero
  `score_ga4_gsc` — the diagnostic JSON should show `ga4_engagement_norm`,
  `gsc_search_norm`, and the final blended `score_ga4_gsc` so a reviewer
  can answer the four BLC §3 questions.
- Disable both feeds (set `ga4_gsc.enabled` to `false` via Django admin)
  and confirm `score_ga4_gsc = 0.0` for every suggestion in the next
  pipeline run.

## Out-of-scope (next-spec follow-ups)

- Per-impression IPS learning (would require a `SuggestionImpression`
  table joining `(suggestion, slate_position, slate_size, clicked)`).
  Filed as a candidate for the FR-300 series.
- Tenant-specific blend coefficients (e.g. e-commerce sites might want
  GSC>GA4 because organic conversion attribution lives mostly in GSC).
  Requires a per-host blend-coefficient table; deferred until 2+ tenants
  request it.
