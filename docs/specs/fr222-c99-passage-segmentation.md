# FR-222 - C99 Passage Segmentation

## Overview
Choi's C99 algorithm segments a document into topical passages by transforming the inter-sentence similarity matrix into a *rank* matrix (each cell is its rank within a local 11×11 region) and then divisively clustering on rank-sum density. This is more robust to vocabulary-noise than raw cosine similarity (TextTiling, FR-221) and consistently outperforms it on the Choi test set. The signal repurposes C99's segment-boundary confidence as a passage-level *quality* feature: an insertion point inside a tightly-clustered, well-bounded C99 segment is a higher-quality landing zone. Used as a small additive bonus on the candidate's passage-relevance term.

## Academic source
**Choi, Freddy Y. Y. (2000).** "Advances in Domain-Independent Linear Text Segmentation." *Proceedings of the 1st North American Chapter of the Association for Computational Linguistics Conference (NAACL 2000)*, Seattle, USA, pp. 26-33. URL: `https://aclanthology.org/A00-2004/`. Defines the rank-matrix transformation, the divisive-clustering objective `inside − outside` density, and the unsupervised stopping rule used in the formula below.

## Formula
From Choi (2000), §3 (rank-matrix construction) and §4 (divisive clustering):

```
1. Tokenise and stem; build sentence-vectors v_i (token-frequency, stopwords removed).

2. Cosine similarity matrix S of size n × n:
       S[i][j] = (v_i · v_j) / (||v_i|| · ||v_j||)

3. Rank matrix R: replace each S[i][j] with its rank within an 11×11 neighbourhood
   centered at (i, j). Ties broken by row-major order.

       R[i][j] = | { (i', j') ∈ N_{11×11}(i,j) : S[i'][j'] < S[i][j] } |

4. Divisive clustering. For each candidate split point k ∈ [1, n-1]:

       inside_density(k) =
           ( Σ_{i,j ∈ A_k} R[i][j] + Σ_{i,j ∈ B_k} R[i][j] )
           / ( |A_k|² + |B_k|² )

   where A_k = sentences [1..k], B_k = sentences [k+1..n].

   Pick split  k* = argmax_k inside_density(k).

5. Recurse on each half until the gain falls below a stopping threshold:

       gain(k*) = inside_density(k*) − inside_density(no_split)
       stop iff gain(k*) <  μ_gain  +  c · σ_gain        (default c = 1.2)

6. Per-passage signal for an insertion point at sentence index s:

       seg_id(s)            = the C99 segment containing s
       split_confidence(seg) = max( gain at left_split,  gain at right_split )

       signal(s) = clamp( split_confidence(seg(s)) / max_gain_in_doc, 0, 1 )
```

Where:
- `N_{11×11}(i,j)` = 11×11 box centered on `(i,j)`, clipped at matrix edges
- bigger `gain` = sharper boundary
- `signal ∈ [0, 1]` — `1` = insertion point sits in the segment with the strongest boundary contrast

## Starting weight preset
```python
"c99_segmentation.enabled": "true",
"c99_segmentation.ranking_weight": "0.0",
"c99_segmentation.rank_neighbourhood": "11",
"c99_segmentation.stop_threshold_c": "1.2",
"c99_segmentation.min_sentences": "8",
```

## C++ implementation
- File: `backend/extensions/c99_segmentation.cpp`
- Entry: `double c99_split_confidence(const float* sim_matrix, int n, int neighbourhood, double c, int insertion_sentence_idx);`
- Complexity: `O(n²)` for similarity matrix, `O(n² · k²)` for rank matrix (k = neighbourhood), `O(n²)` divisive recursion
- Thread-safety: pure function; matrices passed in as read-only buffers
- SIMD: `_mm256_*` for similarity dot-products and rank-counting reductions
- Builds against pybind11 alongside passage-level extensions (FR-053 family)

## Python fallback
`backend/apps/pipeline/services/c99_segmentation.py::compute_c99_signal(...)` — used when the C++ extension is unavailable; reuses the sentence-vector buffer already built in FR-053.

## Benchmark plan
| Sentences | C++ target | Python target |
|---|---|---|
| 50 | < 1 ms | < 50 ms |
| 200 | < 50 ms | < 1000 ms |
| 1000 | < 500 ms | < 30 000 ms |

## Diagnostics
- Raw `split_confidence` per insertion point in suggestion detail UI
- C99 segment id (1-based) and its bounds (start..end sentence index)
- All detected splits with their gain values
- Stopping-threshold value `μ + c·σ` actually applied
- Heat-map snippet of the rank matrix for the segment

## Edge cases & neutral fallback
- Document below `min_sentences` → neutral `0.5`, flag `below_min_sentences`
- Single segment after recursion (no internal split survived threshold) → neutral `0.5`, flag `single_segment`
- Identical sentences (similarity matrix all-ones) → neutral `0.5`, flag `degenerate_similarity`
- Insertion sentence beyond `n` → segment = last segment, no flag
- NaN / Inf in similarity → cell replaced with `0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 8` sentences before the rank-matrix neighbourhood is meaningful; below this returns neutral `0.5` with flag `below_min_sentences`.

## Budget
Disk: <1 MB  ·  RAM: <50 MB (`n²` similarity + rank matrices, freed after computation; capped at `n = 2000`)

## Scope boundary vs existing signals
FR-222 does NOT overlap with FR-221 (TextTiling) — both are passage-segmentation methods, but C99 uses rank-matrix divisive clustering while TextTiling uses sliding-window depth scores. Operators can run both and let FR-018 auto-tuning pick the higher-performing one for their corpus. It does not overlap with FR-053 (passage-level relevance) which measures *destination match*, not host-passage *boundary quality*.

## Test plan bullets
- unit tests: clean three-topic doc (three segments, signal ≈ 1.0 in each), uniform doc (single segment, neutral)
- parity test: C++ vs Python within `1e-4` on 100 sampled documents (matches Choi's published test set scores)
- adversarial test: 1-sentence doc, all-stopword doc, doc with cyclical topic returns
- threshold-tuning test: changing `c` shifts segment count predictably
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: matches Hearst dataset boundary recall within 5 pp of paper-published numbers
