# FR-221 - Passage TextTiling Boundary Strength

## Overview
TextTiling segments a long document into sub-topical "tiles" by sliding a fixed-width window across the body, computing lexical similarity between adjacent windows, and identifying valleys in the similarity curve as topic boundaries. This signal repurposes Hearst's depth-score as a passage-level *quality* feature: a candidate insertion-point sentence whose surrounding context sits inside a strong, well-bounded TextTile is a higher-quality landing zone than one that straddles a noisy topic transition. Used as a small additive bonus on the candidate's passage-relevance term.

## Academic source
**Hearst, Marti A. (1997).** "TextTiling: Segmenting Text into Multi-paragraph Subtopic Passages." *Computational Linguistics*, vol. 23, no. 1, pp. 33-64. DOI: `10.1162/089120197761379977`. Defines the block-comparison similarity score, the depth-score formulation `(y_{i-1} − y_i) + (y_{i+1} − y_i)`, and the `μ − c·σ` boundary threshold used in the formula below.

## Formula
From Hearst (1997), §3.1 (block comparison) and §3.2 (depth scoring):

```
1. Tokenise the document into pseudo-sentences of length w (default w = 20 tokens).
2. For each gap g_i between adjacent blocks B_i and B_{i+1}, compute lexical similarity:

     y_i  =  ( Σ_t  count_t(B_i) · count_t(B_{i+1}) )
              / sqrt( Σ_t count_t(B_i)²  ·  Σ_t count_t(B_{i+1})² )

   (cosine on bag-of-tokens, stopwords removed, stemmed)

3. Smooth the similarity sequence {y_i} with a moving-average window of size s (default s = 2).

4. Depth score at gap i:

     depth(i)  =  ( y_{i-1} − y_i ) + ( y_{i+1} − y_i )

5. Boundary if depth(i) exceeds threshold:

     threshold  =  μ_depth  −  c · σ_depth      (default c = 0.5)
     boundary(i) = 1   iff  depth(i) > threshold,  else 0

6. Per-passage signal for an insertion point at sentence index s:

     d_left  = nearest_boundary_distance_left(s)        (in sentences)
     d_right = nearest_boundary_distance_right(s)
     tile_strength(s) = max( depth(left_boundary), depth(right_boundary) )

     signal(s) = clamp( tile_strength(s) / max_observed_depth_in_doc, 0, 1 )
```

Where:
- `count_t(B)` = frequency of token `t` in block `B`
- bigger `depth(i)` = deeper valley = stronger boundary
- `signal ∈ [0, 1]` — `1` = insertion point sits inside the most strongly-bounded tile in the doc

## Starting weight preset
```python
"texttiling.enabled": "true",
"texttiling.ranking_weight": "0.0",
"texttiling.block_size_tokens": "20",
"texttiling.smoothing_window": "2",
"texttiling.threshold_c": "0.5",
"texttiling.min_blocks": "6",
```

## C++ implementation
- File: `backend/extensions/texttiling.cpp`
- Entry: `double tile_strength(const uint32_t* token_ids, int n_tokens, int block_size, int smooth_w, double c, int insertion_token_idx);`
- Complexity: `O(n_tokens · vocab_per_block)` for similarity sequence, `O(n_blocks)` for depth and boundary scan
- Thread-safety: pure function on token-id buffer
- SIMD: `_mm256_*` for the cosine numerator/denominator dot-product accumulation
- Builds against pybind11 alongside passage-level extensions (FR-053 family)

## Python fallback
`backend/apps/pipeline/services/texttiling.py::compute_tile_strength(...)` — used when the C++ extension is unavailable; reuses the tokenised body already computed in FR-053 passage extraction.

## Benchmark plan
| Tokens | C++ target | Python target |
|---|---|---|
| 500 | < 0.5 ms | < 5 ms |
| 5 000 | < 5 ms | < 50 ms |
| 50 000 | < 50 ms | < 500 ms |

## Diagnostics
- Raw `tile_strength` per insertion-point in suggestion detail UI
- Smoothed similarity sequence and depth-score plot snippet
- Detected boundary positions (sentence indices)
- Tile in which the insertion point sits (bounds + token-length)
- Threshold value `μ − c·σ` actually applied

## Edge cases & neutral fallback
- Document below `min_blocks` blocks → neutral `0.5`, flag `below_min_blocks`
- Uniformly-similar document (depth variance ≈ 0) → neutral `0.5`, flag `flat_similarity`
- Insertion point past the last block → tile = final block, no flag
- Zero-token document → neutral `0.5`, flag `empty_doc`
- NaN / Inf depth → neutral `0.5`, flag `nan_clamped`

## Minimum-data threshold
`≥ 6` blocks (≈ 120 tokens at default block size) before depth statistics are meaningful; below this returns neutral `0.5` with flag `below_min_blocks`.

## Budget
Disk: <1 MB  ·  RAM: <10 MB (per-document block-similarity buffer, freed after computation)

## Scope boundary vs existing signals
FR-221 does NOT overlap with FR-053 (passage-level relevance) — that signal scores topical match between insertion-passage and destination; FR-221 scores the *bounding strength* of the host passage independent of the destination. It does not overlap with FR-098 (dominant-passage centrality) which scores positional dominance. FR-221, FR-222, FR-223, FR-224 are alternative segmentation algorithms — the auto-tuner can pick the best-performing one or blend them.

## Test plan bullets
- unit tests: clean two-topic doc (one strong boundary, signal ≈ 1.0 at both halves), uniform doc (neutral 0.5)
- parity test: C++ vs Python within `1e-4` over 100 sampled documents
- adversarial test: very short doc (< min_blocks), all-stopword doc, single-paragraph doc
- threshold-tuning test: changing `c` shifts boundary count predictably
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: insertion point in mid-tile vs near-boundary score consistently
