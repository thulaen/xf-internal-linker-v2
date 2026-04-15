# FR-199 - Content-Spin Detector

## Overview
"Spinning" is the act of taking one article and producing many slightly-reworded copies — synonym substitution, sentence reordering, paragraph swap. Spun pages look unique to a naive duplicate detector but share a high fraction of their `k`-shingles. This signal computes approximate shingle *containment* between every candidate and its nearest neighbour in the corpus; high containment with at least one other page = likely spin. Used as a multiplicative penalty.

## Academic source
**Bendersky, Michael and Gabrilovich, Evgeniy (2011).** "Modeling Forum Discussions and Spam Detection." *Proceedings of the 4th ACM International Conference on Web Search and Data Mining (WSDM 2011)*, pp. 567-576. DOI: `10.1145/1935826.1935854`. The shingle-containment formulation in §3.2 and the spin-vs-paraphrase calibration in §5 form the basis for this signal. Builds on Broder (1997) MinHash for the shingle representation.

## Formula
For each document `d`, build the shingle set `S(d) = { (t_i, t_{i+1}, …, t_{i+k−1}) : i ∈ [1, |d|−k+1] }` with `k = 5`. Containment is asymmetric Jaccard:

```
containment(d, d') = |S(d) ∩ S(d')| / |S(d)|             (Eq. 4, Bendersky & Gabrilovich)
```

The spin score is the maximum containment with any *other* document:
```
spin(d) = max_{d' ≠ d}  containment(d, d')
```

For scalability we use MinHash with `K = 256` permutations (Broder 1997), giving an unbiased estimator:
```
ĉ(d, d') = |{ i : minhash_i(S(d)) = minhash_i(S(d')) ∧ minhash_i(S(d)) ∈ S(d') }| / K
```

Penalty:
```
spin_penalty(d) = max(0, spin(d) − τ) / (1 − τ),   τ = 0.55  (paper §5.3 cut-off)
```

## Starting weight preset
```python
"content_spin.enabled": "true",
"content_spin.ranking_weight": "0.0",
"content_spin.shingle_k": "5",
"content_spin.minhash_K": "256",
"content_spin.tau": "0.55",
"content_spin.lsh_bands": "32",
"content_spin.lsh_rows": "8",
```

## C++ implementation
- File: `backend/extensions/content_spin.cpp`
- Entry: `void compute_spin_scores(const uint64_t* minhashes, int n_docs, int K, int bands, int rows, double* out_spin);`
- Complexity: `O(n_docs · K)` MinHash + `O(n_docs · b)` LSH bucketing where `b = bands`
- Thread-safety: per-document MinHash computation parallelised via OpenMP
- SIMD: AVX2 `_mm256_min_epu32` for MinHash reduction
- Builds against pybind11; reuses MurmurHash3 from FR-014

## Python fallback
`backend/apps/pipeline/services/content_spin.py::compute_spin(...)` — uses `datasketch.MinHashLSH` for ad-hoc analysis.

## Benchmark plan
| Documents | C++ target | Python target |
|---|---|---|
| 1 K (1KB) | < 50 ms | < 1 s |
| 10 K (1KB) | < 500 ms | < 15 s |
| 100 K (1KB) | < 5 s | < 180 s |

## Diagnostics
- Raw `spin(d)` for each doc with the nearest neighbour ID
- `spin_penalty` after threshold
- Histogram of pairwise containment in LSH buckets
- Number of candidate pairs surfaced by LSH per doc
- C++ vs Python badge

## Edge cases & neutral fallback
- Document with < 50 tokens → neutral `0.0`, flag `text_too_short` (shingles unreliable)
- Document is the only one in corpus → `0.0`, flag `singleton_corpus`
- Containment with self excluded by construction
- Two near-identical docs → both get the same `spin(d)` — disambiguation handled by FR-014 clustering
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 50` tokens AND `≥ 10` documents in corpus before the score is trusted; below this returns neutral `0.0`.

## Budget
Disk: <5 MB (MinHash signatures, `256 × 4 bytes × n_docs`)  ·  RAM: <80 MB at 100 K docs

## Scope boundary vs existing signals
FR-199 does NOT duplicate FR-014 near-duplicate clustering — that uses high-Jaccard cut-off (`≥ 0.9`) for full-page duplicates. FR-199 uses *containment* (asymmetric) and lower threshold (`0.55`) to catch *partial* re-wording. It does not overlap with FR-198 keyword stuffing (term-distribution anomaly) or FR-041 originality (provenance, not text overlap).

## Test plan bullets
- unit tests: identical pages (containment = 1.0), disjoint (0.0), 60% overlap (0.6)
- parity test: MinHash estimate within `±0.05` of exact Jaccard at `K = 256`
- regression test: legitimate quote-and-discuss threads (low containment, high overlap by design)
- adversarial test: word-swap spin (replace 30% of nouns) must yield containment `≥ 0.7`
- integration test: ranking unchanged when `ranking_weight = 0.0`
- timing test: 100 K docs within 5 s in C++
