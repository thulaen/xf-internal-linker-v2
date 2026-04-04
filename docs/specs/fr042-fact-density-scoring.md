# FR-042 - Fact Density Scoring

## Confirmation

- `FR-042` is a new backlog item being added to `FEATURE-REQUESTS.md` in this session.
- Repo confirmed:
  - no fact-density or document-informativeness signal exists in the current ranker;
  - the closest existing signals are topical relevance and later content-quality ideas such as `FR-040`, but none estimate how many factual propositions a page contains relative to its length;
  - `ContentItem.distilled_text` and `Post.clean_text` already provide plain text suitable for deterministic text scanning.

## Current Repo Map

### Existing nearby signals

- `score_semantic`, `score_keyword`, `score_field_aware_relevance`
  - all measure topical fit;
  - none measure how information-dense the destination itself is.

- `FR-024` engagement signal
  - measures whether readers stay on a page;
  - it does not explain whether the page is dense with concrete information.

- `FR-040` multimedia boost
  - measures content richness in images/video;
  - it does not measure factual density in text.

## Source Summary

### Paper: "Using Factual Density to Measure Informativeness of Web Documents" (NODALIDA 2013)

Plain-English read:

- factual density is the number of facts contained in a document, normalized by its length;
- the paper uses Open Information Extraction (Open IE) tuples as approximate facts;
- the authors report meaningful correlation between factual density and human judgments of informativeness on web documents.

Repo-safe takeaway:

- a useful document is often one that packs more factual propositions into less text;
- exact Open IE is not required to reuse the core idea;
- the reusable math is "factual propositions per unit length", not a specific NLP package.

### Patent: US9286379B2 - Document quality measurement

Plain-English read:

- the patent describes document quality models built from document attributes;
- it explicitly treats quality assessment as a distinct classification problem rather than just topical relevance;
- content, source, keywords, and other document features can all contribute to quality ranking.

Repo-safe takeaway:

- fact density belongs in the repo as a separate quality-like signal;
- it should not be hidden inside topical relevance or authority scores.

## Plain-English Summary

Simple version first.

Some pages are mostly useful facts.
Some pages are mostly filler.

FR-042 tries to reward pages that say more real, concrete things in fewer words.

Examples of "fact-like" content:

- dates
- quantities
- product specs
- named things tied together by a relation
- clear attribute/value statements

Examples of low-density filler:

- generic sales fluff
- vague claims with no specifics
- repeated slogans
- padding sentences that do not add new information

## Problem Statement

Today the ranker can find relevant pages, but it cannot distinguish between:

- a relevant destination that contains many concrete, useful facts; and
- a relevant destination that contains mostly vague filler or marketing-style padding.

FR-042 adds a bounded informativeness signal so fact-rich pages can receive a modest quality boost.

## Goals

FR-042 should:

- add a separate, explainable fact-density signal;
- estimate factual proposition density using deterministic text patterns;
- normalize the estimate by document length;
- penalize obvious filler-heavy pages without needing a full truth-verification system;
- stay neutral for short or underspecified pages;
- fit the repo without requiring a heavy NLP stack in v1.

## Non-Goals

FR-042 does not:

- verify whether each extracted fact is objectively true;
- perform full dependency parsing or heavy Open IE in v1;
- replace relevance, authority, or engagement signals;
- rewrite content or moderate pages;
- use user analytics or reviewer feedback.

## Math-Fidelity Note

### Input text

Prefer:

- `Post.clean_text` when available;
- otherwise `ContentItem.distilled_text`.

### Step 1 - sentence splitting

Use existing sentence rows when available.
Otherwise split plain text into sentences with a lightweight punctuation-based fallback.

Let:

- `word_count` = document word count
- `sentences` = list of destination sentences

### Step 2 - extract deterministic fact-like propositions

Approximate a fact-like proposition using simple relation patterns.

A sentence contributes one factual proposition when all of the following hold:

1. it has at least `min_sentence_tokens` non-stopword tokens;
2. it contains a relation marker from a curated whitelist such as:
   - `is`, `was`, `were`, `has`, `have`, `includes`, `contains`, `supports`, `costs`, `measures`, `offers`, `released`, `founded`, `located`, `requires`
3. it contains at least one concrete anchor, such as:
   - a number;
   - a date-like token;
   - a measurement unit;
   - a model/version token;
   - a proper-name-like token or title token match.

Optional second proposition:

- if the same sentence contains a colon-based attribute/value form such as `Weight: 1.2 kg`, count one additional proposition up to a per-sentence cap.

### Step 3 - filler ratio

Mark a sentence as filler-like when it matches any of:

- fewer than `min_sentence_tokens` content tokens;
- repeated sales or CTA phrases from a curated small list;
- exclamation-heavy promotional phrasing;
- high stopword ratio with no concrete anchor.

Then:

```text
filler_ratio = filler_sentence_count / max(total_sentence_count, 1)
```

### Step 4 - density score

Let:

- `fact_count` = extracted factual proposition count

Raw density per 100 words:

```text
fact_density_raw = 100 * fact_count / max(word_count, 1)
```

Apply filler penalty:

```text
effective_density = fact_density_raw * (1 - filler_penalty_weight * filler_ratio)
```

Recommended default:

- `filler_penalty_weight = 0.50`

Normalize:

```text
density_norm = min(1.0, effective_density / density_cap_per_100_words)
```

Recommended default:

- `density_cap_per_100_words = 6.0`

Bounded score:

```text
score_fact_density = 0.5 + 0.5 * density_norm
```

Neutral fallback:

```text
score_fact_density = 0.5
```

Used when:

- feature disabled;
- `word_count < min_word_count`;
- no reliable plain text is available.

### Ranking hook

```text
score_fact_density_component =
  max(0.0, min(1.0, 2.0 * (score_fact_density - 0.5)))
```

```text
score_final += fact_density.ranking_weight * score_fact_density_component
```

Default:

- `ranking_weight = 0.0`

## Scope Boundary Versus Existing Signals

FR-042 must stay separate from:

- `FR-011` field-aware relevance
  - FR-011 measures where matching terms appear;
  - FR-042 measures how information-dense the destination text itself is.

- `FR-024` engagement signal
  - FR-024 measures reader behavior;
  - FR-042 measures textual informativeness.

- `FR-040` multimedia boost
  - FR-040 measures rich media quality;
  - FR-042 measures textual proposition density.

Hard rule:

- `FR-042` must not mutate `distilled_text`, `Post.clean_text`, embeddings, or other feature caches.

## Inputs Required

FR-042 v1 can use:

- `Post.clean_text`
- `ContentItem.distilled_text`
- existing sentence rows when already available
- title tokens for light proper-name anchoring

Explicitly disallowed in v1:

- external fact databases;
- web browsing at scoring time;
- full NER / dependency parsing libraries unless already added in a later dedicated FR;
- GA4 / Matomo / GSC signals.

## Data Model Plan

Add to `ContentItem`:

- `fact_density_score`

Add to `Suggestion`:

- `score_fact_density`
- `fact_density_diagnostics`

Persist destination-level fact density on the content item so the main ranker reads a cached float rather than rescanning text for every suggestion.

## Settings And Feature-Flag Plan

Recommended keys:

- `fact_density.enabled`
- `fact_density.ranking_weight`
- `fact_density.min_word_count`
- `fact_density.density_cap_per_100_words`
- `fact_density.filler_penalty_weight`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `min_word_count = 120`
- `density_cap_per_100_words = 6.0`
- `filler_penalty_weight = 0.50`

## Diagnostics And Explainability Plan

Diagnostics should include:

- `word_count`
- `sentence_count`
- `fact_count`
- `filler_sentence_count`
- `filler_ratio`
- `fact_density_raw`
- `effective_density`
- `sample_fact_sentences` (cap 3)
- `fallback_state`

Plain-English helper text:

- "Fact density rewards destination pages that pack more concrete information into fewer words."

## Native Performance Plan

This is a later ranking-affecting FR, so it must plan a native fast path.

### C++ default path

Add a native document-scan kernel that counts factual-pattern hits and filler-pattern hits across large content batches.

Suggested file:

- `backend/extensions/factdensity.cpp`

### Python fallback

Add:

- `backend/apps/pipeline/services/fact_density.py`

The Python and C++ paths must produce the same bounded scores for the same document text.

### Visibility requirement

Expose:

- native enabled / fallback enabled;
- why fallback is active;
- whether native batch recomputation is materially faster.

## Backend Touch Points

- `backend/apps/content/models.py`
- `backend/apps/suggestions/models.py`
- `backend/apps/core/views.py`
- `backend/apps/pipeline/services/fact_density.py`
- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/tasks.py`
- `backend/extensions/factdensity.cpp`

## Verification Plan

Later implementation must verify at least:

1. spec-heavy pages outrank fluffy pages when other signals are equal;
2. short pages stay neutral;
3. obvious filler-heavy text receives a lower effective density than equivalent fact-heavy text of similar length;
4. `ranking_weight = 0.0` leaves ranking unchanged;
5. C++ and Python paths produce identical scores;
6. diagnostics explain why a page scored high, low, or neutral.
