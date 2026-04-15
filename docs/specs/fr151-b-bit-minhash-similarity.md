# FR-151 — b-Bit MinHash Set Similarity

## Overview
Standard MinHash compares two sets by storing `k` 32- or 64-bit hash signatures per set; two pages with k=128 cost 1 KB just for the sketch. b-Bit MinHash retains only the lowest `b` bits (typically `b=1` or `b=2`) of each signature, cutting storage by 16–64× while losing almost no accuracy at the similarity ranges that matter for near-duplicate detection (Jaccard 0.4–1.0). FR-151 complements FR-014 (near-duplicate destination clustering) and FR-082 (structural duplicate detection) by giving a *low-RAM* signature suitable for storing on every page in the corpus, enabling fast all-pairs duplicate scans.

## Academic source
Li, P. and König, A. C. "b-Bit Minwise Hashing." *Proceedings of the 19th International Conference on World Wide Web (WWW '10)*, pp. 671–680, 2010. DOI: 10.1145/1772690.1772759. Extended journal version: Li, P. and König, A. C. "Theory and applications of b-bit minwise hashing." *Communications of the ACM*, 54(8), pp. 101–109, 2011. DOI: 10.1145/1978542.1978566. COLT 2010 talk also available.

## Formula
For two sets `S_1, S_2` with Jaccard similarity `R = |S_1 ∩ S_2| / |S_1 ∪ S_2|`, the standard MinHash collision probability is `Pr[ minhash(S_1) = minhash(S_2) ] = R`. With b-Bit MinHash, only the lowest `b` bits are stored, so collisions occur both from true matches and from `b`-bit aliasing:

```
P_b = Pr[ low_b(minhash(S_1)) = low_b(minhash(S_2)) ]
    = R + (1 − R) · 2^{−b}    (for two specific sets, ignoring DC term)
```

For uniform random hash, the corrected collision probability accounts for the proportion of zero-collision contributions from each set's elements:

```
P_b = C_{1,b} + (1 − C_{2,b}) · R
```

where the correction constants depend on set sizes `f_1 = |S_1|`, `f_2 = |S_2|`, and the universe size `D`:

```
r_1 = f_1 / D
r_2 = f_2 / D
A_b(r) = r · (1 − r)^{2^b − 1} / (1 − (1 − r)^{2^b})
C_{1,b} = A_{1,b} · r_2 / (r_1 + r_2) + A_{2,b} · r_1 / (r_1 + r_2)
C_{2,b} = A_{1,b} · r_1 / (r_1 + r_2) + A_{2,b} · r_2 / (r_1 + r_2)
```

**Estimator:** with `k` MinHash permutations, count matches `M = Σ_{i=1..k} 𝟙[ low_b(h_i(S_1)) = low_b(h_i(S_2)) ]`. Then

```
R̂ = ( M/k − C_{1,b} ) / ( 1 − C_{2,b} )
```

Variance: `Var(R̂) = (P_b · (1 − P_b)) / (k · (1 − C_{2,b})²)`.

For `b=1`, `k=512` gives ~99% memory reduction vs `k=512, b=64` standard MinHash, while keeping similar variance for `R ≥ 0.5`.

## Starting weight preset
```python
"b_bit_minhash.enabled": "true",
"b_bit_minhash.ranking_weight": "0.0",
"b_bit_minhash.b_bits_per_signature": "1",
"b_bit_minhash.k_permutations": "512",
"b_bit_minhash.universe_size_D": "auto",
"b_bit_minhash.shingle_size": "5",
```

## C++ implementation
- File: `backend/extensions/b_bit_minhash.cpp`
- Entry: `void bbm_signature(uint8_t* sig, const uint64_t* shingles, int n_shingles, int k, int b)`, `double bbm_similarity(const uint8_t* sig1, const uint8_t* sig2, int k, int b, double r1, double r2)`
- Complexity: O(n_shingles · k) for signature generation; O(k) for similarity. With xxhash and bitwise tricks, signature generation is ~5× faster than 64-bit MinHash because of cheaper bit-level packing.
- Thread-safety: pure functions. SIMD: signature comparison is bitwise XOR + popcount on packed 64-bit words. Memory: `k · b / 8` bytes per signature (64 bytes per page at b=1, k=512).

## Python fallback
`backend/apps/pipeline/services/b_bit_minhash.py::BBitMinHash` (mirrors `datasketch.MinHash` with bit-packing wrapper).

## Benchmark plan
| n shingles | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 1,000 | 12 | <1 | ≥12x |
| 100,000 | 1,100 | <100 | ≥11x |
| 10,000,000 | 110,000 | <9,000 | ≥12x |

## Diagnostics
UI: numeric "estimated Jaccard 0.78 (95% CI [0.74, 0.82])". Debug fields: `signature_bits_b`, `permutations_k`, `match_count_M`, `raw_match_fraction`, `correction_C1`, `correction_C2`, `estimated_jaccard`, `confidence_interval_low_high`.

## Edge cases & neutral fallback
Empty set → all-zero signature (or sentinel); similarity to any set returns NaN with state flag. b=0 → degenerate (every comparison matches); raise ValueError. b ≥ 64 → equivalent to standard MinHash (no compression). Universe size `D` unknown → use auto-estimated `D ≈ Σ |S_i|` from corpus. Set sizes `f_1, f_2` required for unbiased estimator; if unavailable use uncorrected `R̂_naive = (M/k − 2^{−b}) / (1 − 2^{−b})`.

## Minimum-data threshold
At least k=64 permutations and 50 shingles per set for stable Jaccard estimates.

## Budget
Disk: 64 bytes/page at b=1, k=512 ·  RAM: ~1.6 MB total for 25,000 pages

## Scope boundary vs existing signals
FR-014 (near-duplicate destination clustering) currently uses standard MinHash; FR-151 supersedes for the *storage* path while FR-014's clustering algorithm remains unchanged. FR-082 (structural duplicate detection) compares HTML structure; FR-151 compares text content via shingles. FR-064 (spectral relational clustering) is graph-based and unrelated. FR-151 is the canonical low-RAM "are these two pages near-duplicate?" signal.

## Test plan bullets
- Two identical sets → R̂ = 1.0 within ±0.02 at k=512, b=1.
- Two disjoint sets → R̂ ≈ 0 within ±0.02.
- Compare R̂ to true Jaccard for k=64, 128, 512: variance scales as 1/k as predicted.
- b=1 storage = 64 bytes vs b=64 standard = 4096 bytes at k=512.
- Empty set similarity → NaN or neutral fallback, no crash.
- Compare to `datasketch.MinHash`: similarity error < 0.05 for R ∈ [0.4, 1.0].
- Universe-size correction: with known `D`, R̂ matches exact Jaccard within variance bounds.
- Persistence: serialise packed signature, deserialise, continue.
