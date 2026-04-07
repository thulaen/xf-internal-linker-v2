# FR-051 - Reference Context Scoring

## Confirmation

- **Backlog confirmed**: `FR-051 - Reference Context Scoring` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No insertion-point context signal exists in the current ranker. The closest existing signal is `score_phrase_match` (FR-008), which checks whether the destination's anchor text appears in the host sentence. FR-051 measures how topically relevant the *surrounding paragraph window* is to the destination page — a fundamentally different scope.
- **Repo confirmed**: IDF vocabulary from BM25 field-aware relevance (FR-011) is already computed at pipeline time and can be reused without a second indexing pass.

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - `score_semantic` — sentence-level embedding similarity between host sentence and destination. Operates at the full sentence level.
  - `score_phrase_match` — checks if destination anchor text phrases appear in the host sentence. Operates on the anchor text, not the surrounding window.
  - `score_field_aware_relevance` — BM25 scoring across destination fields (title, body, scope, anchor). Uses IDF vocabulary that FR-051 can reuse.
  - No signal currently measures the *micro-context window* (the 5 words before and 5 words after the exact insertion point).

- `backend/apps/pipeline/services/field_aware_relevance.py` (FR-011)
  - Already computes and caches site-wide IDF values for the normalized vocabulary.
  - FR-051 needs the same IDF map at ranking time.

- `backend/apps/pipeline/services/text_tokens.py`
  - `tokenize_text(text)` — returns a normalized token set. Reused by FR-051 without modification.

### Source data already available at pipeline time

- `backend/apps/pipeline/services/pipeline.py`
  - Host page `distilled_text` is available at pipeline time.
  - The host sentence text and its position within the host page body are available per candidate.
  - Destination `ContentRecord` rows include normalized token sets.

### Storage and settings patterns already available

- `backend/apps/suggestions/models.py` — separate `FloatField` + `JSONField` per feature signal (FR-008 through FR-050 pattern).
- `backend/apps/core/views.py` — per-feature settings endpoints pattern.
- `backend/apps/suggestions/views.py` — `PipelineRun.config_snapshot` pattern for algorithm version snapshotting.

## Source Summary

### Patent: US8577893B1 — Ranking Based on Reference Contexts

**Plain-English description of the patent:**

The patent describes scoring links by examining the text window immediately surrounding the link insertion point. Rather than scoring the entire source document or the anchor text alone, it extracts the few words before and after the link location, weights them by how rare they are across the corpus (IDF), and uses that weighted window as a "context identifier" to measure how topically relevant the surrounding paragraph is to the linked destination.

**Repo-safe reading:**

The patent is designed for web-scale search engines scoring inbound links across the open web. This repo is site-local and suggestion-time. The reusable core idea is:

- extract a small fixed-size token window around the exact link insertion point;
- weight each token by its IDF (rarer words carry more signal);
- compare the weighted window against the destination page's token set;
- treat high overlap as evidence that the link sits in a topically appropriate context.

**What is directly supported by the patent:**

- using a fixed token window (the patent uses +-5 tokens) around the link position;
- weighting tokens by inverse document frequency to emphasize rare, topically informative words;
- using the resulting context score as an additive ranking signal.

**What is adapted for this repo:**

- "reference context" maps to the +-5-token window around the link insertion point within the host page body;
- IDF values are reused from the existing BM25 vocabulary (FR-011) rather than computed from a web-scale crawl;
- the patent scores existing links across the web; this repo scores *proposed* link insertion points at suggestion time.

## Plain-English Summary

Simple version first.

When the ranker picks a spot in a page to insert a link, the words immediately surrounding that spot matter. If those nearby words are closely related to the destination page, it is a good placement. If the surrounding words are about something completely different, the link will feel out of place to a reader.

FR-051 looks at the 5 words before and 5 words after the proposed insertion point, gives extra weight to rare words (because rare words carry more topic information), and checks how well those weighted words match the destination page.

Think of it this way: `score_semantic` asks "is the whole host sentence about the same topic as the destination?" FR-051 asks "are the words right next to the link spot particularly relevant to the destination?" These are different questions. A long sentence might be generally on-topic, but the insertion point might sit in a clause about something else entirely.

## Problem Statement

Today the ranker rewards relevance at the host-sentence level (`score_semantic`) and at the anchor-text level (`score_phrase_match`). It does not directly measure whether the *micro-context* — the few words immediately surrounding the proposed insertion point — is topically aligned with the destination.

This means two insertion points within the same long sentence are scored identically, even when one sits in a clause directly discussing the destination's topic and the other sits in a clause discussing something unrelated. A reader would experience these as very different link placements.

FR-051 closes this gap with a bounded, IDF-weighted window overlap score.

## Goals

FR-051 should:

- add a separate, explainable, bounded reference-context signal;
- compute it from the +-N-token window around the proposed link insertion point;
- weight tokens by IDF to emphasize rare, topically informative words;
- compare the weighted window against the destination page's token set;
- keep missing or insufficient context data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default;
- reuse the existing IDF vocabulary from FR-011 without a new indexing pass;
- fit the current Django + Celery + PostgreSQL + Angular architecture.

## Non-Goals

FR-051 does not:

- rewrite `ContentItem.distilled_text`, `ContentItem.title`, or any embedding;
- change `score_semantic`, `score_phrase_match`, `score_keyword`, or the core ranker weighted sum;
- change FR-006 through FR-050 logic;
- replace the sentence-level relevance requirement — a high context score does not override a low semantic score;
- use analytics, reviewer feedback, or any live query data;
- introduce a new IDF computation — it reuses FR-011's existing vocabulary;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `w_1, w_2, ..., w_k` = the `2N` tokens in the window centered on the insertion point (N tokens before, N tokens after, with `N = window_tokens`, default 5)
- `D` = normalized token set of the destination page `distilled_text`
- `idf(t)` = inverse document frequency of token `t` across the site corpus, from FR-011's BM25 vocabulary
- `smoothing` = `idf_smoothing` setting (default 1), added to the denominator to prevent division by zero on unseen tokens

**IDF definition (reused from FR-011):**

```text
idf(t) = log((N_docs + 1) / (df(t) + smoothing))
```

where `N_docs` = total documents in the site, `df(t)` = number of documents containing token `t`.

**Window-destination overlap score:**

```text
matched_weight = sum( idf(w_i) for w_i in window if w_i in D )
total_weight   = sum( idf(w_i) for w_i in window )
```

**Raw context ratio:**

```text
context_ratio = matched_weight / max(total_weight, epsilon)
```

where `epsilon = 1e-9` prevents division by zero.

This is the IDF-weighted fraction of the window's information content that is also present in the destination page.

**Bounded score:**

```text
score_reference_context = 0.5 + 0.5 * context_ratio
```

This maps:

- `context_ratio = 0.0` (no window token appears in the destination) -> `score = 0.5` (neutral)
- `context_ratio = 1.0` (every window token appears in the destination) -> `score = 1.0` (maximum)
- Typical values sit in `[0.55, 0.85]` for real content pairs.

**Neutral fallback:**

```text
score_reference_context = 0.5
```

Used when:

- window has fewer than 2 tokens (insertion point at the very start or end of text);
- destination token set is empty;
- IDF vocabulary is not available;
- feature is disabled.

### Why IDF weighting is the right choice

Stopwords like "the", "and", "is" will appear in almost every destination. Without IDF weighting, a window full of stopwords would score high against any destination — pure noise. IDF weighting ensures that only rare, topically informative words contribute meaningful signal. A window containing "stratocaster" (rare, high IDF) near a link to a guitar page is far more informative than a window containing "the best way to" (common, low IDF).

### Ranking hook

Add one centered additive component to the existing ranker:

```text
score_reference_context_component =
  max(0.0, min(1.0, 2.0 * (score_reference_context - 0.5)))
```

```text
score_final += reference_context.ranking_weight * score_reference_context_component
```

Default: `ranking_weight = 0.0` — diagnostics run silently with no ranking impact until an operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-051 must stay separate from:

- `score_semantic`
  - semantic measures sentence-level embedding similarity (dense vectors, full sentence);
  - FR-051 measures token-level IDF-weighted overlap in a narrow window (sparse tokens, 10-word window);
  - different input scope, different representation, different axis.

- `score_phrase_match` (FR-008)
  - phrase matching checks if the destination's anchor text phrases appear in the host sentence;
  - FR-051 checks if the *window tokens around the insertion point* appear in the *destination page body*;
  - opposite direction (anchor-in-sentence vs. window-in-destination) and different scope.

- `score_keyword`
  - keyword uses unweighted Jaccard on host sentence vs destination tokens;
  - FR-051 uses IDF-weighted overlap on a narrow window vs destination tokens;
  - different scope (full sentence vs window) and different weighting (uniform vs IDF).

- `score_field_aware_relevance` (FR-011)
  - FR-011 applies BM25 field weighting across destination title, body, scope, and anchor fields;
  - FR-051 does not apply field weighting. It uses IDF values from the same vocabulary but for a completely different purpose (source window vs destination body);
  - FR-051 reuses the IDF vocabulary but does not modify it.

Hard rule: FR-051 must not mutate any token set, embedding, IDF value, or text field used by any other signal.

## Inputs Required

FR-051 v1 can use only data already available in the pipeline:

- host page `distilled_text` and the insertion point offset — from the host `ContentItem` and the candidate insertion metadata
- destination `distilled_text` — from `ContentRecord.tokens` already loaded per destination
- IDF vocabulary — from FR-011's BM25 vocabulary already computed at pipeline time
- `tokenize_text(...)` — existing normalizer in `text_tokens.py`

Explicitly disallowed FR-051 inputs in v1:

- embedding vectors
- analytics or telemetry data
- reviewer-edited anchors
- any data not already loaded by the pipeline at suggestion time

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `reference_context.enabled`
- `reference_context.ranking_weight`
- `reference_context.window_tokens`
- `reference_context.idf_smoothing`

Defaults:

- `enabled = true`
- `ranking_weight = 0.03`
- `window_tokens = 5`
- `idf_smoothing = 1`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `2 <= window_tokens <= 15`
- `1 <= idf_smoothing <= 10`

### Feature-flag behavior

- `enabled = false`
  - skip context computation entirely
  - store `score_reference_context = 0.5`
  - store `reference_context_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute context score and store diagnostics
  - do not change ranking order

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.reference_context_diagnostics`

Required fields:

- `score_reference_context`
- `reference_context_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_window_too_short`
  - `neutral_destination_empty`
  - `neutral_idf_unavailable`
  - `neutral_processing_error`
- `window_token_count` — number of tokens in the extraction window
- `matched_token_count` — how many window tokens also appear in the destination
- `matched_weight` — sum of IDF weights for matched tokens
- `total_weight` — sum of IDF weights for all window tokens
- `context_ratio` — raw `matched_weight / total_weight`
- `sample_window_tokens` — up to 5 example window tokens with their IDF values for operator review
- `sample_matched_tokens` — up to 5 example matched tokens for operator review
- `window_tokens_setting` — setting value used for this run

Plain-English review helper text should say:

- `Reference context means the words immediately surrounding the proposed link insertion point are topically aligned with the destination page.`
- `A high score means the link sits in a paragraph clause that specifically discusses the destination's topic.`
- `Neutral means the insertion window was too short to compare, the IDF vocabulary was unavailable, or the feature is disabled.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_reference_context: FloatField(default=0.5)`
- `reference_context_diagnostics: JSONField(default=dict, blank=True)`

### Content model

No new `ContentItem` field needed.

Reason:

- reference context is suggestion-time and position-specific (host insertion point x destination), not a stable per-page score;
- the same destination can score differently depending on where on the source page the link is proposed.

### PipelineRun snapshot

Add FR-051 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/reference-context/`
- `PUT /api/settings/reference-context/`

No recalculation endpoint in v1.

Reason:

- FR-051 is position-specific and computed at suggestion time. There is no site-wide pre-computation step to trigger.

### Review / admin / frontend

Add one new review row:

- `Reference Context`

Add one small diagnostics block:

- context ratio
- matched token count vs window token count
- sample window tokens with IDF values (up to 5)
- sample matched tokens (up to 5)
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- window size (tokens) input
- IDF smoothing input

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/reference_context.py` — new service file
- `backend/apps/pipeline/services/ranker.py` — add FR-051 additive hook
- `backend/apps/pipeline/services/pipeline.py` — pass insertion point context to ranker
- `backend/apps/pipeline/services/field_aware_relevance.py` — expose IDF vocabulary for reuse (read-only)
- `backend/apps/pipeline/services/text_tokens.py` — reuse existing `tokenize_text()`
- `backend/apps/suggestions/models.py` — add two new fields
- `backend/apps/suggestions/serializers.py` — expose new fields
- `backend/apps/suggestions/views.py` — snapshot FR-051 settings
- `backend/apps/suggestions/admin.py` — expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/core/views.py` — add settings endpoint
- `backend/apps/api/urls.py` — wire new settings endpoint
- `backend/apps/pipeline/tests.py` — FR-051 unit tests
- `backend/extensions/refcontext.cpp` — C++ extension for batch IDF window scoring
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-051 implementation pass:

- `backend/apps/content/models.py` — no new content fields
- `backend/apps/graph/models.py` — no new graph edges
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`
- `backend/apps/pipeline/services/rare_term_propagation.py`
- `backend/apps/pipeline/services/information_gain.py`

## Test Plan

### 1. IDF-weighted window overlap

- window tokens all appear in destination with high IDF -> score near 1.0
- window tokens none appear in destination -> score = 0.5
- window of only stopwords (low IDF) matching destination produces low context_ratio despite high token overlap
- window of rare terms (high IDF) matching destination produces high context_ratio even with few matched tokens

### 2. Neutral fallback cases

- insertion point at very start of text (fewer than 2 window tokens) -> `score = 0.5`, state `neutral_window_too_short`
- destination token set is empty -> `score = 0.5`, state `neutral_destination_empty`
- IDF vocabulary not loaded -> `score = 0.5`, state `neutral_idf_unavailable`
- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`

### 3. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 4. Bounded score

- score is always in `[0.5, 1.0]` regardless of input
- no pair produces a score below `0.5` or above `1.0`

### 5. Isolation from other signals

- changing `score_semantic` inputs does not affect `score_reference_context`
- changing FR-008 phrase matching does not affect `score_reference_context`
- IDF vocabulary is read-only — FR-051 never modifies it

### 6. Serializer and frontend contract

- `score_reference_context` and `reference_context_diagnostics` appear in suggestion detail API response
- review dialog renders the `Reference Context` row
- settings page loads and saves FR-051 settings

### 7. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-051 settings and algorithm version

### 8. Sample token cap

- `sample_window_tokens` in diagnostics contains at most 5 entries regardless of window size
- `sample_matched_tokens` in diagnostics contains at most 5 entries regardless of match count

## Rollout Plan

### Step 1 — diagnostics only

- implement FR-051 computation with `ranking_weight = 0.0`
- verify context ratios look sensible across a real pipeline run
- confirm IDF reuse from FR-011 works without interference

### Step 2 — operator review

- inspect whether `sample_window_tokens` and `sample_matched_tokens` look like genuine topical context vs noise
- confirm candidates with high context scores have insertion points in topically relevant clauses
- confirm candidates with low context scores have insertion points in off-topic or generic clauses

### Step 3 — optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.02` to `0.04`

## Risk List

- short host sentences may produce windows where N tokens before + N tokens after covers the entire sentence, making FR-051 degenerate to a sentence-level signal similar to `score_keyword` — mitigated by the IDF weighting which still differentiates even in this case;
- IDF values depend on corpus size and may be unstable on very small sites (<100 pages) — mitigated by the `idf_smoothing` parameter;
- the window is token-based, not semantic — it cannot detect paraphrases or synonyms. This is by design: FR-051 is a complementary sparse signal, not a replacement for `score_semantic`;
- future work should not merge this signal with `score_phrase_match` or `score_keyword` — they must remain independent axes.

## Recommended Preset Integration

### `recommended_weights.py` entries (already added — forward-declared)

```python
"reference_context.enabled": "true",
"reference_context.ranking_weight": "0.03",
"reference_context.window_tokens": "5",
"reference_context.idf_smoothing": "1",
```

**Why these values:**

- `enabled = true` — run diagnostics silently from day one so an operator can inspect `sample_window_tokens` before enabling ranking impact.
- `ranking_weight = 0.03` — conservative starting point for an unvalidated micro-context signal. Acts as a light tie-breaker. Raise to `0.05` once a live pipeline run confirms context ratios correlate with editorial quality.
- `window_tokens = 5` — +-5 tokens (10-word window) matches the patent's recommended context size. Large enough to capture clause-level context, small enough to stay narrower than full-sentence signals.
- `idf_smoothing = 1` — standard Laplace smoothing for unseen tokens.

### Migration note

A new data migration is needed to upsert these keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.

### `SETTING_TOOLTIPS` and `UI_TO_PRESET_KEY` entries (already added)

The frontend tooltip dictionary and the preset key map have both been pre-populated for:

- `referenceContext.enabled`
- `referenceContext.ranking_weight`
- `referenceContext.window_tokens`
- `referenceContext.idf_smoothing`

### `ALERT_THRESHOLDS` entries (already added)

- `referenceContext.ranking_weight`: warn above `0.08`, danger above `0.10`
- `referenceContext.window_tokens`: warn above `12`, danger above `15`

## Out Of Scope

- semantic (embedding-based) window comparison
- variable-width windows that expand to clause or sentence boundaries
- multi-insertion-point aggregation for the same destination
- per-field window scoring (title insertion vs body insertion)
- any dependency on analytics or telemetry data
- any modification to stored text, embeddings, or IDF vocabulary
