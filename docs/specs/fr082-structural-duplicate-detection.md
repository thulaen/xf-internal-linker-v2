# FR-082 - Structural Duplicate Detection Score

## Confirmation

- **Backlog confirmed**: `FR-082 - Structural Duplicate Detection Score` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No structural template detection signal exists in the current ranker. The closest signal is `FR-014` (near-duplicate destination clustering), which detects content-level duplicates via embeddings. FR-082 detects structural (HTML template) duplicates via SimHash -- a fundamentally different approach that catches template farms even when content differs.
- **Repo confirmed**: HTML structure data is available during crawl time.

## Source Summary

### Patent: US7734627B1 -- Structural Duplicate Detection (Google)

**Plain-English description of the patent:**

The patent describes using locality-sensitive hashing (SimHash) on document structure (HTML tag sequences, DOM depth histograms) to identify pages generated from the same template. Template-farmed pages may have unique text content but identical page structure -- a sign of automated, low-quality generation.

**What is adapted for this repo:**

- "document structure" maps to the HTML tag sequence and DOM depth histogram of each page;
- SimHash is computed on this structural fingerprint;
- pages that are structurally similar to many others (template farms) are penalized;
- this is distinct from content-level near-duplicate detection (FR-014).

## Plain-English Summary

Simple version first.

Some websites auto-generate hundreds of pages from the same template -- they look identical in structure but have different text plugged in. These template-farmed pages are typically low quality.

FR-082 detects these by fingerprinting the HTML structure of each page. If a page's structure is nearly identical to many other pages (same template), it gets penalized.

This is different from FR-014 (content duplicates) because two pages can have unique text content but identical HTML structure -- FR-014 would miss them, but FR-082 catches them.

## Problem Statement

Today the ranker detects content-level duplicates (FR-014) but not structural template duplication. A template farm with 500 pages that all share the same HTML skeleton but have different text content would pass all current quality checks.

FR-082 closes this gap by detecting structural similarity.

## Goals

FR-082 should:

- add a separate, explainable, bounded structural duplication signal;
- compute SimHash on HTML tag sequences at crawl time;
- penalize pages structurally similar to many others in the corpus;
- keep pages with unique structure unaffected (score 1.0);
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-082 does not:

- modify FR-014 near-duplicate clustering;
- remove or flag pages;
- analyse content quality;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `h(page)` = SimHash of the page's HTML tag sequence (64-bit hash)
- `near_dups(page)` = count of other pages in the corpus where Hamming distance between SimHash values is below `similarity_threshold` (default: hash similarity > 0.90, i.e., fewer than 7 differing bits out of 64)
- `N` = total pages in corpus

**SimHash computation:**

For each page, extract the sequence of HTML tags (e.g., `html body div h1 p a p div footer`), compute n-gram features from this sequence, and apply the SimHash algorithm:

```text
For each n-gram feature f with weight w(f):
  For each bit position i in [0, 63]:
    If bit i of hash(f) is 1: V[i] += w(f)
    Else: V[i] -= w(f)
h(page) = bits where V[i] > 0 set to 1, else 0
```

**Structural uniqueness score:**

```text
dup_ratio = near_dups(page) / N
score_structural_dup = 1 - dup_ratio
```

This maps:

- `near_dups = 0` (unique structure) -> `score = 1.0`
- `near_dups = N/2` (half the corpus shares this template) -> `score = 0.5`
- `near_dups = N` (every page is the same template) -> `score = 0.0`

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_structural_dup
```

**Neutral fallback:**

```text
score_structural_dup = 0.5
```

Used when:

- page HTML is unavailable;
- feature is disabled.

### Ranking hook

```text
score_dup_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += structural_dup.ranking_weight * score_dup_component
```

## Scope Boundary Versus Existing Signals

FR-082 must stay separate from:

- `FR-014` near-duplicate clustering -- detects content duplicates via embeddings, not structural duplicates.
- `FR-054` boilerplate ratio -- measures within-page template-to-content ratio, not cross-page structural similarity.
- `FR-058` n-gram quality -- measures writing quality patterns, not HTML structure.

## Inputs Required

- HTML tag sequences per page -- extracted at crawl time
- SimHash computation -- at index time

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `structural_dup.enabled`
- `structural_dup.ranking_weight`
- `structural_dup.simhash_bits`
- `structural_dup.similarity_threshold`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `simhash_bits = 64`
- `similarity_threshold = 0.90`

## Diagnostics And Explainability Plan

Required fields:

- `score_structural_dup`
- `structural_dup_state` (`computed`, `neutral_feature_disabled`, `neutral_no_html`, `neutral_processing_error`)
- `simhash_value` -- the 64-bit SimHash (hex string)
- `near_duplicate_count` -- pages with similar structure
- `corpus_page_count` -- total pages for normalization
- `dup_ratio` -- raw ratio

Plain-English review helper text should say:

- `Structural duplicate detection measures whether this page's HTML structure is shared by many other pages (template farm indicator).`
- `A high score means the page has a unique structure. A low score means many pages share the same template.`

## Storage / Model / API Impact

### Content model

Add:

- `score_structural_dup: FloatField(default=0.5)`
- `structural_dup_diagnostics: JSONField(default=dict, blank=True)`
- `simhash_structural: BigIntegerField(null=True)` -- stored at crawl time for comparison

### Backend API

Add:

- `GET /api/settings/structural-dup/`
- `PUT /api/settings/structural-dup/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"structural_dup.enabled": "true",
"structural_dup.ranking_weight": "0.02",
"structural_dup.simhash_bits": "64",
"structural_dup.similarity_threshold": "0.90",
```
