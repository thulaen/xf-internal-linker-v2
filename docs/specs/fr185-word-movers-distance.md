# FR-185 — Word Mover's Distance (WMD)

## Overview
Word Mover's Distance treats two documents as bags of word-embedding vectors and computes the *minimum cumulative cost* of transforming one bag into the other, where cost is the Euclidean distance between word vectors. It is an instance of the Earth Mover's Distance (Wasserstein-1) on word embeddings, originally shown by Kusner et al. to dominate Bag-of-Words and TF-IDF baselines on document classification. For an internal-linker, WMD provides an *embedding-aware semantic distance* that captures synonyms (e.g., "car" → "automobile" has near-zero cost) without ever sharing a literal token. Complements `fr181-kl-divergence-source-destination` (LM-based) and `fr182-jensen-shannon-divergence` (symmetric LM divergence) by working in continuous embedding space rather than discrete vocabulary space.

## Academic source
Kusner, M. J., Sun, Y., Kolkin, N. I. and Weinberger, K. Q. "From word embeddings to document distances." *Proceedings of the 32nd International Conference on Machine Learning (ICML 2015), PMLR vol 37*, pp. 957–966, 2015. URL: https://proceedings.mlr.press/v37/kusnerb15.html. Underlying transport theory: Rubner, Y., Tomasi, C. and Guibas, L. J. "The Earth Mover's Distance as a metric for image retrieval." *International Journal of Computer Vision* 40(2), 2000. DOI: `10.1023/A:1026543900054`.

## Formula
From Kusner et al. (2015), Section 3.3 — let document `d` have a normalised bag-of-words distribution `n_{d,i} ∈ [0, 1]` over vocabulary terms, and let `c(i, j) = ‖v_i − v_j‖₂` be the Euclidean distance between word embeddings. WMD is the linear-program optimum:

```
WMD(d, d') = min_{T ≥ 0}  Σ_{i, j} T_{ij} · c(i, j)

subject to
  Σ_j T_{ij} = n_{d,  i}        ∀ i ∈ vocab(d)
  Σ_i T_{ij} = n_{d', j}        ∀ j ∈ vocab(d')
  T_{ij} ≥ 0
```

`T_{ij}` is the (fractional) flow from word `i` in `d` to word `j` in `d'`. The constraints state that all of `d`'s mass must leave and all of `d'`'s mass must arrive.

Cheap lower bounds (introduced in the same paper) for retrieval pruning:

```
WCD(d, d') = ‖ Σ_i n_{d,i} · v_i − Σ_j n_{d',j} · v_j ‖₂          (Word Centroid Distance)
RWMD(d, d') = max( Σ_i n_{d,i} · min_j c(i, j),
                   Σ_j n_{d',j} · min_i c(i, j) )                  (Relaxed WMD)
```

Properties: *symmetric* (`WMD(d,d') = WMD(d',d)`), *metric* on probability simplex with embedding ground metric.

## Starting weight preset
```python
"wmd.enabled": "true",
"wmd.ranking_weight": "0.0",
"wmd.embedding_dim": "300",
"wmd.use_relaxed_lower_bound": "true",
"wmd.exact_threshold_top_k": "50",
"wmd.distance_type": "euclidean",
```

## C++ implementation
- File: `backend/extensions/wmd.cpp`
- Entry: `double wmd_exact(const float* embeds_d, const float* mass_d, int n_d, const float* embeds_dp, const float* mass_dp, int n_dp, int dim)`, `double rwmd(...)`
- Complexity: WMD exact = O((n_d + n_dp)³ log(n_d + n_dp)) via network simplex (or Sinkhorn O(n² · iters)); RWMD = O(n_d · n_dp · dim); WCD = O((n_d + n_dp) · dim)
- Thread-safety: pure function; uses thread-local scratch buffers
- Builds via pybind11; embedding dot products via SIMD; network-simplex from third-party `lemon` graph lib

## Python fallback
`backend/apps/pipeline/services/wmd.py::compute_wmd` using `gensim.models.KeyedVectors.wmdistance` for exact, `scipy.optimize.linprog` for parity tests, NumPy for RWMD and WCD.

## Benchmark plan

| Size | n_d, n_dp | C++ exact | Python exact | C++ RWMD | Python RWMD |
|---|---|---|---|---|---|
| Small | 10, 10 | 0.5 ms | 25 ms | 0.05 ms | 1 ms |
| Medium | 100, 100 | 50 ms | 2,800 ms | 1 ms | 22 ms |
| Large | 1,000, 1,000 | 8,500 ms | 380,000 ms | 75 ms | 1,800 ms |

## Diagnostics
- WMD value rendered as "WMD: 0.84 (RWMD lower bound: 0.62)"
- Top-5 word-pair flows `(i, j, T_{ij}, c_{ij})` shown for explainability
- C++/Python badge
- Debug fields: `n_d`, `n_dp`, `embedding_dim`, `used_exact`, `wcd`, `rwmd`, `wmd_exact`, `compute_method` (network_simplex|sinkhorn|relaxed)

## Edge cases & neutral fallback
- Empty document ⇒ neutral 0.5 with fallback flag (no mass to transport)
- Single-token documents ⇒ WMD = `c(i, j)` (single embedding distance)
- OOV tokens (no embedding) ⇒ skip the token; renormalise mass; if all OOV, fallback
- Identical documents ⇒ WMD = 0
- Use RWMD as a *cheap lower bound* for retrieval pruning: only compute exact WMD for top-`k` candidates surviving RWMD
- Stopwords contribute heavily and uninformatively; recommend pre-filtering with `wmd.stopword_removal = true`

## Minimum-data threshold
Need at least 5 in-vocabulary tokens per document and a precomputed embedding matrix; otherwise neutral 0.5.

## Budget
Disk: ~1.2 GB for 300d Word2Vec on 1M-vocab (already paid for FR-007 embeddings) · RAM: same matrix mmap'd; transient cost matrix `O(n_d · n_dp)` per pair

## Scope boundary vs existing signals
Distinct from `fr007-semantic-similarity` (cosine on document embeddings, ignores token-level transport) and `fr181..fr184` (LM/divergence-based, no embedding ground metric). WMD is the only signal that uses the *Wasserstein optimal-transport distance* on word vectors. Pair with FR-007 cosine: cosine for fast first-pass, WMD-RWMD for re-ranking, exact WMD only for the final top-`k`.

## Test plan bullets
- Unit: identical documents ⇒ WMD = 0
- Unit: known small example (3 words each) matches manual LP solution within 1e-4
- Identity: WMD ≥ RWMD ≥ WCD on 100 random pairs (lower-bound chain)
- Symmetry: `WMD(d, d') = WMD(d', d)` within 1e-4
- Parity: C++ exact vs Python `linprog` within 1e-3 on 100 small pairs
- Edge: all-OOV document returns 0.5 with fallback
- Edge: single-token documents return Euclidean embedding distance
- Pruning: RWMD-then-exact reproduces brute-force exact ranking on top-50 retrieval
- Regression: top-50 ranking unchanged when weight = 0.0
