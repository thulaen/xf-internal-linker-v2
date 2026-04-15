# FR-215 - Schema.org Structured-Data Completeness

## Overview
Pages that ship complete Schema.org / JSON-LD structured data have been editorially curated for search-engine consumption — a strong proxy for content maturity. The signal parses every JSON-LD block and Microdata `itemtype` on the page, classifies each into a Schema.org type `T`, looks up the *required* property set `R(T)` from the official schema definition, and computes per-type completeness as the fraction of required properties actually provided. The page-level score is the mean across detected types. Used as a small additive bonus on destination quality.

## Academic source
**Schema.org Consortium (2011-present).** "Schema.org — A collaborative, community activity with a mission to create, maintain, and promote schemas for structured data on the Internet." Founded 2011 by Google, Microsoft, Yahoo, Yandex; current spec version 28.0 (2024). URL: `https://schema.org/docs/schemas.html`. Defines the Type → required-property mappings this signal evaluates. **US Patent 9,916,304 B2 (Pang et al., assigned to Google, 2018).** "Generating rich content from structured data." Filed 2014-08-12, granted 2018-03-13. URL: `https://patents.google.com/patent/US9916304B2`. Describes scoring structured-data completeness as a quality input for search-result enrichment — the patent basis for treating completeness as a ranker feature.

## Formula
From Schema.org spec + US9916304B2 completeness formulation:

```
For structured-data items D = {d_1, ..., d_k} extracted from the page:

  type(d_i) ∈ Schema.org type vocabulary
  provided(d_i) = { property names actually present on d_i }
  R(type(d_i)) = { required property names per Schema.org spec }

  completeness(d_i) =  | provided(d_i) ∩ R(type(d_i)) |  /  | R(type(d_i)) |

  page_completeness =  ( Σ_{i=1..k} completeness(d_i) ) / max(k, 1)

  signal = page_completeness                if k ≥ min_items
         = 0.5  (neutral)                   if k = 0
```

Where:
- `R(T)` is the canonical required-property set drawn from `https://schema.org/<T>` (e.g. `Article` requires `headline`, `datePublished`, `author`, `image`)
- ties broken by exact lexical match on property name (case-sensitive per spec)
- nested types (e.g. `Article.author = Person`) recurse with the same formula, weighted equally
- `signal ∈ [0, 1]`

## Starting weight preset
```python
"schema_completeness.enabled": "true",
"schema_completeness.ranking_weight": "0.0",
"schema_completeness.min_items": "1",
"schema_completeness.recurse_nested": "true",
"schema_completeness.spec_version": "28.0",
```

## C++ implementation
- File: `backend/extensions/schema_completeness.cpp`
- Entry: `double schema_completeness(const SchemaItem* items, int k, const RequiredPropTable& spec);`
- Complexity: `O(Σ_i |provided(d_i)|)` per page, dominated by hash lookups
- Thread-safety: pure function; `RequiredPropTable` is read-only and shared across threads
- SIMD: not applicable (string-keyed hash lookups)
- Builds against pybind11; required-property table loaded once at extension init

## Python fallback
`backend/apps/pipeline/services/schema_completeness.py::compute_schema_score(...)` — used when the C++ extension is unavailable; reuses `extruct` library output already parsed during FR-091 DOM extraction.

## Benchmark plan
| Items × props | C++ target | Python target |
|---|---|---|
| 1 × 5 | < 0.01 ms | < 0.1 ms |
| 10 × 10 | < 0.1 ms | < 1 ms |
| 50 × 20 | < 0.5 ms | < 10 ms |

## Diagnostics
- Raw `page_completeness` per page in suggestion detail UI
- List of detected types and per-type completeness
- For each item: missing-required-property names
- Whether `min_items` floor triggered neutral fallback
- Spec-version used for the lookup table

## Edge cases & neutral fallback
- Zero structured-data items → neutral `0.5`, flag `no_structured_data`
- Unknown Schema.org type → ignored from numerator and denominator, flag `unknown_type_skipped`
- Malformed JSON-LD → item dropped, flag `malformed_json_ld`
- Empty `R(T)` (rare, e.g. `Thing`) → item contributes `1.0`, flag `no_required_props`
- NaN / Inf → impossible (integer counts), defensive clamp returns `0.5`

## Minimum-data threshold
`≥ 1` parseable structured-data item before the score is trusted; below this returns neutral `0.5` with flag `below_min_items`.

## Budget
Disk: <2 MB (Schema.org required-property lookup table)  ·  RAM: <5 MB (parsed item buffer)

## Scope boundary vs existing signals
FR-215 does NOT overlap with FR-216 (Open Graph completeness) — Schema.org and Open Graph are separate metadata vocabularies serving different consumers (search engines vs social-share previews). It does not overlap with FR-039 (entity salience) which scores entity *frequency*; FR-215 scores metadata *coverage*. The three together form a metadata-quality cluster the auto-tuner can blend.

## Test plan bullets
- unit tests: complete `Article` (1.0), `Article` missing `author` (0.75), no JSON-LD (neutral 0.5)
- parity test: C++ vs Python within `1e-6` over 1000 sampled pages
- adversarial test: malformed JSON-LD, unknown types, deeply-nested items
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: pages with both Microdata and JSON-LD score consistently
- spec-version test: changing `spec_version` updates required-property set as expected
