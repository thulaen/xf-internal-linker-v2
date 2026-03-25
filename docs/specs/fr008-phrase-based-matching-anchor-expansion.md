# FR-008 - Phrase-Based Matching & Anchor Expansion

## Confirmation

Simple version first.

- Active phase confirmed: `Phase 11 / FR-008 - Phrase-Based Matching & Anchor Expansion` is the next real target in `AI-CONTEXT.md` and `FEATURE-REQUESTS.md`.
- Spec-first confirmed: this session is creating the missing FR-008 spec only. It is not the implementation session.
- Repo confirmed: `docs/specs/fr008-phrase-based-matching-anchor-expansion.md` was missing before this spec pass.
- Repo confirmed: `docs/specs/fr006-weighted-link-graph.md` exists.
- Repo confirmed: `docs/specs/fr007-link-freshness-authority.md` exists.
- Repo confirmed: current live anchor extraction already exists in `backend/apps/pipeline/services/anchor_extractor.py`.
- Repo confirmed: the active pipeline calls that extractor from `backend/apps/pipeline/services/pipeline.py` when it creates `Suggestion` rows.
- Repo confirmed: current phrase-like logic is limited to:
  - exact, title-based anchor matching in `backend/apps/pipeline/services/anchor_extractor.py`;
  - keyword Jaccard overlap in `backend/apps/pipeline/services/ranker.py`.
- Repo confirmed: there is no separate FR-008 phrase score in the live ranker today.
- Repo confirmed: review detail, admin, and settings already expose PageRank and Link Freshness, but they do not yet expose any FR-008 phrase settings or phrase diagnostics.

## Current Repo Map

### Active anchor extraction path today

- `backend/apps/pipeline/services/anchor_extractor.py`
  - tokenizes with `TOKEN_RE`;
  - removes `STANDARD_ENGLISH_STOPWORDS`;
  - builds title n-grams only;
  - scans the host sentence for the first exact contiguous normalized match;
  - returns `strong` for 2+ token exact matches, `weak` for one long exact token, and `none` otherwise.
- `backend/apps/pipeline/services/pipeline.py`
  - calls `extract_anchor(sentence_record.text, dest_record.title)`;
  - persists the result into `Suggestion.anchor_phrase`, `anchor_start`, `anchor_end`, and `anchor_confidence`.

### Phrase-like logic already in ranking

- `backend/apps/pipeline/services/ranker.py`
  - uses semantic similarity;
  - uses keyword Jaccard overlap between destination text and host sentence;
  - uses node affinity;
  - uses host quality;
  - can add FR-006 weighted authority and FR-007 link freshness when their weights are enabled;
  - does not currently compute or add a phrase-specific score.

### Current storage and review surfaces

- `backend/apps/suggestions/models.py`
  - stores the current anchor phrase and score breakdown fields;
  - has `anchor_confidence` choices `strong`, `weak`, `none`;
  - has no dedicated FR-008 phrase score or phrase diagnostics field today.
- `backend/apps/suggestions/serializers.py`
  - detail view already returns semantic, keyword, node, quality, PageRank, velocity, and Link Freshness.
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
  - already shows anchor text and score rows;
  - does not yet show phrase-match reasoning.
- `frontend/src/app/settings/settings.component.html`
  - already has cards for March 2026 PageRank, Link Freshness, WordPress sync, and silos;
  - has no FR-008 card yet.

### Important doc-vs-code drift

- `docs/v2-master-plan.md` talks about a larger anchor-policy idea and long-tail anchor preferences.
- The live pipeline does not currently use that broader policy path.
- There is also an unused placeholder file at `backend/services/anchor_extractor.py`, but the active code path is `backend/apps/pipeline/services/anchor_extractor.py`.
- For FR-008, trust the active `apps/pipeline/services/*` path over the older placeholder and over future-looking master-plan text.

## Problem Summary

Simple version first.

The app can already find good host sentences.
It cannot yet do a smart job of understanding phrases inside those sentences.

Today the anchor extractor is narrow:

- it only looks for title words;
- it only accepts exact contiguous matches;
- it stops at the first match;
- it does not use destination distilled text;
- it does not score phrase evidence separately;
- it does not use local phrase context to expand anchors safely.

That creates two gaps:

1. good host sentences can rank well even when they contain a better phrase match than the title-only extractor can see;
2. the chosen anchor can be blank or weaker than it should be because the extractor only knows exact title windows.

FR-008 fills that gap with a separate phrase-based signal and a safer anchor-expansion rule.

## Goal

Add a small, explainable, bounded FR-008 phrase-matching layer that:

- builds a destination phrase inventory from `title` and `distilled_text`;
- finds exact and bounded partial phrase evidence inside the chosen host sentence;
- expands anchor extraction beyond exact title-only matching;
- keeps missing phrase evidence neutral, not negative;
- keeps ranking impact additive, bounded, and off by default;
- stays separate from FR-006 weighted authority, FR-007 link freshness, `velocity`, and FR-009 learned-anchor work.

## Non-goals

FR-008 does not:

- redesign FR-006 weighted-edge authority;
- redesign FR-007 freshness;
- use `velocity_score` or engagement metrics as phrase evidence;
- use `ExistingLink.anchor_text` or historical live anchors as learned anchor evidence;
- use `LinkFreshnessEdge` rows;
- add telemetry, alerts, or adaptive tuning;
- add queue-flow or sync-flow redesign;
- add new content-level storage on `ContentItem`;
- implement FR-009 learned-anchor corroboration;
- implement FR-011 field-aware scoring beyond the narrow title/distilled-text phrase inventory defined here;
- implement production code in this session.

## Source Summary From US7536408B2

Main source:

- `US7536408B2 - Phrase-based indexing in an information retrieval system`
- Google Patents: https://patents.google.com/patent/US7536408B2/en

Patent ideas that matter here:

- The system identifies meaningful phrases instead of relying only on single terms.
- Phrases can be related to other phrases using a predictive measure.
- Incomplete phrases can be extended into more complete phrase forms.
- Sentence relevance can be judged by the presence of query phrases, related phrases, and phrase extensions.
- Ranking can use both body phrase evidence and anchor phrase evidence.
- Anchor text is treated as stronger or more distinguished phrase evidence than ordinary body text in some parts of the indexing flow.

Concrete patent passages that drive this spec:

- The patent says the system uses phrases to index, search, rank, and describe documents, and that phrases can be multi-word phrases, including four, five, or more terms.
- It says incomplete phrases can be extended into likely longer phrases.
- It says sentence selection can use counts of query phrases, related phrases, and phrase extensions inside each sentence.
- It says ranking can combine a body-hit score and an anchor-hit score.

## Math-Fidelity Note

### Directly supported by the patent

- Use phrases, not just single words.
- Prefer complete phrases over incomplete left-prefix fragments.
- Allow phrase extensions.
- Use sentence-level phrase evidence.
- Combine body-like phrase evidence with anchor-like phrase evidence.

### Adapted for this repo

- Inference: this repo does not have a web-scale phrase corpus, posting lists, or phrase bit vectors, so FR-008 v1 uses a destination-local phrase inventory built from `title` and `distilled_text`.
- Inference: the host sentence already selected by the pipeline is the right local unit for phrase-evidence scoring.
- Inference: local context around the matched host phrase can stand in for a small, bounded version of the patent's broader related-phrase idea.
- Inference: because the current ranker is additive and bounded, FR-008 should expose a separate suggestion-level score with a dedicated ranking weight that defaults to `0.0`.

### Deliberately not carried over in FR-008 v1

- No corpus-wide information-gain matrix.
- No global related-phrase clusters.
- No anchor-hit computation from historical inbound links across the whole graph.
- No personalization.
- No duplicate-document logic.
- No learned anchor vocabulary from existing links. That belongs to `FR-009`.

## Scope Boundary Versus FR-006, FR-007, Velocity, and Later Phases

FR-008 must stay separate from:

- `FR-006`
  - do not reuse `ExistingLink.extraction_method`, `link_ordinal`, `source_internal_link_count`, or `context_class` as FR-008 phrase evidence;
  - do not treat FR-006 surrounding-text or prominence ideas as FR-008 phrase evidence.
- `FR-007`
  - do not use link-history timing, appearance counts, disappearance counts, or `link_freshness_score` as phrase evidence.
- `velocity`
  - do not use `view_count`, `reply_count`, `download_count`, `post_date`, `last_post_date`, or `velocity_score`.
- `FR-009`
  - do not use existing-link anchor text as learned anchor corroboration;
  - do not infer preferred anchor families from the graph.
- later phases
  - no field-aware weight expansion from `FR-011`;
  - no click-distance prior from `FR-012`;
  - no reranking/clustering/diversity work from `FR-013` to `FR-015`;
  - no telemetry or adaptive ranking from `FR-016` to `FR-020`.

Hard rule:

- FR-008 v1 uses only destination text, host sentence text, and a small local context window inside that host sentence.

## Inputs Required

FR-008 v1 needs only inputs that already exist in the repo:

- destination `title`
- destination `distilled_text`
- host `Sentence.text`
- current pipeline tokenization pattern:
  - `TOKEN_RE`
  - `STANDARD_ENGLISH_STOPWORDS`
- existing selected candidate context:
  - destination record
  - host sentence record
  - suggestion-level score assembly in `ranker.py`

Allowed text fields that may produce phrase evidence in v1:

- destination title
- destination distilled text
- host sentence text

Explicitly disallowed phrase-evidence fields in v1:

- scope names
- silo labels
- URLs
- existing live anchor text from `ExistingLink`
- FR-006 graph fields
- FR-007 history fields
- velocity metrics
- reviewer-edited anchors

## Neutral Fallback Behavior When Inputs Are Missing

Missing phrase evidence must be neutral, not negative.

Use a stored neutral score of `0.5` when any of these are true:

- destination has no usable title tokens and no usable distilled-text phrases;
- host sentence has no usable tokens;
- no acceptable exact or bounded partial phrase match is found;
- partial overlap exists but does not satisfy the acceptance rules;
- phrase extraction fails or returns invalid offsets;
- anchor expansion is disabled and the current fallback extractor also finds nothing.

Neutral behavior rules:

- `score_phrase_relevance = 0.5` means "no useful phrase evidence."
- FR-008 must not push the candidate down when evidence is missing.
- ranking contribution from a neutral phrase score must be `0.0`.
- if expanded phrase extraction finds nothing acceptable, the implementation should fall back to the current exact-title extractor before returning `none`.

## Proposed Phrase Extraction Logic

### Phrase units for FR-008 v1

Simple answer:

- use contiguous token phrases of length `1` to `5`;
- prefer `2` to `5` token phrases;
- allow `1` token phrases only when the token length is at least `5`.

### Destination phrase inventory

Build a destination-local phrase inventory from:

- `title`
- `distilled_text`

Rules:

1. tokenize with the same normalization style already used by the active pipeline:
   - lowercase
   - `TOKEN_RE`
   - stopword removal using `STANDARD_ENGLISH_STOPWORDS`
2. split phrase generation by source segment:
   - title is one segment;
   - distilled text should be split on sentence-like boundaries and newlines so phrases do not cross sentence edges.
3. generate contiguous candidate phrases from each segment:
   - lengths `1..5`
4. keep a phrase candidate only when:
   - it has `2..5` normalized tokens; or
   - it has `1` normalized token with length `>= 5`
5. record for each kept phrase:
   - normalized tokens
   - original surface text
   - source field: `title` or `distilled`
   - token count
   - source order

### Complete-phrase preference

Use a small local version of the patent's incomplete-phrase idea.

Rule:

- if a shorter candidate is a strict left-prefix of a longer candidate from the same source segment and same start position, prefer the longer phrase as the primary phrase.
- keep the shorter form only if it also appears independently from a different start position or from a different source segment.

Example:

- keep `internal linking guide`
- do not prefer `internal linking` from the same exact start position unless it also appears independently elsewhere.

### Inventory bound

Keep the inventory small and deterministic.

Recommended bound:

- maximum `24` unique destination phrases after dedupe and ranking.

Recommended ordering:

1. title phrases before distilled-only phrases
2. longer phrases before shorter phrases
3. earlier source appearance before later appearance

This keeps compute small and explainability simple.

## Proposed Phrase Matching Logic

### Host phrase candidates

For the chosen host sentence only:

- tokenize with the same normalized token rules;
- preserve character offsets;
- generate contiguous host token spans of length `1..5`.

### Exact match

Exact match means:

- normalized host span equals a kept destination phrase exactly.

Exact match types:

- `exact_title_phrase`
- `exact_distilled_phrase`

### Partial match

Partial match must be bounded.

Partial match means:

- host span and destination phrase are not equal;
- they share an ordered contiguous overlap;
- overlap is at least `2` normalized tokens;
- overlap covers at least `60%` of the shorter side;
- at least one local context corroboration hit exists inside the context window.

Partial match types:

- `partial_title_phrase`
- `partial_distilled_phrase`

### What counts as candidate phrase evidence in the host sentence

Candidate phrase evidence is:

- the matched host span itself; plus
- local corroboration around that span inside the same sentence.

Local corroboration may be:

- one additional destination token outside the anchor span but inside the context window; or
- one additional exact destination phrase inside the context window; or
- both.

This is local sentence corroboration only.
It is not the learned-anchor corroboration of `FR-009`.

### Context window size

Use a fixed same-sentence context window:

- `8` normalized tokens to the left;
- `8` normalized tokens to the right;
- clamped to sentence boundaries.

Reason:

- it is small;
- it is cheap;
- it stays aligned with the repo's sentence-level pipeline;
- it gives enough room for nearby topical words without drifting into adjacent sentences.

## Proposed Anchor Expansion Logic

### Current behavior to preserve as a fallback

Today the extractor:

- checks title phrases only;
- requires exact contiguous token equality;
- returns the first qualifying match.

Keep that as the fallback path.

### Expanded behavior for FR-008 v1

FR-008 anchor expansion should do this instead:

1. build the destination phrase inventory;
2. scan host sentence spans for exact phrase matches;
3. if no exact match wins and partial matching is enabled, scan bounded partial matches;
4. score all acceptable matches;
5. choose the single best host span as the anchor;
6. if no acceptable expanded match exists, fall back to the current extractor.

### How anchor expansion goes beyond exact title-only matching

It expands in three narrow ways:

- it allows exact matches from `distilled_text`, not just `title`;
- it prefers longer complete phrases over incomplete title prefixes;
- it allows bounded partial matches when local sentence context supports them.

### Selection tie-breakers

Choose the winning anchor candidate by:

1. higher FR-008 phrase score
2. exact before partial
3. title-sourced before distilled-only
4. longer token span
5. earlier sentence position

### Confidence mapping

Map back into the existing `Suggestion.anchor_confidence` field:

- `strong` = exact match
- `weak` = accepted partial match
- `none` = no acceptable match after expanded logic and fallback

## Proposed Scoring Logic

### New score name

Add one new suggestion-level score:

- `Suggestion.score_phrase_relevance`

This is a candidate-specific score, not a destination-wide content score.

### Scoring components

For an accepted phrase match:

- `match_strength`
  - `1.0` for exact
  - `0.4` for partial
- `source_strength`
  - `1.0` for title phrase
  - `0.7` for distilled-only phrase
- `context_strength`
  - `0.0` for no corroboration
  - `0.6` for one corroborating hit
  - `1.0` for two or more corroborating hits
- `length_strength`
  - `0.2` for one token
  - `0.6` for two tokens
  - `1.0` for three to five tokens

Then compute:

```text
phrase_lift =
  clamp(
    0.55 * match_strength
    + 0.20 * source_strength
    + 0.15 * context_strength
    + 0.10 * length_strength,
    0.0,
    1.0
  )
```

Stored suggestion score:

```text
score_phrase_relevance = 0.5 + 0.5 * phrase_lift
```

If there is no accepted phrase match:

```text
score_phrase_relevance = 0.5
```

### Why this is safe

- bounded
- deterministic
- explainable
- neutral when evidence is missing
- additive without creating hidden penalties

## Normalization and Bounds

Stored score:

- `Suggestion.score_phrase_relevance` in `[0.5, 1.0]` for v1
- `0.5` is neutral

Centered additive component:

```text
score_phrase_component = 2 * (score_phrase_relevance - 0.5)
```

Because v1 never stores below `0.5`, this component is in `[0.0, 1.0]`.

Exact ranking hook:

```text
score_final += phrase_matching.ranking_weight * score_phrase_component
```

Default safety rule:

- with `ranking_weight = 0.0`, FR-008 does not change ranking order.

## Settings and Defaults

### Operator-facing settings

Persist through `AppSetting` with category `anchor`.

Recommended keys:

- `phrase_matching.ranking_weight`
- `phrase_matching.enable_anchor_expansion`
- `phrase_matching.enable_partial_matching`
- `phrase_matching.context_window_tokens`

Defaults:

- `ranking_weight = 0.0`
- `enable_anchor_expansion = true`
- `enable_partial_matching = true`
- `context_window_tokens = 8`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `context_window_tokens` must be between `4` and `12`

### Code constants for v1

Keep these as code constants, not operator-facing settings in the first implementation pass:

- `max_phrase_tokens = 5`
- `max_destination_phrases = 24`
- `partial_min_token_overlap = 2`
- `partial_min_overlap_ratio = 0.60`
- `min_single_token_chars = 5`

Reason:

- these are implementation-shape controls, not day-one operator knobs;
- keeping them fixed makes rollout smaller and easier to test.

## Diagnostics and Explainability

### Suggestion detail diagnostics

Expose a small `phrase_match_diagnostics` object on suggestion detail.

Required fields:

- `score_phrase_relevance`
- `phrase_match_state`
  - `computed_exact_title`
  - `computed_exact_distilled`
  - `computed_partial_title`
  - `computed_partial_distilled`
  - `neutral_no_destination_phrases`
  - `neutral_no_host_match`
  - `neutral_partial_below_threshold`
  - `fallback_current_extractor`
- `selected_anchor_text`
- `selected_anchor_start`
- `selected_anchor_end`
- `selected_match_type`
  - `exact`
  - `partial`
  - `none`
- `selected_phrase_source`
  - `title`
  - `distilled`
  - `fallback`
  - `none`
- `selected_token_count`
- `context_window_tokens`
- `context_corroborating_hits`
- `destination_phrase_count`

### Review/admin plain-English helper text

Review helper text should say:

- `Phrase relevance means the host sentence contains a destination phrase or a close local phrase match.`
- `Neutral means the sentence did not provide useful phrase evidence.`
- `Partial means the sentence matched part of the destination phrase and nearby words supported it.`

### Settings helper text

- `Anchor expansion can use destination phrases from the title and distilled text.`
- `Ranking impact is off by default until you set a small non-zero weight.`

## Storage Impact, If Any

### ContentItem

No new `ContentItem` field is needed for FR-008 v1.

Reason:

- phrase evidence is host-sentence specific;
- anchor selection is suggestion specific;
- storing a content-wide phrase score would blur candidate-level evidence.

### Suggestion

Add:

- `score_phrase_relevance: FloatField(default=0.5)`
- `phrase_match_diagnostics: JSONField(default=dict, blank=True)`

Keep using existing fields:

- `anchor_phrase`
- `anchor_start`
- `anchor_end`
- `anchor_confidence`

### Separate tables

No separate phrase table is required in v1.

Reason:

- all needed source text already exists on `ContentItem` and `Sentence`;
- the inventory can be built on the fly during pipeline scoring;
- a separate phrase table would widen scope into caching/indexing work that is not necessary for the first FR-008 pass.

### PipelineRun snapshot

Add the FR-008 settings and FR-008 algorithm version to `PipelineRun.config_snapshot`.

## API/Admin Impact, If Any

### Backend API

Add:

- `GET /api/settings/phrase-matching/`
- `PUT /api/settings/phrase-matching/`

No recalculation endpoint is required in v1.

Reason:

- FR-008 phrase scoring is suggestion-time logic, not a destination-wide derived score like FR-006 or FR-007.
- settings changes should apply to new pipeline runs, not silently rewrite old suggestions.

### Suggestion API

Extend detail output with:

- `score_phrase_relevance`
- `phrase_match_diagnostics`

List view should remain unchanged in v1 to keep the UI small.

### Admin

Expose in `SuggestionAdmin`:

- `score_phrase_relevance`
- `phrase_match_diagnostics` read-only

### Review UI

Add one new detail row:

- `Phrase Relevance`

Add one small diagnostics block:

- exact vs partial
- title vs distilled source
- neutral/fallback message

### Settings UI

Add one small settings card:

- ranking weight
- enable anchor expansion
- enable partial matching
- context window tokens

### Content API / admin

No `ContentItem` API or admin change is required in v1.

## Rollout Plan

### Step 1 - pipeline-only phrase logic, no rank impact

- implement the phrase extractor/matcher;
- persist `score_phrase_relevance` and `phrase_match_diagnostics`;
- keep `ranking_weight = 0.0`.

### Step 2 - expose diagnostics

- show the phrase score and phrase reasoning in suggestion detail and admin;
- keep list views unchanged.

### Step 3 - optional small ranking enablement

- only after verification passes;
- operator may set a small non-zero `ranking_weight`;
- recommended first live weight: `0.03` to `0.05`.

## Rollback Plan

Immediate rollback:

- set `phrase_matching.ranking_weight = 0.0`

Anchor rollback:

- set `phrase_matching.enable_anchor_expansion = false`
- this returns anchor extraction to the current exact-title fallback path

Operational rollback:

- keep stored `score_phrase_relevance` and diagnostics for inspection;
- do not delete old suggestions just because FR-008 is disabled.

Failure rule:

- if FR-008 phrase extraction fails for a candidate, use neutral phrase score and the current extractor fallback instead of crashing the run.

## Test Plan

### 1. Destination phrase extraction

- title and distilled text produce a bounded destination phrase inventory
- stopword-only phrases are excluded
- one-token phrases shorter than `5` characters are excluded
- left-prefix incomplete phrases are not preferred over longer complete phrases from the same start position

### 2. Exact title match

- host sentence contains an exact title phrase
- assert `anchor_confidence == "strong"`
- assert `score_phrase_relevance > 0.5`

### 3. Exact distilled-text match

- host sentence contains a phrase from `distilled_text` that is not present in the title
- assert FR-008 finds it
- assert current title-only extractor alone would miss it

### 4. Partial match with corroboration

- host sentence contains a bounded partial overlap plus supporting nearby destination tokens
- assert `anchor_confidence == "weak"`
- assert `score_phrase_relevance > 0.5`

### 5. Partial match without corroboration

- same overlap but no corroborating local evidence
- assert the result is neutral
- assert no partial anchor is accepted

### 6. Neutral fallback

- destination has no usable phrases
- host sentence has no usable match
- extractor failure path
- assert `score_phrase_relevance == 0.5`

### 7. Ranking off-by-default

- with `ranking_weight = 0.0`, ranking order does not change

### 8. Anchor expansion fallback

- expanded matcher finds nothing
- current extractor still finds an exact title phrase
- assert fallback returns the current extractor's result

### 9. Longer complete phrase preference

- sentence contains both a shorter prefix match and a longer exact phrase
- assert the longer complete phrase wins

### 10. Diagnostics persistence

- suggestion detail returns `phrase_match_diagnostics`
- admin shows `score_phrase_relevance`
- config snapshot stores FR-008 settings

### 11. Boundary tests

- changing FR-006 settings does not alter phrase extraction inputs
- changing FR-007 settings or history rows does not alter phrase extraction inputs
- changing velocity-related content metrics does not alter phrase extraction inputs
- historical `ExistingLink.anchor_text` rows are ignored by FR-008 v1

### 12. UI contract

- Angular suggestion detail renders the `Phrase Relevance` row
- settings page can load and save FR-008 settings

## Risks and Open Questions

### Risks

- distilled text may sometimes surface phrases that are topically right but slightly awkward as anchor text;
- one-token exact matches can still be too broad for some topics, even with the length floor;
- phrase extraction that is too aggressive can make anchors look over-optimized;
- phrase extraction that is too conservative can miss good anchor spans and feel unchanged.

### Open questions

1. Should adjacent host sentences ever be considered as phrase context?
   - Proposed v1 answer: no. Stay sentence-local.
2. Should list view show phrase score?
   - Proposed v1 answer: no. Detail and admin only.
3. Should short branded or acronym tokens under five characters be allowed?
   - Proposed v1 answer: no special case in v1. Keep the rule simple.
4. Should FR-008 ever persist destination phrase inventories?
   - Proposed v1 answer: no. Build on the fly during pipeline runs.

## Exact Repo Modules Likely To Be Touched In The Later Implementation Session

### Pipeline and scoring

- `backend/apps/pipeline/services/anchor_extractor.py`
- `backend/apps/pipeline/services/pipeline.py`
- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/services/<new phrase matching service>`
- `backend/apps/pipeline/tests.py`

### Suggestions storage and surfacing

- `backend/apps/suggestions/models.py`
- `backend/apps/suggestions/serializers.py`
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

### Modules that should stay untouched in the first FR-008 implementation pass

- `backend/apps/content/models.py`
- `backend/apps/content/serializers.py`
- `backend/apps/content/views.py`
- `backend/apps/content/admin.py`
- `backend/apps/pipeline/tasks.py`

Reason:

- FR-008 v1 does not need content-level storage, content-level APIs, or a separate background recalculation task.

## Implementation Decision

Path chosen:

- keep FR-008 narrow and suggestion-level;
- use destination-local phrases from `title` and `distilled_text`;
- allow exact matches plus bounded partial matches with same-sentence corroboration;
- expand anchors beyond exact title-only matching;
- keep missing phrase evidence neutral;
- keep ranking impact off by default;
- keep FR-006, FR-007, velocity, and FR-009 fully separate.
