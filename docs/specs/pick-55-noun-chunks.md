# Pick #55 — Noun-Chunk Anchor Candidates

## Summary
Noun chunks are "base noun phrases" – flat phrases that have a noun as their head. They are excellent candidates for anchor text because they typically represent meaningful entities or concepts. This feature uses spaCy's `noun_chunks` iterator to automatically extract these candidates.

## Academic Source
- **Author**: spaCy (Explosion AI)
- **Title**: spaCy Noun Chunks
- **URL**: https://spacy.io/usage/linguistic-features#noun-chunks
- **Rationale**: Reuses the dependency-parse-based chunker already present in our spaCy model.

## Architecture Lane
- **Logic**: Python (Pipeline Stage: Anchor Extraction)
- **Persistence**: `Sentence` metadata or temporary candidate list.

## Real-World Constraints
- **RAM**: Zero incremental cost (already using spaCy).
- **CPU**: < 5ms per post (traverses the already-built dependency tree).

## Researched Defaults
| Parameter | Default | Source |
|---|---|---|
| `noun_chunks.enabled` | `true` | Recommended preset |

## Benchmark
- `backend/benchmarks/test_bench_pick_55.py`
- Target: < 20ms for a 500-word post.

## Edge Cases
- **Overlapping Chunks**: If a chunk is inside another chunk (rare in spaCy), we prefer the longer one.
- **Stopwords Only**: Chunks consisting only of stopwords must be filtered.

## Diagnostics
- **UI**: Candidate list shown in "Explain" panel (FR-232).
- **Logs**: "Extracted X noun chunks for ContentItem ID Y".

## Completed (2026-04-30)
- [x] Integrated `noun_chunks` extraction into `NLPEnricher.enrich`.
- [x] Wired into `evaluate_phrase_match` via `alternative_anchors` diagnostics.
- [x] Added `phrase_matching.noun_chunk_boost_weight` to `ranker.py` and `recommended_weights.py`.
- [x] Verified performance < 20ms in Docker production environment.

