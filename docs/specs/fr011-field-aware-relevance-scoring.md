# FR-011 - Field-Aware Relevance Scoring

## Confirmation

Simple version first.

- Active target confirmed: `Phase 14 / FR-011 - Field-Aware Relevance Scoring` is the next real target in `AI-CONTEXT.md` and `FEATURE-REQUESTS.md`.
- Spec-first confirmed: this session is creating the FR-011 spec only. It is not the implementation session.
- Repo confirmed: the live pipeline already has separate FR-006 weighted authority, FR-007 link freshness, FR-008 phrase relevance, FR-009 learned-anchor corroboration, and FR-010 rare-term propagation layers.
- Repo confirmed: there is no current FR-011 field-aware score, diagnostics object, settings API, or algorithm-version entry in the codebase today.

## Current Repo Map

### Current ranking inputs already in the live pipeline

- `backend/apps/pipeline/services/ranker.py`
  - already scores:
    - semantic similarity
    - keyword Jaccard overlap
    - node affinity
    - host quality
    - optional FR-006 weighted authority
    - optional FR-007 link freshness
    - optional FR-008 phrase relevance
    - optional FR-009 learned-anchor corroboration
    - optional FR-010 rare-term propagation
- `backend/apps/pipeline/services/pipeline.py`
  - already loads `ContentRecord` for each destination/host pair;
  - already loads inbound anchor rows for FR-009;
  - already snapshots per-feature settings and algorithm versions into `PipelineRun.config_snapshot`.

### Destination fields already available in repo data

- `backend/apps/content/models.py`
  - `ContentItem.title`
  - `ContentItem.distilled_text`
  - `ContentItem.scope`
- `backend/apps/content/models.py`
  - `ScopeItem.title`
  - `ScopeItem.parent`
- `backend/apps/pipeline/services/pipeline.py`
  - current `ContentRecord` already includes:
    - `title`
    - `distilled_text`
    - `scope_id`
    - `scope_type`
    - `parent_id`
    - `parent_type`
    - `grandparent_id`
    - `grandparent_type`
    - `silo_group_id`
    - `silo_group_name`
    - combined destination `tokens`
  - but it does **not** yet include scope-title text fields or field-specific token sets.

### Existing learned-anchor source already available

- `backend/apps/graph/models.py`
  - `ExistingLink.anchor_text`
- `backend/apps/pipeline/services/learned_anchor.py`
  - already builds destination-specific learned-anchor families and diagnostics;
  - already has support thresholds and noise filtering;
  - already keeps learned-anchor evidence separate from FR-008 phrase evidence.

### Existing storage and UI patterns already available

- `backend/apps/suggestions/models.py`
  - already stores separate suggestion-level score fields and JSON diagnostics for newer ranking layers.
- `backend/apps/suggestions/views.py`
  - already stores `weighted_authority`, `phrase_matching`, `learned_anchor`, and `rare_term_propagation` settings in `PipelineRun.config_snapshot`.
- `backend/apps/core/views.py`
  - already exposes per-feature settings APIs and validation helpers.
- `frontend/src/app/review/suggestion.service.ts`
  - already models separate FR-008, FR-009, and FR-010 score and diagnostics blocks.
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
  - already shows separate rows and detail blocks for those newer ranking layers.

## Problem Summary

Simple version first.

Right now the app mostly treats destination text as one lump:

- title plus distilled body tokens for keyword overlap;
- separate phrase logic for FR-008;
- separate learned-anchor logic for FR-009.

That misses an important idea:

- a host sentence can match the **title** strongly,
- or match the **body** strongly,
- or match the **scope labels** strongly,
- or match the **learned anchor vocabulary** strongly,
- and those should not all mean the same thing.

FR-011 fixes that by scoring those fields separately, then combining them in a small, bounded, explainable way.

## Goal

Add a separate FR-011 suggestion-level score that:

- scores destination `title`, `body`, `scope labels`, and `learned anchor vocabulary` as separate fields;
- uses field-specific term frequencies and field lengths in a patent-faithful but repo-safe way;
- keeps missing field evidence neutral at `0.5`;
- keeps ranking impact additive, bounded, and off by default;
- exposes field-by-field diagnostics to review and admin;
- stays separate from FR-008 phrase scoring, FR-009 anchor corroboration, and FR-010 propagated rare terms.

## Non-Goals

FR-011 does not:

- replace semantic similarity;
- replace FR-008 phrase matching;
- replace FR-009 learned-anchor corroboration;
- rewrite `ContentItem.title` or `ContentItem.distilled_text`;
- append propagated terms from FR-010 into destination fields;
- use silo-group names as FR-011 scope labels in v1;
- redesign FR-006, FR-007, or velocity;
- implement production code in this session.

## Source Summary

Primary source actually read:

- [US20050210006A1 / US7584221B2 - Field weighting in text searching](https://patents.google.com/patent/US20050210006A1/en)

Useful source ideas:

- documents can be searched as multiple fields rather than one big text blob;
- field-specific term frequencies matter;
- field lengths matter;
- field scores can be combined into one overall score;
- some fields may deserve higher weight than others;
- a field weight of zero can ignore a field completely.

Important source-guided takeaway for this repo:

- a field-aware score should not just be a naive weighted sum of independent field hits;
- it should account for:
  - how often host terms appear in each field;
  - how long that field is;
  - how much that field should matter relative to other fields.

## Math-Fidelity Note

### Directly supported by the patent

- treat a document as multiple fields;
- compute field-weighted term frequencies;
- account for field lengths;
- combine field-aware term evidence into an overall score.

### Adapted for this repo

- Inference: the chosen host sentence plays the role of the short query-like text.
- Inference: the destination page plays the role of the multi-field document.
- Inference: token-level matching is the safest FR-011 v1 unit because:
  - FR-008 already owns phrase scoring;
  - FR-010 already owns propagated rare terms;
  - token-level field scoring stays cleanly separate.
- Inference: a small BM25F-style formula is the safest repo fit:
  - it uses field term frequency and field length;
  - it stays deterministic and bounded;
  - it works with the current additive ranker.

### Deliberately not carried over in FR-011 v1

- no full text-search engine rewrite;
- no virtual document index;
- no phrase scoring inside FR-011;
- no learned ranking model;
- no telemetry-driven field weights;
- no use of FR-010 propagated terms inside FR-011 fields.

## Scope Boundary Versus FR-008, FR-009, and FR-010

FR-011 must stay separate from:

- `FR-008`
  - FR-008 owns phrase inventory and anchor expansion from title + distilled text.
  - FR-011 uses token-level field evidence only.
- `FR-009`
  - FR-009 owns whether the chosen anchor is corroborated by learned anchor families.
  - FR-011 may use the learned vocabulary as one destination field, but it must not reuse FR-009 match states as FR-011 evidence.
- `FR-010`
  - FR-010 owns related-page propagated rare terms.
  - FR-011 field profiles must use only original destination fields plus learned-anchor vocabulary.
  - propagated rare terms must not be appended into title, body, scope, or learned-anchor fields.

Hard rule:

- FR-011 v1 is a separate token-level field score only.

## Fields Included In FR-011 v1

Simple version first.

FR-011 v1 scores exactly four destination-side fields:

1. `title`
2. `body`
3. `scope_labels`
4. `learned_anchor_vocabulary`

### Title field

- source: `ContentItem.title`
- tokenization: existing normalized token rules
- meaning: short, high-signal summary of the destination

### Body field

- source: `ContentItem.distilled_text`
- tokenization: existing normalized token rules
- meaning: broader topical text for the destination

### Scope labels field

- source text only:
  - `scope.title`
  - `parent.title`
  - `grandparent.title`
- excluded in v1:
  - `silo_group.name`
  - `scope_type` display labels
  - source labels like `XenForo` / `WordPress`
- meaning: structural topic labels around the destination

### Learned-anchor vocabulary field

- source: FR-009-style learned anchor families for the destination
- include:
  - canonical anchor text
  - alternate variants for accepted families
- include only when:
  - destination has at least `minimum_anchor_sources`;
  - family support share is at least `minimum_family_support_share`
- meaning: wording already used on the site for this destination

## Inputs Required

FR-011 v1 uses only data the repo already has or already derives:

- host sentence text
- destination title
- destination distilled text
- destination scope title hierarchy
- inbound anchor text for learned-anchor vocabulary

Explicitly disallowed FR-011 inputs in v1:

- FR-006 edge-prominence fields
- FR-007 link-history timing
- FR-010 propagated rare terms
- velocity metrics
- reviewer-edited anchors
- telemetry or search analytics

## Field Profile Construction

### Tokenization rule

Use the repo's existing normalized token rules from `text_tokens.py`.

That means:

- lowercase;
- same token regex;
- same stopword removal;
- no field-specific custom tokenizer in v1.

### Stored field profile per destination

Build one in-memory FR-011 profile per destination during a pipeline run.

Recommended structure:

- `title_tokens: Counter[str]`
- `body_tokens: Counter[str]`
- `scope_label_tokens: Counter[str]`
- `learned_anchor_tokens: Counter[str]`
- `title_length`
- `body_length`
- `scope_label_length`
- `learned_anchor_length`

### Learned-anchor field construction

Build this field from accepted learned families only:

- canonical anchor text once;
- each alternate variant once;
- tokenize them into a `Counter`.

This keeps FR-011 separate from FR-009 because:

- FR-011 uses the vocabulary itself as a destination field;
- FR-009 still separately checks whether the chosen anchor matches that vocabulary.

### Field absence rules

If a field has no usable tokens:

- its field score is treated as absent, not negative;
- it contributes nothing to the combined FR-011 score;
- diagnostics must still show that the field was empty.

## Proposed Scoring Logic

Simple version first.

For each field:

1. look at which host-sentence tokens also appear in that field;
2. reward stronger matches;
3. lightly discount longer fields;
4. combine the field scores with operator-controlled field weights.

### Field-local term score

For one field `f` and one matched host token `t`:

- `tf_f(t)` = term frequency of token `t` in field `f`
- `len_f` = token count of field `f`
- `avg_len_f` = average token count of that field across all destinations in the run
- `df_f(t)` = number of destination field profiles in field `f` that contain token `t`
- `N_f` = number of destination profiles with a non-empty field `f`

Use a BM25F-style per-field term score:

```text
idf_f(t) = log(1 + ((N_f + 1) / (df_f(t) + 0.5)))

length_norm_f =
  (1 - b_f) + b_f * (len_f / max(avg_len_f, 1))

term_score_f(t) =
  idf_f(t) * (
    tf_f(t) / (tf_f(t) + k1 * length_norm_f)
  )
```

Recommended fixed constants for v1:

- `k1 = 1.2`
- `b_title = 0.20`
- `b_body = 0.75`
- `b_scope = 0.35`
- `b_learned_anchor = 0.40`

These stay as code constants in v1, not UI settings.

### Field raw score

For each field:

- collect unique matched host tokens in that field;
- order them by highest `term_score_f(t)`;
- keep at most the top `5` unique matched tokens;
- sum them:

```text
field_raw_f = sum(term_score_f(t) for top matched tokens)
```

### Field normalized score

Convert each field to a bounded `[0, 1)` score:

```text
field_score_f = field_raw_f / (1.0 + field_raw_f)
```

If the field is empty or has no matched tokens:

```text
field_score_f = null
```

This means "no field evidence," not "bad evidence."

### Field weights

Persist operator-facing field weights:

- `title_field_weight`
- `body_field_weight`
- `scope_field_weight`
- `learned_anchor_field_weight`

Default weights:

- `title_field_weight = 0.40`
- `body_field_weight = 0.30`
- `scope_field_weight = 0.15`
- `learned_anchor_field_weight = 0.15`

### Combined FR-011 score

Only include fields that both:

- have non-empty field profiles;
- have at least one matched host token.

Let `active_fields` be those fields.

If `active_fields` is empty:

```text
score_field_aware_relevance = 0.5
```

Otherwise:

```text
active_weight_sum =
  sum(field_weight_f for f in active_fields)

combined_field_score =
  sum(
    (field_weight_f / active_weight_sum) * field_score_f
    for f in active_fields
  )

score_field_aware_relevance =
  0.5 + 0.5 * combined_field_score
```

So in v1:

- stored score range is `[0.5, 1.0)`;
- `0.5` is neutral;
- missing field evidence is neutral, not negative.

### Additive ranking hook

Centered component:

```text
score_field_aware_component =
  max(0.0, min(1.0, 2.0 * (score_field_aware_relevance - 0.5)))
```

Exact ranking hook:

```text
score_final += field_aware_relevance.ranking_weight * score_field_aware_component
```

Default safety rule:

- with `ranking_weight = 0.0`, FR-011 does not change ranking order.

## Why This Fits The Repo

This design matches the repo's current pattern because:

- it creates one separate suggestion-level score;
- it creates one separate diagnostics object;
- it uses additive bounded ranking like FR-008, FR-009, and FR-010;
- it snapshots settings and algorithm version per run;
- it stays off by default.

## Settings And Defaults

Persist through `AppSetting`.

Recommended keys:

- `field_aware_relevance.ranking_weight`
- `field_aware_relevance.title_field_weight`
- `field_aware_relevance.body_field_weight`
- `field_aware_relevance.scope_field_weight`
- `field_aware_relevance.learned_anchor_field_weight`

Defaults:

- `ranking_weight = 0.0`
- `title_field_weight = 0.40`
- `body_field_weight = 0.30`
- `scope_field_weight = 0.15`
- `learned_anchor_field_weight = 0.15`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- each field weight must be finite and `>= 0.0`
- at least one field weight must be `> 0.0`
- recommended soft guardrail:
  - `title_field_weight + body_field_weight + scope_field_weight + learned_anchor_field_weight > 0`

Not operator-facing in v1:

- `k1`
- `b_title`
- `b_body`
- `b_scope`
- `b_learned_anchor`
- top matched token cap per field

## Diagnostics And Explainability

Add one new diagnostics object:

- `Suggestion.field_aware_diagnostics`

Required fields:

- `score_field_aware_relevance`
- `field_aware_state`
  - `computed_match`
  - `neutral_no_field_terms`
  - `neutral_no_host_match`
  - `neutral_processing_error`
- `active_fields`
- `host_tokens_considered`
- `field_weights`
- `matched_fields`

`matched_fields` should be an object with one entry per field:

- `title`
- `body`
- `scope_labels`
- `learned_anchor_vocabulary`

Each field entry should include:

- `field_present`
- `field_length`
- `matched_token_count`
- `matched_tokens`
- `field_raw_score`
- `field_score`
- `configured_field_weight`
- `normalized_field_weight`

Plain-English review helper text:

- `Field-aware relevance means the host sentence matched some destination fields better than others.`
- `Title matches are usually sharper. Body matches are broader. Scope labels are structural hints. Learned anchors are wording already used on the site.`
- `Neutral means the sentence did not give useful field-level evidence.`

## Storage Impact

### Suggestion model

Add:

- `Suggestion.score_field_aware_relevance: FloatField(default=0.5)`
- `Suggestion.field_aware_diagnostics: JSONField(default=dict, blank=True)`

### Content model

No new `ContentItem` field is needed in v1.

Reason:

- FR-011 is candidate-specific;
- one host sentence may match one field strongly while another does not;
- this is not a stable content-wide score.

### Pipeline snapshot

Add to `PipelineRun.config_snapshot`:

- `field_aware_relevance` settings
- `field_aware_relevance` algorithm version metadata

### Algorithm version

Add a new version entry in `backend/apps/pipeline/services/algorithm_versions.py` following the existing helper pattern:

- `FIELD_AWARE_RELEVANCE_VERSION`

Use the implementation-date stamp when the code pass lands.

## API / Admin / Review / Settings Impact

### Backend API

Add:

- `GET /api/settings/field-aware-relevance/`
- `PUT /api/settings/field-aware-relevance/`

No recalculation endpoint in v1.

Reason:

- FR-011 is suggestion-time scoring, not a destination-wide persisted metric.

### Suggestion detail API

Extend output with:

- `score_field_aware_relevance`
- `field_aware_diagnostics`

### Admin

Expose in `SuggestionAdmin`:

- `score_field_aware_relevance`
- `field_aware_diagnostics` read-only

### Review UI

Add one new detail row:

- `Field-Aware Relevance`

Add one small diagnostics block:

- field-aware state
- active fields
- top matched tokens per field
- normalized field contribution per field

### Settings UI

Add one small settings card:

- ranking weight
- title field weight
- body field weight
- scope field weight
- learned-anchor field weight

## Exact Repo Modules Likely To Be Touched In The Later Implementation Session

### Pipeline and scoring

- `backend/apps/pipeline/services/pipeline.py`
- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/services/learned_anchor.py`
- `backend/apps/pipeline/services/text_tokens.py`
- `backend/apps/pipeline/services/<new field aware service>`

### Suggestion storage and surfacing

- `backend/apps/suggestions/models.py`
- `backend/apps/suggestions/serializers.py`
- `backend/apps/suggestions/views.py`
- `backend/apps/suggestions/admin.py`
- `backend/apps/suggestions/migrations/<new migration>`

### Settings and API

- `backend/apps/core/views.py`
- `backend/apps/api/urls.py`
- `backend/apps/pipeline/services/algorithm_versions.py`

### Frontend review and settings

- `frontend/src/app/review/suggestion.service.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

### Repo-shape change needed for `ContentRecord`

The implementation pass should extend `ContentRecord` and loader output with:

- `scope_title`
- `parent_scope_title`
- `grandparent_scope_title`

This is needed because FR-011 must score scope labels by text, not just by IDs.

## Test Plan

### 1. Title field match

- host sentence matches title tokens strongly;
- body/scope/learned fields weak or absent;
- assert title field dominates diagnostics;
- assert `score_field_aware_relevance > 0.5`.

### 2. Body field match

- host sentence matches distilled body tokens but not title;
- assert body field contributes while title does not.

### 3. Scope-label field match

- host sentence matches scope title or parent scope title;
- assert scope field contributes;
- assert silo-group name is **not** used as scope-label evidence in v1.

### 4. Learned-anchor field match

- destination has accepted learned anchor families;
- host sentence overlaps those learned anchor tokens;
- assert learned-anchor field contributes even when title/body do not.

### 5. Neutral fallback

- no field has matched host tokens;
- assert stored score is `0.5`;
- assert diagnostics show `neutral_no_host_match`.

### 6. Empty-field behavior

- destination missing body text or learned-anchor data;
- assert missing field is absent, not negative;
- assert other fields still work.

### 7. Length normalization sanity

- two destinations match the same host token equally;
- one field is much longer than the other;
- assert the shorter field gets a slightly stronger field score.

### 8. Off-by-default ranking

- with `ranking_weight = 0.0`, ranking order stays unchanged.

### 9. Boundary checks

- changing FR-008 settings does not change FR-011 field profile construction except via the learned-anchor thresholds already owned by FR-009;
- changing FR-010 propagated rare terms does not change FR-011 field text;
- changing FR-006 or FR-007 settings does not change FR-011 field text.

### 10. Snapshot coverage

- `PipelineRun.config_snapshot` stores FR-011 settings and algorithm version.

### 11. Serializer and UI contract

- suggestion detail exposes:
  - `score_field_aware_relevance`
  - `field_aware_diagnostics`
- Angular review detail renders:
  - the `Field-Aware Relevance` row
  - the diagnostics summary block.

## Risks And Sanity Notes

### Risks

- scope labels can be too broad if common node titles are noisy;
- learned-anchor vocabulary can overlap title/body language and make field contributions look redundant;
- if field weights are too aggressive, FR-011 can over-favor metadata-like fields over real sentence meaning.

### Sanity safeguards

- keep ranking weight at `0.0` by default;
- keep scope weight and learned-anchor weight smaller than title by default;
- keep FR-011 token-level only so it does not steal FR-008's phrase role;
- never pull FR-010 propagated terms into FR-011 fields.

## Implementation Decision

Path chosen:

- use one separate suggestion-level FR-011 score;
- score four destination-side fields separately;
- use a small BM25F-style token-and-length-aware formula per field;
- combine only matched fields with bounded operator-facing field weights;
- keep missing evidence neutral;
- keep ranking impact off by default;
- keep FR-008, FR-009, and FR-010 separate.
