# FR-045 - Anchor Diversity & Exact-Match Reuse Guard

## Confirmation

- `FR-045` is a new backlog item being added to `FEATURE-REQUESTS.md` in this session.
- Repo confirmed:
  - the live pipeline already stores `Suggestion.repeated_anchor`, but that field is only a warning flag today, not a separate scoring or guardrail system;
  - `FR-008` already chooses candidate anchor phrases;
  - `FR-009` already learns anchor vocabulary from live inbound `ExistingLink.anchor_text`;
  - no separate anchor-diversity scorer, cap, or diagnostics model exists in the current ranker.
- Source check confirmed:
  - the user-supplied patent number `US7814085B1` is not the right primary source for anchor-text repetition or duplicate-anchor weighting;
  - `US7814085B1` is about categorized search-result scoring, not anchor-density spam control;
  - this spec therefore uses Google Search Central guidance plus `US20110238644A1`, which directly discusses duplicated anchor texts and reducing their weight.

## Current Repo Map

### Existing nearby anchor-related logic

- `backend/apps/pipeline/services/phrase_matching.py`
  - selects a candidate anchor phrase from the host sentence.
  - this is the current anchor-generation path.

- `backend/apps/pipeline/services/learned_anchor.py`
  - learns trusted anchor families from inbound live links already present on the site.
  - this is anchor corroboration, not anchor-variety control.

- `backend/apps/pipeline/services/ranker.py`
  - stores `anchor_phrase`, `anchor_confidence`, and multiple score components on `ScoredCandidate`.
  - does not currently score whether a candidate anchor is overused for the destination across existing suggestions.

- `backend/apps/suggestions/models.py`
  - already stores `repeated_anchor: BooleanField`.
  - already has the standard per-feature pattern of one score field plus one diagnostics JSON field.

- `backend/apps/suggestions/serializers.py`
  - already exposes `repeated_anchor` in list/detail review serializers.

### Gap this FR closes

The repo can currently:

- generate an anchor;
- say whether the anchor matches destination phrases well;
- say whether the anchor resembles already-live inbound anchor vocabulary;
- warn if the exact anchor already appears in another suggestion.

The repo cannot currently:

- measure whether one exact anchor surface is becoming too dominant for the same destination;
- softly down-rank that anchor pattern;
- optionally hard-block obviously repetitive anchor spikes;
- explain anchor concentration in review/admin/settings terms.

## Source Summary

### Google Search Central - SEO Link Best Practices

Primary source:

- https://developers.google.com/search/docs/crawling-indexing/links-crawlable

Repo-relevant takeaways:

- Google says good anchor text is descriptive, reasonably concise, and relevant.
- Google explicitly says to write naturally and resist cramming every keyword into the anchor text.
- Google ties over-forced keyword use in anchor text back to keyword stuffing spam policy.

This is the plain-English product rule for this FR:

- anchors should sound natural;
- anchors should not be mechanically repeated or stuffed;
- the system should prefer not to over-concentrate one exact anchor surface for one destination.

### Google Search Central - Spam Policies

Primary source:

- https://developers.google.com/search/docs/essentials/spam-policies

Repo-relevant takeaways:

- Google defines spam as techniques used to deceive users or manipulate ranking systems.
- Google explicitly lists `link spam` and `keyword stuffing` as prohibited patterns.
- keyword stuffing is described as filling content with keywords unnaturally or out of context.

This is the plain-English anti-spam rule for this FR:

- exact-match anchor repetition can become a manipulation pattern if it concentrates too heavily;
- the linker should reduce or block obviously repetitive exact-match reuse before the reviewer sees a spammy pile-up.

### Patent - US20110238644A1, Using Anchor Text With Hyperlink Structures for Web Searches

Primary source:

- https://patents.google.com/patent/US20110238644A1/en

Repo-relevant takeaways:

- the patent says not every anchor text should be treated as independent and equally valuable;
- it explicitly calls out the failure case where a source page includes multiple hyperlinks with the same anchor text to the same destination;
- it says duplicated anchor texts can make a destination look more relevant than it really is;
- it motivates reducing anchor weight when those signals are unreliable.

This is the narrow repo-safe takeaway:

- repeated exact-match anchor surfaces should not be allowed to accumulate weight as if each reuse were fresh evidence;
- the linker should discount repeated exact-match anchor reuse for the same destination.

## Plain-English Summary

Simple version first.

If the linker keeps recommending the same exact phrase for the same destination over and over, it starts to look spammy.

Example:

- destination: `Internal Linking Guide`
- suggested anchors over time:
  - `internal linking guide`
  - `internal linking guide`
  - `internal linking guide`
  - `internal linking guide`

Even if that phrase is technically relevant, the pattern is unhealthy.

FR-045 adds a small anti-spam layer that says:

- repeated exact-match anchors should lose strength when they become too dominant for one destination;
- the system can optionally hard-block extreme repetition;
- review should show the operator why a candidate was penalized or blocked.

## Problem Statement

Today the ranker can produce a good anchor phrase, but it does not control how repetitive the destination's anchor portfolio becomes across active suggestions.

That creates two risks:

1. a reviewer may see repeated exact-match anchors for the same destination and approve them one by one;
2. the suggestion history for one destination can drift toward a keyword-stuffed, unnatural anchor monoculture.

FR-045 adds a separate anchor-diversity layer that measures and controls exact-match reuse without changing phrase matching, learned anchors, or telemetry.

## Goals

FR-045 should:

- add a separate, explainable anchor-diversity score and diagnostics field;
- treat exact normalized anchor reuse for the same destination as the primary anti-spam signal in v1;
- keep missing or tiny history neutral at `0.5`;
- support an optional hard cap for extreme exact-match repetition;
- keep ranking impact bounded and enabled by default with a conservative starting weight;
- preserve the existing `repeated_anchor` review warning while making it more systematic;
- fit the current Django + PostgreSQL + Celery + Angular architecture.

## Non-Goals

FR-045 does not:

- generate anchor text from scratch;
- replace `FR-008` phrase matching;
- replace `FR-009` learned-anchor corroboration;
- use live inbound `ExistingLink.anchor_text` as the history source in v1;
- use embeddings, telemetry, clicks, dwell time, approval rates, or GSC data;
- change `score_semantic`, `score_keyword`, `score_quality`, or any FR-006 through FR-044 signal math;
- create a second destination-diversity layer beside `FR-015`.

## Scope Boundary Versus Past, Present, and Future FRs

### `FR-008` phrase matching

- `FR-008` chooses a plausible anchor phrase from the host sentence.
- `FR-045` scores whether that chosen anchor surface is becoming too repetitive for the destination.
- hard rule:
  - `FR-045` must never rewrite the phrase inventory, phrase-expansion logic, or phrase-match score from `FR-008`.

### `FR-009` learned anchors

- `FR-009` asks whether the candidate anchor resembles trusted live inbound anchor vocabulary.
- `FR-045` asks whether the candidate anchor is overused across active suggestions for the destination.
- hard rule:
  - `FR-045` v1 must use `Suggestion` history, not `ExistingLink.anchor_text`, as its repetition corpus.
  - this prevents collision with `FR-009` and keeps "trusted live vocabulary" separate from "anti-spam concentration control."

### `FR-013` to `FR-015`

- `FR-013` reranks destinations using reviewer outcomes.
- `FR-014` suppresses near-duplicate destinations.
- `FR-015` diversifies the final destination slate.
- `FR-045` must stay at the anchor layer, not the destination layer.
- hard rule:
  - do not use `FR-015` embedding similarity or slot-selection math here.

### `FR-016` to `FR-018`

- `FR-016` collects telemetry.
- `FR-017` measures delayed search outcomes.
- `FR-018` learns from those signals later.
- hard rule:
  - `FR-045` must not use CTR, dwell, engagement, or delayed reward.

### `FR-021` and later value-model work

- `FR-021` is a pre-ranking destination value model.
- `FR-045` is not a destination value signal.
- hard rule:
  - `FR-045` belongs in the main suggestion-scoring path after anchor selection, not in the value model.

## Chosen V1 Interpretation

This feature is intentionally narrow.

V1 measures only:

- exact normalized anchor-surface reuse
- for the same destination
- across active suggestions

Why this narrow scope is chosen:

- it is directly supported by the sources;
- it avoids collision with `FR-009`'s anchor-family logic;
- it avoids subjective semantic grouping of anchor variants;
- it is easy to explain to a non-technical user.

## Data Inputs

### Candidate-time inputs

- `destination_id`
- `candidate.anchor_phrase`
- active historical suggestions for the same destination with statuses:
  - `pending`
  - `approved`
  - `applied`
  - `verified`

### Explicitly excluded inputs in v1

- `ExistingLink.anchor_text`
- destination embeddings
- host embeddings
- GA4 / Matomo / GSC data
- reviewer-approval stats
- search-demand or co-occurrence data

## Normalization Rule

Normalize anchor text using a deterministic surface-normalization pass:

1. lowercase
2. trim leading/trailing whitespace
3. collapse internal whitespace to one space
4. strip leading/trailing punctuation
5. keep alphanumeric tokens in their original order

Example:

- `Internal Linking Guide`
- ` internal   linking guide `
- `Internal Linking Guide!`

all normalize to:

- `internal linking guide`

Important:

- do not stem;
- do not synonym-expand;
- do not canonicalize through `FR-009` learned families.

Reason:

- v1 is an exact-match reuse guard, not a semantic anchor-family model.

## Math-Fidelity Note

### Definitions

Let:

- `d` = one destination
- `a` = normalized candidate anchor for that destination
- `H(d)` = normalized anchors from active suggestions for destination `d`
- `N` = count of non-empty normalized anchors in `H(d)`
- `C_exact(a, d)` = count of active anchors in `H(d)` exactly equal to `a`

Projected values if the new candidate is accepted:

```text
N' = N + 1
```

```text
C' = C_exact(a, d) + 1
```

```text
projected_exact_share = C' / max(N', 1)
```

### Neutral fallback

If:

- candidate anchor is blank after normalization, or
- `N < min_history_count`

then:

```text
score_anchor_diversity = 0.5
```

This keeps the feature neutral when there is not enough history to judge concentration.

### Soft concentration penalty

Settings:

- `max_exact_match_share`
- `max_exact_match_count`

Compute:

```text
share_overflow =
  max(0, projected_exact_share - max_exact_match_share)
  / max(1 - max_exact_match_share, 1e-9)
```

```text
count_overflow =
  max(0, C' - max_exact_match_count)
```

```text
count_overflow_norm =
  min(1.0, count_overflow / max(max_exact_match_count, 1))
```

```text
spam_risk =
  min(1.0, 0.8 * share_overflow + 0.2 * count_overflow_norm)
```

Then:

```text
score_anchor_diversity = 0.5 - 0.5 * spam_risk
```

Interpretation:

- `0.5` = neutral, no material repetition issue detected
- values below `0.5` = the anchor is over-concentrated and should be penalized
- `0.0` = strongest repetition risk

### Ranking hook

This feature is penalty-only in v1.

Compute:

```text
score_anchor_diversity_component =
  min(0.0, 2.0 * (score_anchor_diversity - 0.5))
```

This yields:

- `0.0` when neutral
- negative values down to `-1.0` when repetition risk is high

Then:

```text
score_final += anchor_diversity.ranking_weight * score_anchor_diversity_component
```

Default:

- `ranking_weight = 0.03`

This keeps the default penalty live without overpowering the main relevance signals.

### Optional hard cap

If:

- `hard_cap_enabled = true`
- and `C' > max_exact_match_count`

then the candidate may be hard-blocked with:

- pipeline diagnostic reason: `anchor_diversity_blocked`

Default:

- `hard_cap_enabled = false`

Reason:

- keep rollout low-regression by default;
- let operators validate diagnostics first.

## Stored Fields Required

### `Suggestion`

Add:

```python
score_anchor_diversity = models.FloatField(
    default=0.5,
    help_text="FR-045 anchor-diversity anti-spam score. 0.5 = neutral, lower values mean the anchor is too repetitive for the destination.",
)
```

```python
anchor_diversity_diagnostics = models.JSONField(
    default=dict,
    blank=True,
    help_text="Explainable FR-045 anchor-diversity details for review and debugging.",
)
```

### Reuse existing field

Keep:

- `Suggestion.repeated_anchor`

New meaning:

- `True` when the exact normalized anchor already exists in at least one active suggestion for the same destination.

Reason:

- preserves existing review UI behavior;
- upgrades it from an ad-hoc warning to a formalized signal input.

## Diagnostics Shape

Recommended JSON shape:

```json
{
  "anchor_diversity_state": "neutral_no_history",
  "normalized_anchor": "internal linking guide",
  "active_anchor_count": 4,
  "exact_match_count_before": 2,
  "projected_exact_match_count": 3,
  "projected_exact_share": 0.6,
  "max_exact_match_share": 0.4,
  "max_exact_match_count": 3,
  "share_overflow": 0.333333,
  "count_overflow_norm": 0.0,
  "spam_risk": 0.266667,
  "score_anchor_diversity": 0.366667,
  "hard_cap_enabled": false,
  "would_block": false,
  "active_statuses_considered": ["pending", "approved", "applied", "verified"],
  "algorithm_version": "fr045-v1"
}
```

Suggested states:

- `neutral_no_anchor`
- `neutral_no_history`
- `neutral_below_threshold`
- `penalized_exact_share`
- `penalized_exact_count`
- `blocked_exact_count`

## Pipeline Integration

### Load-time requirement

In `pipeline.py`, load active normalized-anchor counts by destination from `Suggestion` rows in active statuses.

Do not load rejected, stale, or superseded suggestions.

### Scoring-time placement

Placement must be:

1. `FR-008` phrase matching chooses the candidate anchor phrase
2. `FR-045` scores anchor repetition risk for that chosen anchor
3. `FR-013` explore/exploit may rerank the already-scored candidates
4. `FR-015` may later diversify destination selection

Reason:

- `FR-045` depends on the candidate anchor surface already existing;
- `FR-013` and `FR-015` operate at later reranking layers.

### Persistence-time requirement

Persist:

- `score_anchor_diversity`
- `anchor_diversity_diagnostics`
- upgraded `repeated_anchor`

### Pipeline snapshot requirement

Extend `PipelineRun.config_snapshot` to include:

- `anchor_diversity`
- `anchor_diversity.algorithm_version`

Reason:

- operators need to know which thresholds produced a run.

## Settings

Persist through `AppSetting`.

Keys:

- `anchor_diversity.enabled`
- `anchor_diversity.ranking_weight`
- `anchor_diversity.min_history_count`
- `anchor_diversity.max_exact_match_share`
- `anchor_diversity.max_exact_match_count`
- `anchor_diversity.hard_cap_enabled`
- `anchor_diversity.algorithm_version`

### Recommended defaults

- `enabled = true`
- `ranking_weight = 0.03`
- `min_history_count = 3`
- `max_exact_match_share = 0.40`
- `max_exact_match_count = 3`
- `hard_cap_enabled = false`
- `algorithm_version = "fr045-v1"`

### Bounds

- `0.0 <= ranking_weight <= 0.20`
- `1 <= min_history_count <= 10`
- `0.20 <= max_exact_match_share <= 0.90`
- `1 <= max_exact_match_count <= 10`

### Validation rules

- all numeric settings must be finite
- `max_exact_match_share` must be strictly less than `1.0`
- `max_exact_match_count` must be positive
- saving settings must not retroactively rewrite existing suggestions

## API, Admin, Review, and UI Impact

### Backend API

Add:

- `GET /api/settings/anchor-diversity/`
- `PUT /api/settings/anchor-diversity/`

No recalculation endpoint is required.

Reason:

- this feature is computed during pipeline execution from active suggestion history.

### Review UI

Add one review row:

- `Anchor Diversity`

Show:

- normalized anchor
- exact-match count already active for the destination
- projected share if accepted
- whether hard cap would block it

### Existing review warning

Keep the current repeated-anchor warning icon.

New rule:

- the icon is driven by the normalized exact-match history, not raw one-off string comparison.

### Admin

Expose:

- `score_anchor_diversity`
- `anchor_diversity_diagnostics`

## Ranking Performance Rule

This FR changes hot ranking behavior.

Per repo policy, the implementation phase must plan:

- a Python reference path in a new service such as `backend/apps/pipeline/services/anchor_diversity.py`
- a C++ fast path in `backend/extensions/` for batch calculation over candidate rows
- a `HAS_CPP_EXT`-style gate
- a correctness test that compares Python and C++ outputs on identical candidate batches
- a plain-English diagnostics flag that says whether the C++ path is active, disabled, missing, unsupported, or not helping enough

Important scope guard:

- the spec pass does not implement the C++ extension;
- it only reserves the architecture and correctness requirements.

## Fallback Behavior

- If the feature is disabled, keep `score_anchor_diversity = 0.5` and do not alter ranking.
- If a candidate anchor is blank, keep the feature neutral.
- If active suggestion history cannot be loaded, keep the feature neutral and expose `neutral_history_unavailable`.
- If the C++ speed path is unavailable, Python reference logic must still compute correct results.
- If `hard_cap_enabled = false`, no candidate is blocked by this FR.

## Regression Risks And Mitigations

### 1. Colliding with `FR-009` learned anchors

Mitigation:

- use only `Suggestion` history in v1;
- do not read `ExistingLink.anchor_text` for repetition counts.

### 2. Accidentally rewriting anchor generation

Mitigation:

- run only after `FR-008` has already chosen `anchor_phrase`;
- never mutate `anchor_phrase` inside `FR-045`.

### 3. Over-penalizing small-history destinations

Mitigation:

- neutral fallback until `min_history_count` is reached.

### 4. Surprising ranking regressions

Mitigation:

- `ranking_weight` defaults to `0.03`
- `hard_cap_enabled` defaults to `false`
- diagnostics still explain every penalty contribution

### 5. Duplicate logic with existing `repeated_anchor`

Mitigation:

- keep the field;
- formalize it as an output of the anchor-diversity service instead of a separate side check.

## Exact Repo Files Likely To Be Touched In The Implementation Phase

- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/services/pipeline.py`
- `backend/apps/pipeline/services/anchor_diversity.py`
- `backend/extensions/<new anchor diversity batch scorer>.cpp`
- `backend/apps/suggestions/models.py`
- `backend/apps/suggestions/serializers.py`
- `backend/apps/suggestions/views.py`
- `backend/apps/suggestions/admin.py`
- `backend/apps/core/views.py`
- `backend/apps/api/urls.py`
- `frontend/src/app/review/suggestion.service.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

## Test Plan

### 1. Neutral on no history

- destination has no active suggestions
- candidate anchor is non-empty
- assert `score_anchor_diversity == 0.5`
- assert `repeated_anchor == false`

### 2. Repeated-anchor warning with exact normalized match

- active suggestion anchor: `Internal Linking Guide`
- candidate anchor: ` internal   linking guide `
- assert normalized exact match is detected
- assert `repeated_anchor == true`

### 3. No collision with punctuation-only formatting

- active anchor: `Internal Linking Guide!`
- candidate anchor: `Internal Linking Guide`
- assert they normalize to the same key

### 4. Soft penalty when share threshold is exceeded

- destination has 4 active suggestions
- 2 already use the candidate anchor
- candidate would raise projected exact share above `max_exact_match_share`
- assert score drops below `0.5`
- assert diagnostics report `penalized_exact_share`

### 5. Count overflow penalty

- destination already has `max_exact_match_count` active exact matches
- candidate uses the same anchor
- assert `count_overflow_norm > 0`

### 6. Optional hard block

- enable `hard_cap_enabled`
- destination already has `max_exact_match_count` exact matches
- candidate uses same anchor
- assert candidate is skipped with `anchor_diversity_blocked`

### 7. Disabled parity

- `enabled = false`
- assert ranking order matches pre-FR-045 behavior
- assert stored score is neutral and no block occurs

### 8. Snapshot correctness

- start a pipeline run
- assert `PipelineRun.config_snapshot["anchor_diversity"]` is populated

### 9. C++ parity

- run the same candidate batch through Python and C++ implementations
- assert score, warning flag, and block decision match exactly

### 10. Review serializer exposure

- assert detail response includes:
  - `score_anchor_diversity`
  - `anchor_diversity_diagnostics`
  - updated `repeated_anchor`

## Final Chosen Behavior

Simple version first.

This FR does one thing:

- stop one exact anchor phrase from taking over the suggestion history of a destination.

Exact outcome:

- `FR-008` still picks the anchor.
- `FR-009` still checks whether the anchor looks like trusted live vocabulary.
- `FR-045` adds a new anti-spam check that penalizes or optionally blocks repeated exact-match anchor reuse for the same destination.
- it uses active suggestion history only, not live-link corpus, telemetry, or destination embeddings.
