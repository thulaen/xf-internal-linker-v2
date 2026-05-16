# C++ Kernel Roadmap (parked work)

**Plain-English summary**

This file lists every C++ kernel that was DECLARED in `backend/apps/diagnostics/health.py` but for which no `backend/extensions/<name>.cpp` source ever existed. We are NOT throwing the names away — they are parked here so a future agent can pick one up, write the kernel, and re-promote it through the full Rule J lifecycle (source file + EXTENSION_NAMES + _NATIVE_RUNTIME_MODULES).

**Why this file exists**

Until 2026-05-16 the health check declared 124 C++ kernels but only 23 of them had a `.cpp` source on disk (and 1 of those — `pixie_walk.cpp` — was an empty placeholder). That meant 112 names showed up forever as "missing C++ kernels" in the diagnostics GUI even though nobody was actually working on them. The Rule J lifecycle hook also could not enforce "all three places together" because the codebase started from a half-registered state.

The 2026-05-16 cleanup did three things at once:

1. Deleted the empty `backend/extensions/pixie_walk.cpp` placeholder.
2. Trimmed `_NATIVE_RUNTIME_MODULES` to the 12 entries that have a real, non-empty `.cpp` source.
3. Parked the 112 declared-but-not-built kernel tuples here so the roadmap isn't lost.

**Re-promoting a kernel back into the build**

When a future agent wants to actually implement one of these kernels:

1. Write `backend/extensions/<name>.cpp` with a `PYBIND11_MODULE(<name>, m) { ... }` block. The module name **must** match the filename stem.
2. Add `"<name>"` to the `EXTENSION_NAMES` set in `scripts/ensure_compiled_artifacts.py`.
3. Move the matching tuple line from this file back into `_NATIVE_RUNTIME_MODULES` in `backend/apps/diagnostics/health.py`.
4. Add unit tests, a benchmark (per the Mandatory Benchmark Rule), and a spec entry in `docs/specs/` with at least one citation (Citation Rule).
5. Run `docker compose exec -T backend python manage.py check_kernel_status` to confirm the kernel lights up in the diagnostics GUI.

The `.githooks/check-cpp-lifecycle.py` hook will hard-block the commit if any of the three registration points is missing.

**11 orphan kernels (previously had `.cpp` source but were missing from `_NATIVE_RUNTIME_MODULES`) — RESOLVED in the same 2026-05-16 cleanup**

These already had real source on disk. The cleanup extracted their `PYBIND11_MODULE` exports (`m.def` function names or `py::class_` class names) and added them directly to `_NATIVE_RUNTIME_MODULES` so the health check tracks them. The final three-way state is 23/23/23 — every kernel name is in all three places (source file, `EXTENSION_NAMES`, `_NATIVE_RUNTIME_MODULES`):

| Kernel | Callable / class used by `hasattr` check |
| --- | --- |
| `anchor_descriptiveness` | `damerau_levenshtein` |
| `anchor_diversity` | `evaluate_batch` |
| `anchor_self_information` | `bigram_entropy` |
| `api_rate_limiter` | `RateLimiterRegistry` (class) |
| `compressed_bloom` | `CompressedBloomFilter` (class) |
| `count_min_sketch` | `CountMinSketch` (class) |
| `counting_bloom` | `CountingBloomFilter` (class) |
| `generic_anchor_matcher` | `build_automaton` |
| `ivf_index` | `ivf_search` |
| `lesson_index` | `memory_cap_bytes` |
| `papertrail_dedup` | `DedupIndex` (class) |

---

## Parked kernel tuples (112 names — paste back into `_NATIVE_RUNTIME_MODULES` when re-implementing)

The tuples below preserve the original `(name, callable, label, critical)` shape. The `callable` and `label` values are placeholders inherited from the original declarations — verify them against the actual `PYBIND11_MODULE` exports when re-implementing.

### FR-051/058: Patent-backed ranking signal extensions

```python
("refcontext", "ref_context_score", "FR-051 Reference context scorer", False),
("ngramqual", "ngram_score", "FR-058 N-gram quality scorer", False),
```

### FR-066/067/068: Core meta-algorithm extensions

```python
("smoothrank", "smoothrank_step", "FR-066 SmoothRank NDCG optimiser", False),
("rankagg", "power_iter", "FR-067 Markov rank aggregation", False),
("cascade", "stage_score", "FR-068 Cascade re-ranker", False),
```

### OPT-01 to OPT-05: Initial resource optimisations

```python
("embpool", "alloc", "OPT-01 Embedding memory pool", False),
("vecdeser", "parse_vector", "OPT-02 Fast vector deserialiser", False),
("jaccard_avx", "jaccard_similarity", "OPT-03 AVX2 Jaccard kernel", False),
("clustuf", "union_find", "OPT-04 Cluster union-find", False),
("candfilter", "filter_candidates", "OPT-05 SIMD candidate filter", False),
```

### OPT-07 to OPT-12: Memory allocators

```python
("slab_alloc", "alloc", "OPT-07 Slab allocator", False),
("buddy_alloc", "alloc", "OPT-08 Buddy allocator", False),
("cow_buffer", "wrap", "OPT-09 Copy-on-write buffer", False),
("obj_recycle", "recycle", "OPT-10 Object recycler", False),
("stack_scratch", "alloc", "OPT-11 Stack scratch allocator", False),
("compact_heap", "compact", "OPT-12 Compact heap", False),
```

### OPT-13 to OPT-20: Data structures

```python
("robin_map", "lookup", "OPT-13 Robin Hood hash map", False),
("btree_map", "range_query", "OPT-14 B-tree range map", False),
("skip_rank", "insert", "OPT-15 Skip list top-K", False),
("trie_prefix", "search", "OPT-16 Patricia trie prefix search", False),
("compact_set", "contains", "OPT-17 Compact hash set", False),
("bitset_bloom", "check", "OPT-18 Bloom filter", False),
("sparse_bitvec", "rank", "OPT-19 Sparse bit vector", False),
("ring_queue", "push", "OPT-20 Lock-free ring buffer", False),
```

### OPT-21 to OPT-27: SIMD / AVX2 vectorised operations

```python
("simd_cosine", "cosine_sim", "OPT-21 AVX2 cosine similarity", False),
("simd_topk", "partial_sort", "OPT-22 AVX2 top-K selection", False),
("simd_dotbatch", "dot_batch", "OPT-23 AVX2 batched dot product", False),
("simd_hamming", "hamming_dist", "OPT-24 AVX2 Hamming distance", False),
("simd_strlen", "bulk_strlen", "OPT-25 SIMD string length", False),
("simd_minmax", "reduce", "OPT-26 AVX2 min/max reduction", False),
("simd_gather", "gather", "OPT-27 AVX2 gather", False),
```

### OPT-28 to OPT-34: Compression & encoding

```python
("varint_enc", "encode", "OPT-28 Varint encoder", False),
("delta_enc", "encode", "OPT-29 Delta encoder", False),
("dict_enc", "encode", "OPT-30 Dictionary encoder", False),
("rle_flags", "encode", "OPT-31 Run-length encoder", False),
("fp16_vec", "convert", "OPT-32 Float16 converter", False),
("nibble_score", "pack", "OPT-33 4-bit score packer", False),
("lz4_block", "compress", "OPT-34 LZ4 block compressor", False),
```

### OPT-35 to OPT-38: Cache-line-friendly layouts

```python
("soa_candidate", "to_soa", "OPT-35 Struct-of-arrays layout", False),
("padded_vec", "alloc_aligned", "OPT-36 Cache-aligned vectors", False),
("hot_cold_split", "split", "OPT-37 Hot/cold field splitter", False),
("tile_matrix", "tile_mul", "OPT-38 Cache-tiled matrix ops", False),
```

### OPT-39 to OPT-43: String optimisation

```python
("sso_string", "create", "OPT-39 Small-string optimised container", False),
("str_intern", "intern", "OPT-40 String interning table", False),
("rope_text", "concat", "OPT-41 Rope data structure", False),
("suffix_arr", "search", "OPT-42 Suffix array substring search", False),
("url_canon", "canonicalize", "OPT-43 URL canonicaliser", False),
```

### OPT-44 to OPT-47: Serialisation & zero-copy

```python
("flatvec", "serialize", "OPT-44 FlatBuffers zero-copy", False),
("zerocopy_buf", "as_numpy", "OPT-45 Zero-copy buffer protocol", False),
("msgpack_fast", "pack", "OPT-46 Fast MessagePack", False),
("proto_lite", "encode", "OPT-47 Lightweight protobuf", False),
```

### OPT-48 to OPT-52: Parallel processing

```python
("worksteal_pool", "submit", "OPT-48 Work-stealing thread pool", False),
("lockfree_map", "insert", "OPT-49 Lock-free sharded map", False),
("par_merge", "merge", "OPT-50 Parallel merge sort", False),
("rw_spinlock", "read_lock", "OPT-51 Reader-writer spinlock", False),
("atomic_counter", "increment", "OPT-52 Cache-aligned atomic counter", False),
```

### OPT-53 to OPT-57: I/O prefetching

```python
("async_reader", "read_async", "OPT-53 io_uring async reader", False),
("mmap_embed", "open_mmap", "OPT-54 Memory-mapped embeddings", False),
("prefetch_hint", "prefetch", "OPT-55 Cache prefetch hints", False),
("buffered_write", "flush", "OPT-56 Buffered writer", False),
("page_touch", "touch", "OPT-57 Page pre-fault", False),
```

### OPT-58 to OPT-61: Numerical optimisation

```python
("fixedpt_score", "to_fixed", "OPT-58 Fixed-point scoring", False),
("lut_sigmoid", "sigmoid", "OPT-59 Lookup-table sigmoid", False),
("fast_log", "log2", "OPT-60 Fast IEEE754 log2", False),
("rsqrt_norm", "rsqrt", "OPT-61 Fast inverse sqrt", False),
```

### OPT-62 to OPT-65: Index structures

```python
("radix_tree", "lookup", "OPT-62 Radix tree URL index", False),
("bitmap_idx", "query", "OPT-63 Bitmap index filter", False),
("sparse_matrix", "spmv", "OPT-64 Sparse CSR matrix-vector", False),
("interval_tree", "overlap", "OPT-65 Interval tree query", False),
```

### OPT-66 to OPT-68: Network / IPC

```python
("redis_pipe", "execute", "OPT-66 Redis pipeline batcher", False),
("pg_batch", "copy_in", "OPT-67 PostgreSQL COPY batcher", False),
("ipc_shm", "write", "OPT-68 Shared-memory IPC", False),
```

### OPT-69 to OPT-70: SQL optimisation

```python
("prepared_stmt", "execute", "OPT-69 Prepared statement cache", False),
("result_codec", "decode", "OPT-70 Binary result decoder", False),
```

### OPT-71 to OPT-72: Pipeline-specific

```python
("incr_diff", "has_changed", "OPT-71 Incremental content differ", False),
("result_cache", "get", "OPT-72 Two-tier result cache", False),
```

### META-04 to META-39: Extended meta-algorithm extensions

```python
("coord_ascent", "optimize", "META-04 Coordinate ascent ranker", False),
("cma_es", "optimize", "META-05 CMA-ES weight optimiser", False),
("random_search", "search", "META-06 Random search sampler", False),
("sim_anneal", "anneal", "META-07 Simulated annealing ranker", False),
("diff_evolution", "evolve", "META-08 Differential evolution", False),
("quantile_norm", "normalize", "META-09 Quantile score normaliser", False),
("sigmoid_temp", "scale", "META-10 Sigmoid temperature scaler", False),
("zscore_norm", "normalize", "META-11 Z-score query normaliser", False),
("boxcox_tf", "transform", "META-12 Box-Cox transformer", False),
("rank_pctl", "normalize", "META-13 Rank percentile normaliser", False),
("feat_cross", "cross", "META-14 Pairwise feature crosses", False),
("residual_stack", "stack", "META-15 Residual feature stacker", False),
("ratio_feat", "generate", "META-16 Ratio feature generator", False),
("elastic_reg", "regularize", "META-17 Elastic net regulariser", False),
("weight_drop", "ensemble", "META-18 Weight dropout ensemble", False),
("maxnorm_clip", "clip", "META-19 Max-norm weight clipper", False),
("huber_loss", "loss", "META-20 Huber pairwise loss", False),
("focal_loss", "loss", "META-21 Focal ranking loss", False),
("hinge_loss", "loss", "META-22 Hinge rank loss", False),
("pa_ranker", "update", "META-23 Passive-aggressive ranker", False),
("exp_decay", "decay", "META-24 Exponential decay updater", False),
("slide_window", "retrain", "META-25 Sliding window retrainer", False),
("stack_meta", "blend", "META-26 Stacking meta-learner", False),
("bayes_avg", "average", "META-27 Bayesian model averaging", False),
("bucket_blend", "blend", "META-28 Bucket-wise blender", False),
("bootstrap_ci", "confidence", "META-29 Bootstrap confidence scorer", False),
("conformal_band", "predict", "META-30 Conformal prediction bands", False),
("winsorize", "clip", "META-31 Winsorize score clipper", False),
("iso_forest", "score", "META-32 Isolation forest filter", False),
("eq_freq_bin", "bin", "META-33 Equal frequency binner", False),
("adam_opt", "step", "META-34 Adam weight optimiser", False),
("sgd_mom", "step", "META-35 SGD+momentum optimiser", False),
("rmsprop_opt", "step", "META-36 RMSProp weight optimiser", False),
("kfold_sel", "select", "META-37 K-fold weight selector", False),
("succ_halve", "evaluate", "META-38 Successive halving tuner", False),
("qcluster_route", "route", "META-39 Query cluster router", False),
```

---

## How the cleanup was decided (2026-05-16)

The Rule J hook (`.githooks/check-cpp-lifecycle.py`) requires every C++ kernel name to be present in ALL THREE places together: a non-empty `.cpp` source with a matching `PYBIND11_MODULE` block, the `EXTENSION_NAMES` set, AND `_NATIVE_RUNTIME_MODULES`. Before this cleanup, that invariant was violated for 112 names. Asking the hook to "lock down" a state it never reached was nonsense, so we first cleaned the state.

The cleanup kept the 12 kernels that already passed all three checks. Everything else was either parked here (no source) or moved to a paper-trail follow-up (has source but missing the runtime declaration). Once the cleanup committed, the hook started running in full-tree mode (Phase A): every commit re-validates the full set, not just the staged diff.

If you want to bring one of these names back, the implementation cost is real: a kernel needs a spec citation, a benchmark across three input sizes, tests, and a 20× speedup proof. Picking from this list is not a free decision — it's a slice-sized commitment.
