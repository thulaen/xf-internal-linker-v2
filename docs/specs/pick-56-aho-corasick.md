# Pick #56 — Aho-Corasick Multi-Pattern Matcher

## Summary
The Aho-Corasick algorithm is a string-searching algorithm that locates elements of a finite set of strings (the "dictionary") within an input text simultaneously. It is much more efficient than looping over thousands of regex patterns. This feature integrates `pyahocorasick` to speed up anchor-phrase scanning in the pipeline.

## Academic Source
- **Author**: Alfred V. Aho and Margaret J. Corasick
- **Title**: Efficient Bibliographic Search: A Long-lived Pattern Matching Algorithm
- **Year**: 1975
- **Journal**: Communications of the ACM
- **DOI**: 10.1145/360827.360855
- **Rationale**: The gold standard for multi-pattern search in sub-linear time O(n + m + k).

## Architecture Lane
- **Logic**: Python wrapping a C library (Pipeline Stage: Stage 2 Scanning)
- **Library**: `pyahocorasick==2.1.0`

## Real-World Constraints
- **RAM**: The trie structure consumes memory proportional to the anchor vocabulary size (~2-5 MB for 10k anchors).
- **CPU**: Substantial speedup over regex (target ≥ 10x for vocab sizes > 1000).

## Researched Defaults
| Parameter | Default | Source |
|---|---|---|
| `aho_corasick.enabled` | `true` | Recommended preset |

## Benchmark
- `backend/benchmarks/test_bench_pick_56.py`
- Target: < 5ms for 5k tokens vs 10k patterns.

## Edge Cases
- **Overlapping Matches**: Aho-Corasick finds all overlaps. We must apply a "longest-match-first" or "non-overlapping" filter to stay link-policy compliant.
- **Case Sensitivity**: The trie must be built in a case-folded manner if case-insensitive matching is desired.

## Diagnostics
- **UI**: Speedup visible on `/performance` dashboard.
- **Logs**: "Aho-Corasick trie built with X patterns in Y ms".

## Pending
- [ ] Implement `AhoCorasickScanner` service.
- [ ] Replace existing regex loops in `stage2_ranker`.
