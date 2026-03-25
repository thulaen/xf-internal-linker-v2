# FR-010 - Rare-Term Propagation Across Related Pages

## Confirmation

Simple version first.

- Active target confirmed: when the FR-010 implementation pass began, `Phase 13 / FR-010 - Rare-Term Propagation Across Related Pages` was the next exact target in `AI-CONTEXT.md` and `FEATURE-REQUESTS.md`.
- Spec status confirmed: this file is the approved FR-010 source of truth for behavior and guardrails.
- Repo confirmed: FR-010 now has implementation coverage in backend code plus review/settings exposure in the frontend.
- Repo confirmed: the live pipeline already has separate FR-006 weighted authority, FR-007 link freshness, FR-008 phrase relevance, and FR-009 learned-anchor corroboration paths.

## Current Repo Map

### Content and relationship data already available

- `backend/apps/content/models.py`
  - `ContentItem` already stores `title`, `distilled_text`, `url`, `scope`, `march_2026_pagerank_score`, `velocity_score`, and `link_freshness_score`.
  - `ScopeItem` already stores `parent` and optional `silo_group`.
- `backend/apps/pipeline/services/pipeline.py`
  - already loads `ContentRecord` rows with:
    - destination text tokens
    - scope / parent / grandparent identifiers
    - silo-group identifiers
- `backend/apps/pipeline/services/ranker.py`
  - already defines:
    - `score_node_affinity(...)` for structural closeness
    - silo compatibility rules
    - separate additive hooks for FR-006, FR-007, FR-008, and FR-009
- `backend/apps/pipeline/services/text_tokens.py`
  - already provides the normalized tokenization rules used by the live ranker.

### Storage and settings patterns already available

- `backend/apps/suggestions/models.py`
  - already stores separate suggestion-level score fields and JSON diagnostics for newer ranking layers.
- `backend/apps/suggestions/views.py`
  - already snapshots per-feature settings and algorithm versions into `PipelineRun.config_snapshot`.
- `backend/apps/core/views.py`
  - already exposes per-feature settings endpoints and validation logic.
- `frontend/src/app/settings/silo-settings.service.ts`
  - now loads and saves separate settings cards for FR-006 to FR-010.

### Important repo fact for FR-010

- There is no current place where propagated terms are stored on `ContentItem`.
- FR-010 uses separate `Suggestion.score_rare_term_propagation` and `Suggestion.rare_term_diagnostics` fields.
- FR-010 has its own settings surface and review exposure, but the propagation signal still stays suggestion-time only.

## Plain-English Summary

Simple version first.

Sometimes one page on a site uses a very special word, but a nearby page is really about the same thing and never says that word out loud.

FR-010 lets the app borrow a few rare, strong words from nearby related destination pages, but only in a very controlled way.

It does **not** rewrite the destination text.
It does **not** mix borrowed words into embeddings, phrase matching, or learned anchors.
It only adds a small separate bonus when a host sentence contains one of those safely borrowed rare terms.

## Problem Statement

Today the pipeline mainly understands a destination through:

- its own `title`
- its own `distilled_text`
- its own authority / freshness / phrase / learned-anchor signals

That leaves a gap.

A destination can be strongly related to a few nearby pages in the same area of the site, and those nearby pages may contain a rare, high-signal term that the destination itself does not contain.

Examples:

- a nearby guide page might use a model name or location name;
- a sibling page might use a niche product family term;
- a closely related page might use an uncommon category term that helps a host sentence line up with the right destination.

Without a separate propagation layer, the app may miss those host sentences entirely or rank them too low.

## Goals

FR-010 should:

- add a separate, explainable, bounded rare-term propagation signal;
- borrow only a small number of rare terms from nearby related destination pages;
- define "related pages" using existing repo concepts such as scope ancestry and silo compatibility;
- keep propagated evidence separate from the destination's original text evidence;
- keep missing or weak propagation evidence neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-010 does not:

- rewrite `ContentItem.title`, `ContentItem.distilled_text`, or embeddings;
- change FR-006 weighted-authority math;
- change FR-007 link-freshness math;
- change FR-008 phrase-inventory or phrase-matching math;
- change FR-009 learned-anchor vocabulary logic;
- implement FR-011 field-aware scoring;
- use analytics, reviewer feedback loops, or adaptive tuning;
- introduce a broad new indexing subsystem in the first implementation pass;
- implement production code in this session.

## Patent / Source Inspiration Summary

Primary source:

- `US20110196861A1 - Propagating Information Among Web Pages`

Useful source ideas for this repo:

- pages on the same site can share highly descriptive information;
- uncommon or high-signal terms can be associated with related pages, not only the page where the term first appeared;
- the propagated information should remain a separate association, not hidden inside the original page text;
- any score increase should be bounded and layered onto an existing relevance score, not replace it.

Repo-safe reading of the source:

- the patent is query-time and search-engine oriented;
- this repo is suggestion-time and site-local;
- the core reusable idea is still valid:
  - save a controlled association between a rare term and nearby related pages,
  - then give a bounded boost when that term appears in a relevant match context.

## Math-Fidelity Note

### Directly supported by the source

- propagate strongly descriptive terms across related pages;
- treat propagated information as an association, not original page text;
- apply a bounded score increase rather than a hard replacement;
- limit propagation to related pages within the same site.

### Adapted for this repo

- Inference: "related pages" should map to this repo's structural scope tree plus silo compatibility rules.
- Inference: the repo's normalized destination token sets are the practical place to detect rare terms.
- Inference: because the current ranker is additive and bounded, FR-010 should be a separate suggestion-level score, not a content-level rewrite.
- Inference: FR-010 v1 should propagate only **single rare tokens**, not phrases, to stay cleanly separate from FR-008 phrase matching and FR-011 field-aware scoring.

### Deliberately not carried over in FR-010 v1

- no search-engine query rewriting;
- no website-wide query/result scoring engine;
- no URL-only site-map crawler logic;
- no hidden insertion of propagated terms into stored text;
- no phrase propagation;
- no authority-weighted donor terms in v1;
- no user-click or telemetry-based propagation.

## Scope Boundary Versus FR-006, FR-007, FR-008, FR-009, and FR-011

FR-010 must stay separate from:

- `FR-006`
  - do not use `ExistingLink` edge prominence fields;
  - do not reuse PageRank as donor-term weight in v1.
- `FR-007`
  - do not use link-appearance or disappearance timing as propagation evidence.
- `FR-008`
  - do not propagate phrases or anchor spans;
  - do not add propagated terms into the destination phrase inventory.
- `FR-009`
  - do not learn propagated terms from inbound anchor text;
  - do not mix rare-term evidence into learned-anchor corroboration.
- `FR-011`
  - do not split propagated evidence by title/body/anchor fields;
  - do not add field-level weighting rules here.

Hard rule:

- FR-010 v1 propagates only bounded **single-token**, suggestion-level evidence from structurally related destination pages.

## Inputs Required

FR-010 v1 can use only data the repo already loads:

- destination `title`
- destination `distilled_text`
- host sentence text
- destination `scope`, `parent`, and `grandparent` context
- destination `silo_group`
- normalized token sets from `tokenize_text(...)`

Allowed FR-010 inputs:

- `ContentRecord.tokens`
- `ContentRecord.scope_id`, `parent_id`, `grandparent_id`
- `ContentRecord.silo_group_id`
- host sentence normalized tokens

Explicitly disallowed FR-010 inputs in v1:

- inbound anchor text from `ExistingLink.anchor_text`
- FR-006 weighted-edge fields
- FR-007 history rows
- velocity metrics
- reviewer-edited anchors
- analytics or search telemetry

## Relationship Rules For "Related Pages"

Simple version first.

A page is "related" only when it is nearby in the site's structure and not obviously in a different topical silo.

### Silo compatibility rule

If both destination pages have silo assignments:

- same silo => still eligible
- different silos => not eligible

If either page has no silo assignment:

- do not block on silo alone

### Structural relationship tiers

For destination page `d` and donor page `r`, `r` is eligible only when one of these is true:

1. `same_scope`
   - `d.scope_id == r.scope_id`
   - relationship weight = `1.00`
2. `same_parent`
   - `d.parent_id == r.parent_id`
   - relationship weight = `0.75`
3. `same_grandparent`
   - `d.grandparent_id == r.grandparent_id`
   - relationship weight = `0.50`

No other relationship types are allowed in v1.

### Shared-topic guardrail

Structural proximity alone is not enough.

Use the normalized original destination token sets only.

Eligibility also requires:

- `same_scope`: at least `1` shared original token between `d` and `r`
- `same_parent` or `same_grandparent`: at least `2` shared original tokens between `d` and `r`

This guardrail uses only the pages' original tokens.
It does not look at propagated terms.

### Donor-page cap

For one destination:

- keep at most `5` donor pages

Order donor pages by:

1. higher relationship weight
2. higher shared-token count
3. lower content ID as a stable tie-break

## Rare-Term Definition And Thresholds

FR-010 v1 uses only single normalized tokens.

### A token can be a candidate rare term only when all are true

- length is at least `5` characters
- it contains at least one letter
- it is not numeric-only
- it survives the existing stopword filter
- it appears in the donor page's original destination tokens
- it does **not** appear in the destination page's original tokens

### Site-wide rarity threshold

Let `document_frequency(term)` be the number of non-deleted destination pages whose original token set contains the term.

Default rule:

- a token is rare when `document_frequency(term) <= 3`

Operator-facing bound for later implementation:

- `1 <= max_document_frequency <= 10`

Default:

- `max_document_frequency = 3`

### Minimum support across related pages

A candidate propagated term must appear in at least:

- `2` eligible donor pages

Operator-facing bound:

- `1 <= minimum_supporting_related_pages <= 5`

Default:

- `minimum_supporting_related_pages = 2`

## Exact Bounded Signal Design

### Step 1 - build site-wide rare-term stats once per pipeline run

Using all non-deleted destination pages:

- tokenize each page's original destination text with `tokenize_text(...)`
- count per-term document frequency

Important:

- "original destination text" means only the destination page's own `title + distilled_text`
- propagated terms are not fed back into this corpus count

### Step 2 - build a propagated rare-term profile for each destination

For one destination `d`:

1. find eligible donor pages using the structural + silo + shared-topic rules above
2. keep only the top `5` donors
3. from each donor, extract candidate rare terms using the rarity rules above
4. keep at most `3` contributed terms per donor
5. merge identical terms across donors
6. keep at most `8` propagated terms for the destination

Per merged propagated term store:

- `term`
- `document_frequency`
- `supporting_related_pages`
- `supporting_relationship_weights`
- `average_relationship_weight`

### Step 3 - per-term evidence score

For one propagated term `t`:

- `relationship_strength(t) = average_relationship_weight(t)`
- `support_strength(t) = min(1.0, supporting_related_pages(t) / 3.0)`
- `rarity_strength(t) = 1.0 - ((document_frequency(t) - 1) / max(max_document_frequency, 1))`
  - then clamp to `[0.0, 1.0]`

Compute:

```text
term_evidence(t) =
  clamp(
    0.45 * relationship_strength(t)
    + 0.35 * support_strength(t)
    + 0.20 * rarity_strength(t),
    0.0,
    1.0
  )
```

### Step 4 - host-sentence match rule

For one suggestion candidate:

- normalize host sentence tokens with the existing tokenization rules
- a propagated term matches only when the exact normalized term appears in the host sentence token set

Duplicate-counting rules:

- the same term counts at most once per host sentence
- repeated occurrences of the same term in the sentence do not add extra credit
- multiple donor pages supporting the same term are merged into one term score before sentence scoring

### Step 5 - suggestion-level rare-term score

If no propagated terms match the host sentence:

```text
score_rare_term_propagation = 0.5
```

If one or more propagated terms match:

1. sort matched propagated terms by:
   - higher `term_evidence`
   - higher supporting-related-page count
   - alphabetical term tie-break
2. keep at most the top `2` unique matched terms
3. compute:

```text
rare_term_lift =
  average(term_evidence(top_matched_terms))
```

Stored score:

```text
score_rare_term_propagation = 0.5 + 0.5 * rare_term_lift
```

### Why this is bounded and safe

- no negative penalty in v1
- no score below `0.5`
- at most `2` matched propagated terms can affect one suggestion
- donor pages are capped
- propagated terms per donor and per destination are capped

## Propagation Limits And Drift Guards

These rules are mandatory.

### Topic drift guardrails

- never propagate across different assigned silos
- never propagate outside the same scope / same parent / same grandparent family
- require shared original-token overlap before a donor page is eligible
- never use already propagated terms to qualify another donor page

### Over-propagation guardrails

- max `5` donor pages per destination
- max `3` donated terms per donor page
- max `8` propagated terms per destination
- max `2` matched propagated terms per suggestion

### Duplicate-counting guardrails

- merge same term across donors before scoring
- count each matched term once per host sentence
- if a term already exists in the destination's original tokens, it is not a propagated term

### Hidden-mixing guardrails

- do not append propagated terms to `distilled_text`
- do not append propagated terms to `ContentRecord.tokens`
- do not add propagated terms to embeddings
- do not add propagated terms to FR-008 phrase inventory
- do not add propagated terms to FR-009 learned-anchor vocabulary

### Explainability guardrails

- store the matched propagated terms separately in diagnostics
- store donor counts and relationship tiers
- store original destination tokens and propagated terms as separate concepts

## How Propagated Evidence Stays Separate From Original Content Evidence

Simple version first.

The app must always know:

- what the destination page really says itself;
- what extra rare terms were only borrowed from related pages.

Separation rules:

- original evidence comes only from the destination page's own `title + distilled_text`
- propagated evidence is built in a separate in-memory profile during the pipeline run
- host-sentence scoring uses a separate FR-010 score field and a separate diagnostics object
- original-token overlap tests use only original destination tokens
- propagated terms are never written back into persistent destination text fields

Required diagnostics separation:

- `original_destination_terms`
- `propagated_term_candidates`
- `matched_propagated_terms`

These must remain separate arrays or objects.

## Ranking Integration Plan

Add one new suggestion-level score:

- `Suggestion.score_rare_term_propagation`

Add one centered additive component:

```text
score_rare_term_component =
  max(0.0, min(1.0, 2.0 * (score_rare_term_propagation - 0.5)))
```

Exact ranking hook:

```text
score_final += rare_term_propagation.ranking_weight * score_rare_term_component
```

Default safety rule:

- with `ranking_weight = 0.0`, FR-010 does not change ranking order

Important:

- FR-010 is positive-only in v1
- no match means neutral, not penalty
- this keeps the feature easy to explain and easy to disable

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `rare_term_propagation.enabled`
- `rare_term_propagation.ranking_weight`
- `rare_term_propagation.max_document_frequency`
- `rare_term_propagation.minimum_supporting_related_pages`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `max_document_frequency = 3`
- `minimum_supporting_related_pages = 2`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `1 <= max_document_frequency <= 10`
- `1 <= minimum_supporting_related_pages <= 5`

### Code-defined constants for v1

Keep these fixed in the first implementation pass:

- `minimum_term_chars = 5`
- `max_donor_pages = 5`
- `max_terms_per_donor = 3`
- `max_terms_per_destination = 8`
- `max_terms_per_suggestion = 2`

Reason:

- they shape the safety envelope of the feature;
- exposing them all as UI knobs would widen the rollout too much.

### Feature-flag behavior

- `enabled = false`
  - do not build propagated-term profiles
  - store neutral `0.5`
  - skip FR-010 diagnostics
- `enabled = true` and `ranking_weight = 0.0`
  - build diagnostics and store the separate score
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.rare_term_diagnostics`

Required fields:

- `score_rare_term_propagation`
- `rare_term_state`
  - `computed_match`
  - `neutral_feature_disabled`
  - `neutral_no_eligible_related_pages`
  - `neutral_no_rare_terms`
  - `neutral_below_min_support`
  - `neutral_no_host_match`
  - `neutral_processing_error`
- `original_destination_terms`
  - small preview only, not the full token set
- `matched_propagated_terms`
  - array of objects with:
    - `term`
    - `document_frequency`
    - `supporting_related_pages`
    - `average_relationship_weight`
    - `term_evidence`
- `top_propagated_terms`
  - top destination candidates even if not matched
- `eligible_related_page_count`
- `related_page_summary`
  - array of objects with:
    - `content_id`
    - `relationship_tier`
    - `shared_original_token_count`
- `max_document_frequency`
- `minimum_supporting_related_pages`

Plain-English review helper text should say:

- `Rare-term propagation means this sentence uses a rare word that nearby related pages use for this topic.`
- `Neutral means there was not enough safe related-page evidence to borrow terms.`
- `Borrowed words stay separate from the destination's own text.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_rare_term_propagation: FloatField(default=0.5)`
- `rare_term_diagnostics: JSONField(default=dict, blank=True)`

### Content model

No new `ContentItem` field is needed in v1.

Reason:

- propagation is suggestion-time evidence, not a stable content-wide score;
- storing it on `ContentItem` would blur original content and borrowed evidence.

### Separate tables

No new table is required in v1.

Reason:

- the current pipeline already loads all content records needed to compute donor pages and token frequencies in memory;
- a cache table would widen scope before the first rollout proves useful.

### PipelineRun snapshot

Add FR-010 settings and FR-010 algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/rare-term-propagation/`
- `PUT /api/settings/rare-term-propagation/`

No recalculation endpoint in v1.

Reason:

- FR-010 is suggestion-time logic, not a persisted destination-wide recalculation like FR-006 or FR-007.

### Review / admin / frontend

Add one new review row:

- `Rare-Term Propagation`

Add one small diagnostics block:

- matched propagated terms
- donor-page count
- neutral reason when no safe propagation was used

Add one settings card:

- enabled
- ranking weight
- max document frequency
- minimum supporting related pages

## Backend Service Touch Points

Likely implementation files for the later code pass:

- `backend/apps/pipeline/services/pipeline.py`
- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/services/text_tokens.py`
- `backend/apps/pipeline/services/<new rare term propagation service>`
- `backend/apps/suggestions/models.py`
- `backend/apps/suggestions/serializers.py`
- `backend/apps/suggestions/views.py`
- `backend/apps/suggestions/admin.py`
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/core/views.py`
- `backend/apps/api/urls.py`
- `backend/apps/pipeline/tests.py`
- `backend/apps/suggestions/tests.py`
- `frontend/src/app/review/suggestion.service.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that should stay untouched in the first FR-010 implementation pass:

- `backend/apps/content/models.py`
- `backend/apps/graph/models.py`
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`

Reason:

- FR-010 v1 does not need new content fields, new graph history, or direct changes to FR-008 / FR-009 algorithms.

## Test Plan

### 1. Rare-term extraction and site-wide frequency

- terms under `5` characters are excluded
- stopwords are excluded
- numeric-only tokens are excluded
- site-wide document-frequency map is stable and deduped by page

### 2. Related-page eligibility

- same-scope donor with one shared token is eligible
- same-parent donor needs at least two shared tokens
- same-grandparent donor needs at least two shared tokens
- cross-silo donor is rejected when both pages have different silos

### 3. Destination separation rules

- a term already present in the destination's original tokens is never treated as propagated
- propagated terms do not mutate destination token sets or phrase inventories

### 4. Support threshold behavior

- one donor page is neutral when `minimum_supporting_related_pages = 2`
- two donor pages for the same term can qualify

### 5. Host-sentence matching

- exact normalized token presence in the host sentence triggers a match
- repeated copies of the same token in the sentence count once
- unmatched propagated terms do not affect the score

### 6. Duplicate-counting protection

- the same term supported by multiple donors merges into one term score
- multiple host-sentence occurrences of the same term count once

### 7. Caps and bounds

- no more than `5` donor pages per destination
- no more than `3` terms per donor page
- no more than `8` propagated terms per destination
- no more than `2` matched terms per suggestion
- stored score stays in `[0.5, 1.0]`

### 8. Ranking off by default

- with `ranking_weight = 0.0`, ranking order stays unchanged

### 9. Feature disabled behavior

- with `enabled = false`, score is `0.5`
- diagnostics report `neutral_feature_disabled`

### 10. Serializer / admin / frontend contract

- suggestion detail exposes `score_rare_term_propagation`
- suggestion detail exposes `rare_term_diagnostics`
- review dialog renders the `Rare-Term Propagation` row
- settings page loads and saves FR-010 settings

### 11. Snapshot coverage

- `PipelineRun.config_snapshot` stores FR-010 settings and algorithm version

### 12. Boundary checks

- changing FR-006 settings does not change FR-010 propagated terms
- changing FR-007 settings does not change FR-010 propagated terms
- changing FR-008 phrase settings does not change which terms are considered rare
- changing FR-009 learned-anchor settings does not change FR-010 propagated terms

## Rollout Plan

### Step 1 - diagnostics only

- implement FR-010 profile building and suggestion-level diagnostics
- keep `ranking_weight = 0.0`

### Step 2 - operator review

- inspect whether matched propagated terms look sensible
- confirm neutral behavior is common when structure or support is weak
- confirm no hidden mixing with phrase or learned-anchor diagnostics

### Step 3 - optional small ranking enablement

- only after verification passes
- recommended first live weight: `0.02` to `0.04`

## Risk List

- small sites may not have enough related-page support, so many results stay neutral;
- broad scopes can still contain mixed topics if the shared-token guard is too weak;
- spelling variants and naming variants may split obvious rare terms;
- too many donor pages would make scoring harder to explain if caps are loosened;
- future work could accidentally mix FR-010 propagated evidence into FR-008 or FR-011 if boundaries are ignored.

## Out Of Scope

- phrase propagation
- automatic destination-text rewriting
- automatic anchor rewriting
- content-level propagated-term caching tables
- authority-weighted donor terms
- telemetry-driven or reviewer-driven propagation
- any FR-011 field-aware scoring
- any FR-012 or later ranking work

## Implementation Decision

Path chosen:

- keep FR-010 suggestion-level and separate;
- propagate only bounded single-token rare terms;
- define related pages through existing scope ancestry plus silo compatibility;
- require donor support from more than one related page by default;
- keep missing or weak evidence neutral;
- keep ranking impact off by default;
- preserve strict separation from FR-006, FR-007, FR-008, FR-009, and FR-011.
