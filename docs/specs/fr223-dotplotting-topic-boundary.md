# FR-223 - Dotplotting Topic-Boundary Density

## Overview
Reynar's dotplotting method visualises topic structure by plotting a self-similarity matrix `M[i][j] = overlap(sentence_i, sentence_j)` and detecting topic boundaries where the diagonal-density drops sharply. It is the third classical unsupervised passage-segmenter alongside TextTiling (FR-221) and C99 (FR-222), and frequently outperforms both on long-form prose with many short topical asides. The signal repurposes diagonal-density at an insertion point as a passage-level *quality* feature: a sentence sitting inside a high-diagonal-density square is inside a coherent topic block. Used as a small additive bonus on the candidate's passage-relevance term.

## Academic source
**Reynar, Jeffrey C. (1998).** "Topic Segmentation: Algorithms and Applications." Ph.D. thesis, University of Pennsylvania, Department of Computer and Information Science. Earlier paper: **Reynar, Jeffrey C. (1994).** "An Automatic Method of Finding Topic Boundaries." *Proceedings of the 32nd Annual Meeting of the Association for Computational Linguistics (ACL 1994)*, pp. 331-333. DOI: `10.3115/981732.981783`. The 1998 SIGIR-published refinement is: **Reynar, Jeffrey C. (1998).** "Topic Segmentation Algorithms and Applications." *Proceedings of SIGIR 1998 Workshop on Topic-based Vector Space Models*. Defines the dot-plot self-similarity matrix and the diagonal-square optimisation criterion used in the formula below.

## Formula
From Reynar (1994/1998), §3 (dot plot) and §4 (region maximisation):

```
1. Tokenise into sentences s_1..s_n (stopwords removed, stemmed).

2. Self-similarity matrix M of size n × n:

     M[i][j] = | tokens(s_i) ∩ tokens(s_j) |
              / sqrt( |tokens(s_i)| · |tokens(s_j)| )       (normalised overlap)

3. The dot plot is the binary indicator B[i][j] = 1 iff M[i][j] ≥ θ (default θ = mean(M)).

4. Region-maximisation objective. A topic block is a square [a..b] × [a..b] along the
   diagonal. Its density is:

     density(a, b) = ( Σ_{i,j ∈ [a..b]} B[i][j] )  /  (b − a + 1)²

5. Greedy boundary detection. Boundary at position p is a local minimum of the
   running diagonal-density curve d(p) = density(p − w, p + w) for window w (default
   w = 5):

     boundary(p) = 1   iff  d(p) < d(p − 1)  ∧  d(p) < d(p + 1)
                          ∧  d(p) < μ_d − c · σ_d           (default c = 0.5)

6. Per-passage signal for an insertion point at sentence index s:

     block(s) = the diagonal block [a..b] containing s
     block_density(s) = density(a, b)

     signal(s) = clamp( block_density(s) / max_block_density_in_doc, 0, 1 )
```

Where:
- bigger `block_density` = denser dot-plot square = more coherent topic block
- `signal ∈ [0, 1]` — `1` = insertion point sits in the most internally-coherent block in the doc

## Starting weight preset
```python
"dotplot_segmentation.enabled": "true",
"dotplot_segmentation.ranking_weight": "0.0",
"dotplot_segmentation.binarize_threshold": "auto",  # mean(M) if "auto"
"dotplot_segmentation.window_w": "5",
"dotplot_segmentation.boundary_c": "0.5",
"dotplot_segmentation.min_sentences": "10",
```

## C++ implementation
- File: `backend/extensions/dotplotting.cpp`
- Entry: `double dotplot_block_density(const float* sim_matrix, int n, double theta, int window_w, double c, int insertion_sentence_idx);`
- Complexity: `O(n²)` for similarity matrix build, `O(n)` for sliding diagonal-density window
- Thread-safety: pure function on read-only similarity buffer
- SIMD: `_mm256_*` for sentence-overlap intersection counting via bitmask
- Builds against pybind11 alongside passage-level extensions (FR-053 family)

## Python fallback
`backend/apps/pipeline/services/dotplotting.py::compute_dotplot_signal(...)` — used when the C++ extension is unavailable; reuses the sentence-token sets already built in FR-053.

## Benchmark plan
| Sentences | C++ target | Python target |
|---|---|---|
| 50 | < 1 ms | < 25 ms |
| 200 | < 25 ms | < 500 ms |
| 1000 | < 250 ms | < 15 000 ms |

## Diagnostics
- Raw `block_density` per insertion point in suggestion detail UI
- Block bounds (start..end sentence index) containing the insertion point
- Detected boundaries with their density-drop magnitude
- Binarisation threshold `θ` actually applied (auto vs configured)
- Sparkline of the running diagonal density `d(p)`

## Edge cases & neutral fallback
- Document below `min_sentences` → neutral `0.5`, flag `below_min_sentences`
- Empty intersection (degenerate stopword-only sentences) → cell `M[i][j] = 0`
- Uniformly-similar document (all `B[i][j] = 1`) → single block covering whole doc, signal `1.0`
- Insertion sentence past `n` → block = final block, no flag
- NaN / Inf in similarity → cell replaced with `0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 10` sentences before the diagonal-density window (`w = 5` on each side) is meaningful; below this returns neutral `0.5` with flag `below_min_sentences`.

## Budget
Disk: <1 MB  ·  RAM: <50 MB (`n²` similarity + binary plot, freed after computation; capped at `n = 2000`)

## Scope boundary vs existing signals
FR-223 does NOT overlap with FR-221 (TextTiling) or FR-222 (C99) — all three are passage-segmentation methods with different mathematical bases (sliding-window cosine, rank-matrix divisive clustering, dot-plot diagonal density respectively). Operators run them in parallel and FR-018 auto-tuning blends or selects. It does not overlap with FR-053 (passage-level relevance) which measures destination match, not host-passage block quality.

## Test plan bullets
- unit tests: clean two-topic doc (two dense diagonal squares), interleaved-topic doc (low density everywhere), single-topic doc (one big square)
- parity test: C++ vs Python within `1e-4` on 100 sampled documents
- adversarial test: doc with all-identical sentences, doc with all-disjoint vocabulary
- threshold-tuning test: changing `c` shifts boundary count predictably
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: matches Choi-corpus boundary precision within 5 pp of Reynar-published numbers
