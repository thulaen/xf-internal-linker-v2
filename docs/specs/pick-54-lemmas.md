# Pick #54 — Lemmatization (spaCy)

## Summary
Lemmatization is the process of grouping together the inflected forms of a word so they can be analysed as a single item, identified by the word's lemma, or dictionary form. This feature integrates spaCy's `lemma_` attribute into the pipeline to improve anchor-to-query matching stability.

## Academic Source
- **Author**: spaCy (Explosion AI)
- **Title**: spaCy Lemmatizer Architecture
- **URL**: https://spacy.io/api/lemmatizer
- **Rationale**: Reuses the industry-standard neural lemmatizer already present in our `en_core_web_md` model.

## Architecture Lane
- **Logic**: Python (Pipeline Stage: Parse / NLP Enrichment)
- **Persistence**: `Sentence` metadata or `ContentItem` keywords.

## Real-World Constraints
- **RAM**: Zero incremental cost (already using spaCy).
- **CPU**: negligible overhead during the existing NER/parse pass.

## Researched Defaults
| Parameter | Default | Source |
|---|---|---|
| `lemma.enabled` | `true` | Recommended preset |

## Benchmark
- `backend/benchmarks/test_bench_pick_54.py`
- Target: < 10ms per 1k tokens (added to existing parse pass).

## Edge Cases
- **Proper Nouns**: spaCy sometimes over-lemmatizes names. We must check `token.pos_ == "PROPN"` before applying.
- **Empty Body**: Handled by existing null-check in `text_processor`.

## Diagnostics
- **UI**: None (infrastructure-only).
- **Logs**: "Lemmatization complete for ContentItem ID X".

## Pending
- [ ] Implement `LemmaExtractor` service.
- [ ] Wire into `text_processor` spaCy pipeline.
