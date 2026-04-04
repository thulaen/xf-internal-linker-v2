# FR-041 - Originality Provenance Scoring

## Confirmation

- `FR-041` is a new backlog item being added to `FEATURE-REQUESTS.md` in this session.
- Repo confirmed:
  - no originality-provenance signal exists in the current ranker;
  - `FR-014` clusters semantically near-duplicate destinations, but it does not identify which member of a similar-content family appeared first or should receive "historical authority";
  - `FR-007` tracks link history, not content-origin history;
  - `ContentItem.distilled_text`, `ContentItem.title`, `ContentItem.url`, and `ContentItem.content_hash` already exist;
  - `ContentItem` does not currently store the source-system publication timestamp, so this FR introduces one.

## Current Repo Map

### Existing nearby signals and models

- `backend/apps/content/models.py`
  - `ContentItem` stores destination-level text and metadata.
  - `Post.clean_text` stores plain text for XenForo-backed items.

- `backend/apps/pipeline/services/ranker.py`
  - `weighted_authority`, `link_freshness`, `phrase_matching`, `learned_anchor`, `rare_term_propagation`, `field_aware_relevance`, `click_distance`, and later rerankers all exist.
  - none of them answer the question: "among similar pages, which page appears to be the original source on this site?"

- `FR-014`
  - `ContentCluster` groups semantically similar destinations and helps suppress duplicates in the final slate.
  - that grouping is for duplicate suppression, not origin attribution.

### Gap this FR closes

The repo can currently detect that two pages are similar, but it cannot tell whether one page is the earlier, source-like, historically primary version and the other is a later derivative, repost, archive copy, or lower-authority restatement.

## Source Summary

### Patent: US8707459B2 - Determination of originality of content

Plain-English read:

- the patent compares matching content objects;
- it computes an originality score across those matching objects;
- the object with the highest originality score is designated as the original candidate;
- when scores are close, the earliest time of first appearance can break ties.

Repo-safe takeaway:

- build groups of similar pages;
- score which member of the group looks most "source-like";
- prefer the earliest first appearance when other factors are otherwise similar.

### Near-duplicate math lineage: Broder-style shingling / resemblance / containment

Near-duplicate web-document work commonly models similarity using word shingles and set overlap measures:

- resemblance: how much two pages overlap overall;
- containment: how much one page is contained inside another.

Repo-safe takeaway:

- provenance should not rely only on semantic embeddings;
- lexical shingles are better for identifying copies, partial reposts, and "mostly the same page with minor edits";
- containment is especially useful because a derivative page may mostly contain the original page plus extra boilerplate.

## Plain-English Summary

Simple version first.

If two pages on the site are very similar, the earlier and more source-like one should get extra credit.

That page has "historical authority":

- it likely introduced the topic first;
- later copies or light rewrites should not outrank it just because they are newer, longer, or happened to pick up more generic relevance signals.

FR-041 adds a separate signal that asks:

- is this destination part of a near-copy family?
- if yes, does it look like the original member of that family?

## Problem Statement

Today the ranker can reward authority, freshness, structure, and topical match. But it cannot reward original-on-site authorship.

That means two similar pages can be treated as equally strong destinations even when one page is clearly the earlier, canonical, historically primary write-up and the other is a later copy, summary, archive mirror, or lightly edited repost.

FR-041 adds a bounded provenance signal so original destination pages can receive a modest historical-authority boost.

## Goals

FR-041 should:

- add a separate, explainable originality-provenance signal;
- identify lexical near-copy families using shingled text overlap;
- assign higher scores to the earliest and most source-like member of a family;
- keep pages with no meaningful near-copy family neutral at `0.5`;
- remain separate from `FR-014` clustering and `FR-007` freshness;
- fit the current Django + PostgreSQL + Celery + Angular architecture.

## Non-Goals

FR-041 does not:

- try to determine legal copyright ownership;
- crawl the public web outside the local site corpus in v1;
- replace `FR-014` semantic clustering;
- use external link data, manual legal disputes, or DMCA workflows;
- rewrite any destination text, embedding, or existing duplicate-cluster assignment;
- auto-hide or auto-delete derivative pages.

## Data Model Change

### New field on `ContentItem`

Add:

```python
source_published_at = models.DateTimeField(
    null=True,
    blank=True,
    help_text="Publication timestamp from the source platform when available.",
)
```

### New provenance score field

Add:

```python
originality_provenance_score = models.FloatField(
    default=0.5,
    db_index=True,
    help_text="Historical-authority score based on originality provenance among near-copy families.",
)
```

### New suggestion fields

Add to `Suggestion`:

- `score_originality_provenance`
- `originality_provenance_diagnostics`

### Optional explicit cluster model

Add separate provenance storage rather than reusing `ContentCluster`:

- `ContentProvenanceCluster`
- `ContentProvenanceMembership`

Hard rule:

- do not store provenance membership in `FR-014`'s `ContentCluster`;
- provenance clusters are lexical-copy families;
- `FR-014` clusters remain semantic redundancy groups.

## Math-Fidelity Note

### Step 1 - build shingle sets

For each content item with enough text:

- prefer `Post.clean_text` when available;
- otherwise fall back to `ContentItem.distilled_text`.

Normalize text with the repo's existing token normalization rules and build `k`-word shingles.

Recommended default:

- `k = 5`

Let:

- `A` = shingle set for page A
- `B` = shingle set for page B

### Step 2 - pairwise similarity measures

Use both resemblance and containment:

```text
resemblance(A, B) = |A ∩ B| / max(|A ∪ B|, 1)
```

```text
containment(A in B) = |A ∩ B| / max(|A|, 1)
```

Rationale:

- resemblance catches near duplicates of similar size;
- containment catches a smaller original page that is largely embedded inside a longer derivative page.

### Step 3 - provenance-family membership

Two pages belong to the same provenance family when either threshold is met:

```text
resemblance(A, B) >= min_resemblance
or
max(containment(A in B), containment(B in A)) >= min_containment
```

Recommended defaults:

- `min_resemblance = 0.55`
- `min_containment = 0.80`

### Step 4 - rank members inside one family

For each family:

1. sort by `source_published_at` ascending when available;
2. if missing, fall back to `ContentItem.created_at`;
3. compute corroboration from peer containment.

Let:

- `rank_first_seen` = 1 for earliest member, 0 for latest member, linearly scaled inside the family;
- `peer_containment_support(i)` = average containment of other family members inside page `i`;
- `url_canonical_bonus(i)` = 1.0 when page `i` has the shortest canonical URL path in the family, else 0.0.

Then:

```text
provenance_strength(i) =
    0.70 * rank_first_seen(i)
  + 0.20 * peer_containment_support(i)
  + 0.10 * url_canonical_bonus(i)
```

Clamp to `[0, 1]`.

### Step 5 - bounded destination score

If a page has no family peers above threshold:

```text
originality_provenance_score = 0.5
```

Otherwise:

```text
originality_provenance_score = 0.5 + 0.5 * provenance_strength
```

Interpretation:

- `0.5` = neutral, no meaningful evidence either way;
- `1.0` = strongest candidate for being the historical origin page in its family.

### Ranking hook

Use the standard centered additive pattern:

```text
score_originality_provenance_component =
  max(0.0, min(1.0, 2.0 * (score_originality_provenance - 0.5)))
```

```text
score_final += originality_provenance.ranking_weight * score_originality_provenance_component
```

Default:

- `ranking_weight = 0.0`

Diagnostics run silently until the operator validates the signal.

## Scope Boundary Versus Existing Signals

FR-041 must stay separate from:

- `FR-007` link freshness
  - FR-007 asks whether links to a destination are historically fresh or established;
  - FR-041 asks whether the destination itself appears to be the original member of a near-copy family.

- `FR-014` semantic clustering
  - FR-014 groups semantically redundant destinations for slate suppression;
  - FR-041 groups lexical near-copies for origin attribution.

- `FR-006` weighted authority
  - FR-006 measures graph authority;
  - FR-041 measures historical originality within similar content families.

Hard rule:

- `FR-041` must not mutate `ContentCluster`, `march_2026_pagerank_score`, embeddings, or text fields used by other signals.

## Inputs Required

FR-041 v1 can use:

- `ContentItem.title`
- `ContentItem.distilled_text`
- `Post.clean_text` when present
- `ContentItem.url`
- `ContentItem.created_at`
- new `ContentItem.source_published_at`

Explicitly disallowed in v1:

- external web-crawl timestamps;
- Search Console / GA4 / Matomo behavior data;
- manual reviewer feedback;
- FR-014 cluster IDs as provenance truth.

## Settings And Feature-Flag Plan

Persist via `AppSetting`.

Recommended keys:

- `originality_provenance.enabled`
- `originality_provenance.ranking_weight`
- `originality_provenance.shingle_size`
- `originality_provenance.min_resemblance`
- `originality_provenance.min_containment`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `shingle_size = 5`
- `min_resemblance = 0.55`
- `min_containment = 0.80`

## Diagnostics And Explainability Plan

Suggestion-level diagnostics should include:

- `family_size`
- `first_seen_timestamp_used`
- `first_seen_rank`
- `peer_containment_support`
- `url_canonical_bonus`
- `family_leader_content_item_id`
- `fallback_state`

Plain-English review helper text:

- "Originality provenance rewards destination pages that look like the earliest source version among very similar pages on this site."

## Native Performance Plan

This is a later ranking-affecting FR, so it must plan a native fast path.

### C++ default path

Add a native shingle-overlap kernel that computes resemblance and containment for candidate page pairs during provenance-family recomputation.

Suggested file:

- `backend/extensions/provenance.cpp`

### Python fallback

Add:

- `backend/apps/pipeline/services/originality_provenance.py`

The Python implementation must produce the same family membership and bounded scores as the C++ path.

### Visibility requirement

Expose operator-facing status:

- native path active / fallback active;
- why fallback is being used;
- whether the native pass produced material speedup during recomputation.

## Backend Touch Points

- `backend/apps/content/models.py`
- `backend/apps/content/admin.py`
- `backend/apps/suggestions/models.py`
- `backend/apps/suggestions/serializers.py`
- `backend/apps/core/views.py`
- `backend/apps/pipeline/services/originality_provenance.py`
- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/tasks.py`
- `backend/extensions/provenance.cpp`

## Verification Plan

Later implementation must verify at least:

1. identical pages join the same provenance family;
2. shorter originals contained inside longer reposts are still grouped correctly;
3. earliest `source_published_at` wins ties unless corroboration strongly differs;
4. singletons stay neutral at `0.5`;
5. `ranking_weight = 0.0` leaves ranking order unchanged;
6. C++ and Python paths produce identical family assignments and scores;
7. diagnostics and native-status messaging appear in review/settings/diagnostics UI.
