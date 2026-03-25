# FR-009 - Learned Anchor Vocabulary & Corroboration

## Confirmation

Simple version first.

- Active target confirmed: `Phase 12 / FR-009 - Learned Anchor Vocabulary & Corroboration` is the current target in `AI-CONTEXT.md` and `FEATURE-REQUESTS.md`.
- Spec-first confirmed: this session is creating the missing FR-009 spec only. It is not the implementation session.
- Repo confirmed: `docs/specs/fr009-learned-anchor-vocabulary-corroboration.md` was missing before this spec pass.
- Repo confirmed: current FR-008 phrase logic already exists in `backend/apps/pipeline/services/phrase_matching.py` and is wired through `backend/apps/pipeline/services/ranker.py` and `backend/apps/pipeline/services/pipeline.py`.
- Repo confirmed: current exact anchor extraction already exists in `backend/apps/pipeline/services/anchor_extractor.py`.
- Repo confirmed: existing live anchor text already exists in `backend/apps/graph/models.py` on `ExistingLink.anchor_text`.
- Repo confirmed: review/detail/admin/settings already expose FR-008 phrase behavior, FR-006 weighted authority, and FR-007 link freshness, but there is no separate FR-009 learned-anchor score, diagnostics block, settings surface, or spec file yet.

## Current Repo Map

### Current learned-anchor evidence source

- `backend/apps/graph/models.py`
  - `ExistingLink.anchor_text` stores live anchor text already found on the site.
  - `ExistingLink` also stores `from_content_item`, `to_content_item`, and extraction metadata.
  - This is the only existing repo storage that can support learned-anchor vocabulary in a first pass.

### Current anchor and phrase path

- `backend/apps/pipeline/services/anchor_extractor.py`
  - exact title-based fallback anchor extraction only.
- `backend/apps/pipeline/services/phrase_matching.py`
  - FR-008 phrase inventory from destination title + distilled text.
  - exact and bounded partial phrase matching.
  - local sentence corroboration only.
- `backend/apps/pipeline/services/ranker.py`
  - computes `score_phrase_relevance` through FR-008.
  - currently has no FR-009 learned-anchor component.
- `backend/apps/pipeline/services/pipeline.py`
  - persists anchor fields and FR-008 phrase diagnostics to `Suggestion`.

### Current suggestion/review/settings/admin surfaces

- `backend/apps/suggestions/models.py`
  - stores `anchor_phrase`, `anchor_confidence`, `score_phrase_relevance`, and `phrase_match_diagnostics`.
  - stores no FR-009 learned-anchor score or diagnostics field today.
- `backend/apps/suggestions/serializers.py`
  - detail view exposes FR-008 phrase data and FR-007 freshness data.
  - no FR-009 vocabulary or corroboration data yet.
- `backend/apps/suggestions/views.py`
  - pipeline-run snapshot currently stores FR-006 and FR-008 config.
  - no FR-009 config snapshot yet.
- `backend/apps/suggestions/admin.py`
  - admin exposes current anchor phrase and FR-008 phrase diagnostics.
  - no FR-009 section yet.
- `backend/apps/core/views.py`
  - settings APIs exist for weighted authority, link freshness, and phrase matching.
  - no learned-anchor settings API yet.
- `backend/apps/api/urls.py`
  - no FR-009 settings route yet.
- `frontend/src/app/review/suggestion.service.ts`
  - review detail type includes FR-008 phrase diagnostics and FR-007 freshness diagnostics.
  - no FR-009 learned-anchor type yet.
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
  - plain-English summary helpers exist for phrase and freshness.
  - no learned-anchor summary helper yet.
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
  - review detail already shows anchor text, phrase relevance, and phrase diagnostics.
  - no learned-anchor vocabulary block yet.
- `frontend/src/app/settings/silo-settings.service.ts`
  - settings service already loads phrase matching, link freshness, and weighted authority settings.
  - no FR-009 settings calls yet.
- `frontend/src/app/settings/settings.component.ts`
  - settings page already loads FR-006, FR-007, and FR-008 cards.
  - no FR-009 state yet.
- `frontend/src/app/settings/settings.component.html`
  - no learned-anchor settings card yet.

## Problem Summary

Simple version first.

The app can already find a phrase in the chosen host sentence.
It still does not learn from anchor wording that real editors already used on the live site.

That leaves a gap:

- FR-008 can find a good phrase from destination text and local sentence text.
- But the app does not yet know whether that phrase looks like the anchor wording people already use for that destination.
- It also cannot show the reviewer a learned list of common anchor variants for the destination.

So today the app is missing two useful things:

1. a learned anchor vocabulary built from real existing internal links;
2. a separate corroboration signal that says whether the chosen anchor matches that learned vocabulary.

## Goal

Add a small, explainable, bounded FR-009 layer that:

- learns a destination-specific anchor vocabulary from existing inbound `ExistingLink.anchor_text` rows;
- keeps that learned vocabulary separate from FR-008 phrase evidence;
- computes a separate suggestion-level corroboration score for the chosen anchor;
- stays neutral when learned-anchor evidence is missing or too thin;
- keeps ranking impact additive, bounded, and off by default;
- shows canonical and alternate learned anchor variants in review/admin;
- does not redesign FR-008, FR-006, FR-007, or velocity logic.

## Non-Goals

FR-009 does not:

- replace FR-008 phrase matching;
- replace the current exact fallback extractor;
- redesign FR-006 weighted authority;
- redesign FR-007 freshness;
- use `velocity_score` or content activity as learned-anchor evidence;
- add FR-011 field-aware scoring;
- add telemetry, alerting, or auto-tuning;
- add a destination-level learned-anchor table in the first implementation pass;
- add reviewer preference/disallow persistence in the first implementation pass;
- implement production code in this session.

## Source Summary From The FR-009 Patent / Source Material

Source actually read:

- [US9208229B2 - Anchor text summarization for corroboration](https://patents.google.com/patent/US9208229B2/en)

Important source ideas:

- A set of anchor texts pointing to the same document can be treated as a candidate set.
- Repeated anchor texts matter more than rare outliers.
- Similar anchor texts can be grouped and summarized.
- A representative anchor can be selected from the candidate set using similarity plus frequency.
- Noise anchors such as generic text can be filtered out before corroboration.
- Anchor text can help decide whether a referenced document is relevant enough to use as corroborating evidence.
- The patent also mentions that anchor candidates may be weighted by source quality such as PageRank.

Repo-safe reading of the source:

- For this repo, the main reusable idea is not fact extraction.
- The reusable part is anchor-set summarization and using that summary as corroborating evidence.

## Math-Fidelity Note

### Directly supported by the patent

- aggregate anchor texts that point to the same target;
- count repeated anchors;
- reduce the influence of outliers;
- filter noise anchors;
- select a representative anchor from a group of related anchors;
- use anchor evidence as corroboration, not as the only signal.

### Adapted for this repo

- Inference: a destination `ContentItem` is the local stand-in for the patent's referenced document.
- Inference: inbound `ExistingLink.anchor_text` rows are the local stand-in for the patent's candidate anchor set.
- Inference: a simple token-based family grouping is a safe local stand-in for the patent's broader n-gram clustering step.
- Inference: the FR-008-selected anchor phrase is the candidate anchor that FR-009 should corroborate in v1.
- Inference: because the current ranker is additive and bounded, FR-009 should use a separate suggestion-level score with a dedicated ranking weight that defaults to `0.0`.

### Deliberately not carried over in FR-009 v1

- no web-scale clustering;
- no fact repository logic;
- no source-quality weighting by FR-006 PageRank in the first pass;
- no auto-rewrite of anchor text based only on learned vocabulary;
- no reviewer feedback loop or preference learning in the first pass.

## Scope Boundary Versus FR-008, FR-006, FR-007, Velocity, and Later Phases

FR-009 must stay separate from:

- `FR-008`
  - FR-008 finds phrase evidence inside the chosen host sentence using destination title + distilled text.
  - FR-009 uses existing live anchor text from `ExistingLink.anchor_text`.
  - FR-008 local corroboration is same-sentence evidence only.
  - FR-009 corroboration is learned-anchor evidence from historical links only.
- `FR-006`
  - do not use weighted-edge factors or March 2026 PageRank as learned-anchor inputs in v1.
  - do not let learned-anchor clustering depend on authority math.
- `FR-007`
  - do not use link-history timestamps, freshness buckets, or disappearance data as anchor evidence.
- `velocity`
  - do not use views, replies, downloads, or recency metrics as anchor evidence.
- later phases
  - no FR-011 field-aware scoring;
  - no FR-012 click-distance prior;
  - no FR-013 to FR-015 reranking or diversity work;
  - no FR-016 to FR-020 telemetry, alerts, model tuning, or runtime changes.

Hard rule:

- FR-009 v1 only learns from existing inbound anchor text and only corroborates the chosen suggestion anchor.

## Inputs Required

FR-009 v1 needs only data that already exists:

- `Suggestion.anchor_phrase` or the candidate anchor chosen during scoring;
- destination `content_id` / `content_type`;
- inbound `ExistingLink` rows for that destination;
- `ExistingLink.anchor_text`;
- `ExistingLink.from_content_item` so one source page can count once per normalized anchor;
- current tokenization style from `TOKEN_RE` and `STANDARD_ENGLISH_STOPWORDS`.

Allowed learned-anchor inputs in v1:

- live inbound anchor text from `ExistingLink.anchor_text`;
- source-page identity for per-source dedupe;
- destination identity.

Explicitly disallowed learned-anchor inputs in v1:

- destination title or distilled text as learned vocabulary evidence;
- FR-006 edge weights or authority scores;
- FR-007 freshness data;
- velocity metrics;
- reviewer-edited anchors;
- external analytics.

## Neutral Fallback Behavior When Learned-Anchor Evidence Is Missing

Missing or thin learned-anchor evidence must be neutral, not negative.

Use a stored neutral score of `0.5` when any of these are true:

- the destination has no inbound `ExistingLink` rows with usable `anchor_text`;
- all available anchor text normalizes to noise or empties out;
- usable anchor evidence exists from fewer than `minimum_anchor_sources`;
- the suggestion has no candidate anchor phrase to corroborate;
- the candidate anchor does not match any learned family strongly enough;
- learned-anchor processing fails.

Neutral behavior rules:

- `score_learned_anchor_corroboration = 0.5` means "no useful learned-anchor evidence."
- ranking contribution from a neutral score must be `0.0`.
- FR-009 v1 does not push a suggestion below neutral.
- FR-009 v1 does not remove or rewrite the FR-008-selected anchor just because learned evidence is thin.

## Proposed Learned-Anchor Vocabulary Logic

### Step 1 - collect raw anchor candidates per destination

For one destination:

- gather inbound `ExistingLink` rows where `to_content_item == destination`;
- discard blank `anchor_text`;
- tokenize and normalize with the same lowercasing and token pattern used by FR-008;
- keep the original surface text too.

### Step 2 - discard obvious noise

Discard an anchor candidate when:

- normalization produces zero usable tokens;
- all remaining tokens are stopwords;
- the normalized surface is in a known-noise list.

Initial known-noise list for v1:

- `click here`
- `here`
- `read more`
- `this link`
- `link`
- `source`
- `website`
- `visit site`

Rule:

- the noise list is code-defined in the first implementation pass, not operator-editable.

### Step 3 - dedupe per source page

To stop one source page from over-voting:

- count at most one vote per `from_content_item` for each normalized anchor variant.

This means:

- repeated copies of the same anchor text from the same source page do not inflate support;
- different source pages can still vote for the same variant.

### Step 4 - build exact variants

Each exact variant stores:

- normalized token tuple;
- display surface text;
- unique supporting source count;
- support share across all usable inbound anchor sources.

### Step 5 - build anchor families

Group exact variants into one family when one of these is true:

1. normalized token tuple is exactly equal;
2. contiguous overlap is at least `2` tokens and covers at least `60%` of the shorter side;
3. token sequence differs only by a one-token prefix or suffix extension;
4. normalized strings differ only by a small typo with edit distance `1` when token count is `1` or `2`.

This keeps families simple and deterministic.

### Step 6 - choose the canonical variant

For each family, pick one canonical display form using these tie-breakers:

1. higher supporting source count;
2. higher support share;
3. longer token count;
4. exact surface text that appears most often;
5. alphabetical surface tie-break.

### Step 7 - cap the vocabulary

Keep the vocabulary small.

Recommended bounds:

- maximum `8` learned families per destination;
- maximum `5` alternate variants shown per family.

Family ordering:

1. higher support share;
2. higher supporting source count;
3. longer canonical token count;
4. canonical display text alphabetical.

## Proposed Corroboration Logic

Simple version first.

FR-009 does not discover the anchor from scratch.
FR-009 checks whether the already chosen anchor looks like something the site already uses for that destination.

### Candidate anchor to corroborate

The v1 candidate anchor is:

- the FR-008-selected `anchor_phrase` during pipeline scoring; or
- the current fallback extractor result if FR-008 returned fallback behavior.

### Corroboration states

- `exact_variant_match`
  - candidate anchor exactly matches a learned exact variant.
- `family_match`
  - candidate anchor is not an exact variant, but it matches a learned family by the same overlap rule used during family building.
- `host_contains_canonical_variant`
  - the candidate anchor does not match, but the host sentence still contains the learned canonical variant exactly.
  - v1 records this as explainability only. It does not auto-swap anchors.
- `neutral_no_anchor_candidate`
- `neutral_no_learned_anchor_data`
- `neutral_below_min_sources`
- `neutral_no_family_match`
- `neutral_processing_error`

### Corroboration acceptance rules

Accept learned corroboration when:

- the destination has at least `minimum_anchor_sources` usable inbound anchor sources; and
- the matched family has support share at or above `minimum_family_support_share`.

Recommended defaults:

- `minimum_anchor_sources = 2`
- `minimum_family_support_share = 0.15`

### Exact vs family corroboration meaning

- exact variant match means the chosen anchor is already a learned variant;
- family match means the chosen anchor is close to a learned family, but not the strongest exact variant;
- host-contains-canonical means the sentence includes a stronger learned anchor alternative, but v1 only reports it.

## Proposed Scoring Or Weighting Logic

### New score name

Add one new suggestion-level score:

- `Suggestion.score_learned_anchor_corroboration`

This is separate from:

- `Suggestion.score_phrase_relevance`
- `Suggestion.score_march_2026_pagerank`
- `Suggestion.score_link_freshness`

### Component definitions

For the matched family:

- `match_strength`
  - `1.0` for exact variant match
  - `0.65` for family match
  - `0.0` otherwise
- `family_support_strength`
  - learned family support share, clamped to `[0.0, 1.0]`
- `variant_share_strength`
  - exact variant support share if exact match, else `0.0`
- `source_count_strength`
  - `min(1.0, supporting_source_count / 5.0)`

Compute:

```text
corroboration_lift =
  clamp(
    0.45 * match_strength
    + 0.25 * family_support_strength
    + 0.15 * variant_share_strength
    + 0.15 * source_count_strength,
    0.0,
    1.0
  )
```

Stored score:

```text
score_learned_anchor_corroboration = 0.5 + 0.5 * corroboration_lift
```

If no accepted corroboration exists:

```text
score_learned_anchor_corroboration = 0.5
```

### Why this is safe

- bounded;
- deterministic;
- positive-only in v1;
- neutral when learned evidence is weak;
- separate from FR-008 phrase math.

## Normalization And Bounds

Stored score:

- `Suggestion.score_learned_anchor_corroboration` in `[0.5, 1.0]` for v1;
- `0.5` is neutral.

Centered additive component:

```text
score_learned_anchor_component =
  2 * (score_learned_anchor_corroboration - 0.5)
```

This gives `[0.0, 1.0]` in v1.

Exact ranking hook:

```text
score_final += learned_anchor.ranking_weight * score_learned_anchor_component
```

Default safety rule:

- with `ranking_weight = 0.0`, FR-009 does not change ranking order.

## Settings And Defaults

### Operator-facing settings

Persist through `AppSetting` with category `anchor`.

Recommended keys:

- `learned_anchor.ranking_weight`
- `learned_anchor.minimum_anchor_sources`
- `learned_anchor.minimum_family_support_share`
- `learned_anchor.enable_noise_filter`

Defaults:

- `ranking_weight = 0.0`
- `minimum_anchor_sources = 2`
- `minimum_family_support_share = 0.15`
- `enable_noise_filter = true`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `1 <= minimum_anchor_sources <= 10`
- `0.05 <= minimum_family_support_share <= 0.50`

### Code constants for v1

Keep these fixed in the first implementation pass:

- `max_anchor_families = 8`
- `max_alternates_per_family = 5`
- `family_min_overlap_tokens = 2`
- `family_min_overlap_ratio = 0.60`
- `max_small_variant_edit_distance = 1`

Reason:

- these are shape controls, not day-one operator knobs;
- keeping them fixed makes FR-009 smaller and easier to verify.

## Diagnostics And Explainability

### Suggestion detail diagnostics

Expose a separate `learned_anchor_diagnostics` object.

Required fields:

- `score_learned_anchor_corroboration`
- `learned_anchor_state`
  - `exact_variant_match`
  - `family_match`
  - `host_contains_canonical_variant`
  - `neutral_no_anchor_candidate`
  - `neutral_no_learned_anchor_data`
  - `neutral_below_min_sources`
  - `neutral_no_family_match`
  - `neutral_processing_error`
- `candidate_anchor_text`
- `candidate_anchor_normalized`
- `matched_family_canonical`
- `matched_variant_display`
- `family_support_share`
- `variant_support_share`
- `supporting_source_count`
- `usable_inbound_anchor_sources`
- `learned_family_count`
- `top_learned_families`
  - array of objects with:
    - `canonical_anchor`
    - `support_share`
    - `supporting_source_count`
    - `alternate_variants`
- `host_contains_canonical_variant`
- `recommended_canonical_anchor`

### Plain-English review helper text

Review helper text should say:

- `Learned anchor means wording the site already uses when it links to this destination.`
- `Corroborated means the chosen anchor looks like a learned site pattern.`
- `Neutral means the site does not have enough clean anchor history yet.`

### Settings helper text

- `Learned anchors come from existing live internal links only.`
- `Ranking impact is off by default until you set a small non-zero weight.`

## Storage Impact, If Any

### Existing storage reused

Reuse:

- `ExistingLink.anchor_text`
- `ExistingLink.from_content_item`
- `ExistingLink.to_content_item`
- `PipelineRun.config_snapshot`

### Storage allowed in the first implementation pass

Allowed:

- one new suggestion score field:
  - `Suggestion.score_learned_anchor_corroboration`
- one new suggestion diagnostics field:
  - `Suggestion.learned_anchor_diagnostics`
- FR-009 settings in `AppSetting`
- FR-009 settings + algorithm version in `PipelineRun.config_snapshot`

### Storage explicitly not allowed in the first implementation pass

Not allowed:

- no new graph table;
- no new destination-level learned-anchor cache table;
- no `ContentItem` learned-anchor score field;
- no reviewer preference table;
- no reviewer disallow table;
- no automatic anchor-policy history table.

Reason:

- the repo already has the raw anchor evidence on `ExistingLink`;
- the first pass should stay suggestion-level and additive;
- manual preference/disallow storage is a separate policy layer and would widen scope too much for the first FR-009 implementation pass.

## API / Admin / Review / Settings Impact, If Any

### Backend API

Add:

- `GET /api/settings/learned-anchor/`
- `PUT /api/settings/learned-anchor/`

No recalculation endpoint in the first pass.

Reason:

- FR-009 vocabulary is built from existing live anchor rows at suggestion-generation time;
- there is no separate destination-wide cache to recalculate in v1.

### Suggestion API

Extend suggestion detail output with:

- `score_learned_anchor_corroboration`
- `learned_anchor_diagnostics`

List view stays unchanged in v1.

### Admin

Expose in `SuggestionAdmin`:

- `score_learned_anchor_corroboration`
- `learned_anchor_diagnostics` read-only

No new `ExistingLink` admin behavior required in v1.

### Review UI

Add one new detail row:

- `Learned Anchor Corroboration`

Add one small diagnostics block:

- learned state;
- canonical anchor;
- alternate variants;
- support counts;
- neutral message when evidence is thin.

### Settings UI

Add one small settings card:

- ranking weight;
- minimum anchor sources;
- minimum family support share;
- noise filter enabled.

### Reviewer controls

Not in the first implementation pass:

- no saved prefer/disallow action;
- no persistent reviewer anchor policy editing.

The review UI may show learned variants read-only in v1.

## Rollout Plan

### Step 1 - read-only learned vocabulary and neutral score

- build destination learned-anchor vocabulary from existing live anchor text;
- persist `score_learned_anchor_corroboration` and diagnostics;
- keep `ranking_weight = 0.0`;
- keep learned variants read-only in review/admin.

### Step 2 - inspect diagnostics

- verify that canonical anchors and alternates look sensible;
- verify that neutral behavior is common on thin-history destinations;
- verify that FR-008 anchors are not being silently rewritten.

### Step 3 - optional small ranking enablement

- only after verification passes;
- operator may set a small non-zero weight;
- recommended first live weight: `0.02` to `0.04`.

## Rollback Plan

Immediate rollback:

- set `learned_anchor.ranking_weight = 0.0`

Operational rollback:

- leave stored learned-anchor diagnostics in place;
- hide review/settings UI for FR-009 if needed;
- keep FR-008 anchor selection behavior unchanged.

Failure rule:

- if learned-anchor processing fails for a candidate, return neutral `0.5` and do not block suggestion creation.

## Test Plan

### 1. Vocabulary build from existing links

- inbound `ExistingLink.anchor_text` rows produce learned families;
- blank anchors are ignored;
- per-source dedupe works.

### 2. Noise filtering

- generic anchors like `click here` and `read more` are removed;
- all-noise destinations stay neutral.

### 3. Canonical family selection

- repeated similar anchors cluster into one family;
- the highest-support variant becomes canonical;
- typo outliers do not become canonical.

### 4. Exact corroboration

- chosen anchor exactly matches a learned variant;
- assert `score_learned_anchor_corroboration > 0.5`;
- assert learned state is `exact_variant_match`.

### 5. Family corroboration

- chosen anchor is close to a learned family but not an exact variant;
- assert learned state is `family_match`;
- assert score is above neutral.

### 6. Thin-history neutral fallback

- fewer than `minimum_anchor_sources` usable inbound anchors;
- assert stored score is `0.5`.

### 7. No-candidate-anchor neutral fallback

- suggestion has no anchor candidate;
- assert learned score is neutral.

### 8. No-family-match neutral fallback

- destination has learned families but chosen anchor does not match any;
- assert learned score is neutral;
- assert no negative penalty is applied.

### 9. Ranking off by default

- with `ranking_weight = 0.0`, ranking order does not change.

### 10. Review/detail/admin contract

- suggestion detail exposes learned score and diagnostics;
- review dialog renders canonical + alternate learned anchors;
- admin shows read-only learned diagnostics.

### 11. Pipeline snapshot

- pipeline run stores FR-009 settings and FR-009 algorithm version in `config_snapshot`.

### 12. Boundary checks

- changing FR-008 settings does not change learned vocabulary inputs;
- changing FR-006 settings does not change learned vocabulary inputs;
- changing FR-007 settings does not change learned vocabulary inputs;
- changing velocity data does not change learned vocabulary inputs.

## Risks And Open Questions

### Risks

- some destinations may not have enough inbound links to learn useful anchors;
- historic live anchors can include noisy or low-quality wording;
- family grouping that is too loose can merge unrelated anchors;
- family grouping that is too strict can fragment obvious variants.

### Open questions

1. Should FR-009 ever auto-swap a weaker FR-008 anchor to a learned canonical variant already present in the same sentence?
   - Proposed v1 answer: no. Report it only.
2. Should reviewer prefer/disallow choices be part of the first FR-009 implementation pass?
   - Proposed v1 answer: no. Defer to a later policy slice if the read-only learned vocabulary proves useful.
3. Should learned-anchor families ever use FR-006 source authority as a weight?
   - Proposed v1 answer: no in v1. Keep FR-009 independent.
4. Should list view show learned-anchor score?
   - Proposed v1 answer: no. Detail and admin only.

## Exact Repo Modules Likely To Be Touched In The Later Implementation Session

### Pipeline and scoring

- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/services/pipeline.py`
- `backend/apps/pipeline/services/anchor_extractor.py`
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/<new learned anchor service>`

### Existing-link evidence source

- `backend/apps/graph/models.py`

Read only in the first implementation pass:

- use existing `ExistingLink.anchor_text` data;
- no schema change required.

### Suggestion storage and surfacing

- `backend/apps/suggestions/models.py`
- `backend/apps/suggestions/serializers.py`
- `backend/apps/suggestions/views.py`
- `backend/apps/suggestions/admin.py`
- `backend/apps/suggestions/migrations/<new migration>`

### Settings and API

- `backend/apps/core/views.py`
- `backend/apps/api/urls.py`

### Frontend review and settings

- `frontend/src/app/review/suggestion.service.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

## Implementation Decision

Path chosen:

- keep FR-009 suggestion-level and separate from FR-008;
- learn anchor vocabulary only from existing live inbound anchor text;
- corroborate the already chosen anchor instead of rediscovering the anchor from scratch;
- keep missing or weak learned-anchor evidence neutral;
- keep ranking impact off by default;
- do not add destination-level cache tables or reviewer policy storage in the first implementation pass.
