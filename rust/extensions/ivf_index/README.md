# ivf_index (Rust)

Inverted File (IVF) + Optimized Product Quantization (OPQ) asymmetric-distance
vector-search kernel. Ported from the C++ `ivf_index` kernel
(`backend/extensions/ivf_index.cpp` + `include/ivf_index_core.h`) to Rust and
exposed to Python as the native module `extensions.ivf_index` via PyO3 + the
`numpy` crate.

## Python-callable surface

Two module-level functions (no classes), matching the old C++ pybind11 module:

- `ivf_search(query, centroids, partition_member_lists, opq_codes, rotation,
  codebooks, nprobe=16, top_k=100) -> numpy.ndarray[int32]`
  Finds the top-`nprobe` nearest centroids by squared-L2, walks their assigned
  members, scores each by asymmetric distance computation (ADC), and returns the
  global vector indices of the nearest neighbours ordered ascending by ADC
  distance (length `<= top_k`). Out-of-range centroid and vector ids are
  skipped. **No production Python caller** — present for completeness and the
  native-runtime health probe.
- `adc_score_destination(query, opq_codes, rotation, codebooks) ->
  (best_index: int, best_cosine_sim: float)`
  Builds the per-query ADC lookup table once and scores each OPQ code row,
  returning the closest passage (first minimum wins) and its cosine similarity
  `clamp(1 - dist/2, 0, 1)`. **The only production caller** is
  `apps/pipeline/services/passage_relevance.py`. Empty `opq_codes` returns
  `(0, 0.0)` before any shape validation.

## Parity basis: `contract` (not byte-exact)

The binding floor is correct nearest-neighbour ranking within `<= 1e-4` ADC
distance and identical exception types/messages and skip/degenerate/empty
behaviour — **not** byte-identical float output. The C++ build used
`-O3 -march=native` (FMA contraction, vectorised reductions); this Rust port
uses a scalar serial `f32` sum with `mul_add`, so the last ULP can differ. The
only real consumer reads `best_cosine_sim` and `best_index` for ranking, which
the contract preserves.

### Port notes

- **Tie order made deterministic.** The C++ `partial_sort` / `std::sort` left
  distance ties implementation-defined. This port breaks ties by id ascending
  (centroids, in `find_top_centroids`) and by `vec_idx` ascending (search
  results). This does not change the result SET for distinct distances; it only
  fixes a reproducible order for ties, allowed under the `contract` basis.
- **Degenerate geometry** (`m == 0` or `dim % m != 0`) zero-fills the LUT, no
  error — every code then scores `0.0`.
- **Rotation convention** is `q_rot[j] = sum_i query[i] * rotation[i*dim + j]`
  (`q . R`, `R` indexed row-major), exactly as the C++.

## Tests and benchmark

- `cargo test -p ivf_index` exercises the plain-Rust core
  (`find_top_centroids`, `build_adc_lut`, `adc_distance`, `ivf_search_core`,
  `adc_score_destination_core`) including the degenerate, empty, out-of-range,
  tie, clamp, NaN, and many-vector f64-reference parity cases.
- `cargo bench -p ivf_index` runs the Criterion benchmark over
  `adc_score_destination_core` at 3 passage counts (8 / 64 / 256) at the
  production OPQ geometry (dim 1024, m 8, k 256).

## Citations

- Sivic and Zisserman 2003 ICCV, `doi:10.1109/ICCV.2003.1238663` — inverted file.
- Jegou, Douze and Schmid 2010 CVPR / 2011 IEEE TPAMI,
  `doi:10.1109/TPAMI.2010.57` — Product Quantization + IVFADC.
- Ge, He, Ke and Sun 2013 CVPR, `doi:10.1109/CVPR.2013.379` — Optimized Product
  Quantization (OPQ rotation).
