# Pick #53 — Acronym Detection (Schwartz-Hearst)

## Summary
The Schwartz-Hearst algorithm is a simple, high-precision algorithm for identifying abbreviation definitions in text. It looks for patterns like "Acronym (Long Form)" or "Long Form (Acronym)" and validates them using character-matching rules. This feature builds a per-post and per-corpus acronym dictionary.

## Academic Source
- **Author**: Ariel S. Schwartz and Marti A. Hearst
- **Title**: A simple algorithm for identifying abbreviation definitions in biomedical text.
- **Year**: 2003
- **Conference**: Pacific Symposium on Biocomputing (PSB)
- **DOI**: 10.1142/9789812776303_0042
- **Rationale**: Industry standard for high-precision, low-compute acronym extraction.

## Architecture Lane
- **Logic**: Python (Pipeline Stage: NLP Enrichment)
- **Persistence**: `ContentItem.acronyms` (JSONField / Dict).

## Real-World Constraints
- **RAM**: Trivial (dictionary of strings).
- **CPU**: < 10ms per 500 words.

## Researched Defaults
| Parameter | Default | Source |
|---|---|---|
| `acronyms.enabled` | `true` | Recommended preset |

## Benchmark
- `backend/benchmarks/test_bench_pick_53.py`
- Target: ≥ 95% Precision on standard datasets (e.g., Medstract).

## Edge Cases
- **Nested Parentheses**: e.g. "AI (Artificial Intelligence (ML-based))". Algorithm must handle nesting correctly.
- **Short Acronyms**: Acronyms < 2 chars are usually noise; Schwartz-Hearst suggests a minimum length.

## Diagnostics
- **UI**: Acronym map shown in suggestion-detail sidebar.
- **Logs**: "Detected X acronym pairs for ContentItem Y".

## Pending
- [ ] Implement `SchwartzHearstDetector` service.
- [ ] Wire into `text_processor` pipeline.
- [ ] Add `acronyms` field to `ContentItem` (if not present).
