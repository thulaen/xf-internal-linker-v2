"""Generate all 108 META and OPT spec files for docs/specs/."""
import os

SPECS_DIR = os.path.join(os.path.dirname(__file__), '..', 'docs', 'specs')

SAFETY = """## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Predicate-form `condition_variable::wait()`. Document atomic ordering. `_mm_pause()` spinlocks with 1000-iter fallback.

**Memory:** No raw `new`/`delete` hot paths. No `alloca`/VLA. No `void*` delete. RAII only. Debug bounds checks. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` beyond scope. No return ref to local.

**Type safety:** `static_cast` for narrowing. No signed/unsigned mismatch. No aliasing violation. All switch handled.

**SIMD:** No SSE/AVX mix without `zeroupper`. Unaligned loads. Max 12 YMM. `alignas(64)` hot arrays.

**Floating point:** Flush-to-zero init. NaN/Inf entry checks. Double accumulator >100 elements.

**Performance:** No `std::endl` loops. No `std::function` hot. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** `noexcept` destructors. `const&` catch. Basic guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_str)`. Scrub memory. No TOCTOU."""

GATES = """## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings `-Werror` |
| 2 | `pytest test_parity_*.py` | Matches Python ref within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero ASAN/UBSan errors |
| 4 | `bench_extensions.py` | >=3x faster than Python |
| 5 | `pytest test_edges_*.py` | Empty, single, NaN/Inf, n=10000 pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md confirmed |"""

def write_spec(fname, title, cat, cppfile, algo, sig, ram="<10 MB"):
    path = os.path.join(SPECS_DIR, f"{fname}.md")
    if os.path.exists(path):
        return  # don't overwrite
    content = f"""# {title}

## Overview
**Category:** {cat}
**Extension file:** `{cppfile}`
**Expected speedup:** >=3x over Python equivalent
**RAM:** {ram} | **Disk:** <1 MB

## Algorithm

{algo}

## C++ Interface (pybind11)

```cpp
{sig}
```

## Memory Budget
- Runtime RAM: {ram}
- Disk: <1 MB (compiled .so/.pyd only)

## Performance Target
- Target: >=3x faster than Python baseline
- Benchmark: 1000 iterations on production-size input

{SAFETY}

{GATES}

## Dependencies
- None (standalone extension)

## Test Plan
- Correctness: output matches Python reference within 1e-4
- Edge cases: empty input, single element, NaN/Inf, n=10000
- Seed reproducibility (where applicable)
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ── META-04 to META-39 (36 files, meta-04 already exists) ──

METAS = [
    ("meta-05-cma-es-optimizer", "META-05 -- CMA-ES Weight Optimizer", "Weight optimizer", "cma_es.cpp",
     "Sample lambda=20 vectors from N(mu, C). Evaluate NDCG. Update mu = weighted mean of top-mu. C via rank-1 + rank-mu update. O(d^2 * lambda) per generation.",
     "std::vector<float> cma_es_optimize(const float* init, int d, int n_gen, int lambda_pop);"),
    ("meta-06-random-search", "META-06 -- Random Search Weight Sampler", "Weight optimizer", "random_search.cpp",
     "Draw w_i ~ LogUniform(0.01, 10) for T=500 iterations. Keep w* = argmax NDCG(w). O(T * eval_cost).",
     "std::vector<float> random_search(int d, int T, uint64_t seed);"),
    ("meta-07-simulated-annealing", "META-07 -- Simulated Annealing Ranker", "Weight optimizer", "sim_anneal.cpp",
     "Perturb: w' = w + N(0, T*I). Accept if NDCG improves or with prob exp(delta/T). T *= 0.99. O(steps * eval_cost).",
     "std::vector<float> sim_anneal(const float* init, int d, int steps, float T0, float cool);"),
    ("meta-08-differential-evolution", "META-08 -- Differential Evolution", "Weight optimizer", "diff_evolution.cpp",
     "Mutant: v = w_a + F*(w_b - w_c). Trial: u_j = v_j if rand<CR else w_j. Replace if better. F=0.8, CR=0.9.",
     "std::vector<float> diff_evolution(int d, int pop, int gen, float F, float CR, uint64_t seed);"),
    ("meta-09-quantile-normalizer", "META-09 -- Quantile Score Normalizer", "Score normalizer", "quantile_norm.cpp",
     "q_i = rank(s_i) / n. Output in (0,1]. O(n log n) for sort.",
     "void quantile_normalize(const float* scores, int n, float* out);"),
    ("meta-10-sigmoid-temperature", "META-10 -- Sigmoid Temperature Scaler", "Score normalizer", "sigmoid_temp.cpp",
     "f(s) = 1/(1+exp(-(s-mu)/tau)). Learn mu, tau per signal by MLE. O(n).",
     "void sigmoid_scale(const float* scores, int n, float mu, float tau, float* out);"),
    ("meta-11-zscore-normalizer", "META-11 -- Z-Score Query Normalizer", "Score normalizer", "zscore_norm.cpp",
     "z_i = (s_i - mean) / (std + eps). eps=1e-6. Two-pass O(n).",
     "void zscore_normalize(const float* scores, int n, float eps, float* out);"),
    ("meta-12-box-cox-transform", "META-12 -- Box-Cox Transformer", "Score normalizer", "boxcox_tf.cpp",
     "y(s;lam) = (s^lam - 1)/lam if lam!=0 else log(s). Fit lam by max Shapiro-Wilk. O(n log n).",
     "float boxcox_fit(const float* s, int n); void boxcox_transform(const float* s, int n, float lam, float* out);"),
    ("meta-13-rank-percentile", "META-13 -- Rank Percentile Normalizer", "Score normalizer", "rank_pctl.cpp",
     "p_i = (rank(s_i) - 0.5) / n. Uniform [0,1]. O(n log n).",
     "void rank_percentile(const float* scores, int n, float* out);"),
    ("meta-14-pairwise-feature-crosses", "META-14 -- Pairwise Feature Crosses", "Feature interaction", "feat_cross.cpp",
     "cross_ij = s_i * s_j for top-K pairs by mutual information. O(K*n).",
     "void feature_crosses(const float* feats, int n, int d, const int* pairs, int K, float* out);"),
    ("meta-15-residual-stacker", "META-15 -- Residual Feature Stacker", "Feature interaction", "residual_stack.cpp",
     "r_i = y_i - f0(x_i). Train f1 on residuals. score = f0(x) + alpha*f1(x). O(n*d).",
     "void residual_stack(const float* base, const float* resid, int n, float alpha, float* out);"),
    ("meta-16-ratio-feature-generator", "META-16 -- Ratio Feature Generator", "Feature interaction", "ratio_feat.cpp",
     "ratio_ij = log(s_i / (s_j + eps)). Clip [-10,10]. O(K*n).",
     "void ratio_features(const float* feats, int n, int d, const int* pairs, int K, float eps, float* out);"),
    ("meta-17-elastic-net-regularizer", "META-17 -- Elastic Net Regularizer", "Regularizer", "elastic_reg.cpp",
     "L(w) = loss + alpha*||w||_1 + beta*||w||_2^2. Proximal: prox_L1(w - lr*grad). O(d).",
     "void elastic_net_step(float* w, const float* grad, int d, float lr, float a_l1, float b_l2);"),
    ("meta-18-weight-dropout-ensemble", "META-18 -- Weight Dropout Ensemble", "Regularizer", "weight_drop.cpp",
     "Mask m ~ Bernoulli(1-p), p=0.2. Use w*m. Inference: average B=10 passes. O(B*n*d).",
     "void dropout_ensemble(const float* w, int d, const float* feats, int n, int B, float p, uint64_t seed, float* out);"),
    ("meta-19-max-norm-clipper", "META-19 -- Max-Norm Weight Clipper", "Regularizer", "maxnorm_clip.cpp",
     "If ||w||_2 > c: w *= c/||w||_2. c=3.0. O(d).",
     "void maxnorm_clip(float* w, int d, float max_norm);"),
    ("meta-20-huber-pairwise-loss", "META-20 -- Huber Pairwise Loss", "Loss function", "huber_loss.cpp",
     "L_H(D) = 0.5*D^2 if |D|<delta else delta*(|D|-0.5*delta). D = f(u)-f(v)-margin. O(n_pairs).",
     "float huber_loss(const float* scores, const int* pairs, int np, float margin, float delta);"),
    ("meta-21-focal-ranking-loss", "META-21 -- Focal Ranking Loss", "Loss function", "focal_loss.cpp",
     "p_t = sigma(f(u)-f(v)). L = -(1-p_t)^gamma * log(p_t). gamma=2. Down-weights easy pairs. O(n_pairs).",
     "float focal_loss(const float* scores, const int* pairs, int np, float gamma);"),
    ("meta-22-hinge-rank-loss", "META-22 -- Hinge Rank Loss", "Loss function", "hinge_loss.cpp",
     "L = sum max(0, margin - (f(u)-f(v))). margin=1.0. Zero grad when correct. O(n_pairs).",
     "float hinge_loss(const float* scores, const int* pairs, int np, float margin);"),
    ("meta-23-passive-aggressive-ranker", "META-23 -- Passive-Aggressive Ranker", "Online learner", "pa_ranker.cpp",
     "Loss l = max(0, 1-(f(u)-f(v))). dw = (l/||u-v||^2) * sign(u-v). PA-II: clip C=0.1. O(d).",
     "void pa_update(float* w, const float* xu, const float* xv, int d, float C);"),
    ("meta-24-exponential-decay-updater", "META-24 -- Exponential Decay Updater", "Online learner", "exp_decay.cpp",
     "alpha_t = exp(-lambda * age_t). lambda=0.01/day. g = sum(alpha_t * grad_t). O(n).",
     "void exp_decay_grad(const float* grads, const float* ages, int n, int d, float lambda, float* out);"),
    ("meta-25-sliding-window-retrainer", "META-25 -- Sliding Window Retrainer", "Online learner", "slide_window.cpp",
     "FIFO buffer: last W=1000 pairs. Every R=100 new: re-solve via L-BFGS on buffer. O(W*d).",
     "void slide_window_retrain(const float* buffer, int W, int d, float* weights);"),
    ("meta-26-stacking-meta-learner", "META-26 -- Stacking Meta-Learner", "Ensemble blender", "stack_meta.cpp",
     "K ranker score vectors. Ridge: w* = (X^T X + lam*I)^-1 X^T y. O(K^2*n).",
     "void stack_blend(const float* scores, int n, int K, float lambda, float* weights);"),
    ("meta-27-bayesian-model-averaging", "META-27 -- Bayesian Model Averaging", "Ensemble blender", "bayes_avg.cpp",
     "p(Mk|D) ~ exp(NDCG(Mk)). f(x) = sum_k p(Mk)*fk(x). O(K*n).",
     "void bayes_average(const float* scores, const float* ndcgs, int n, int K, float* out);"),
    ("meta-28-bucket-wise-blender", "META-28 -- Bucket-Wise Blender", "Ensemble blender", "bucket_blend.cpp",
     "Cluster sources into B=8 buckets. Separate ridge blender per bucket. O(B*K^2*n/B).",
     "void bucket_blend(const float* feats, const int* buckets, int n, int B, int K, float* weights);"),
    ("meta-29-bootstrap-confidence", "META-29 -- Bootstrap Confidence Scorer", "Confidence estimator", "bootstrap_ci.cpp",
     "B=50 resamplings. Variance sigma^2. CI = score +/- 1.96*sigma. O(B*n).",
     "void bootstrap_ci(const float* scores, int n, int B, uint64_t seed, float* mean, float* lo, float* hi);"),
    ("meta-30-conformal-prediction", "META-30 -- Conformal Prediction Bands", "Confidence estimator", "conformal_band.cpp",
     "Residuals r_i = y_i - f(x_i). 90th pct q_hat. Band: [f(x)-q, f(x)+q]. O(n log n).",
     "void conformal_bands(const float* scores, const float* labels, int n, float alpha, float* lo, float* hi);"),
    ("meta-31-winsorize-clipper", "META-31 -- Winsorize Score Clipper", "Outlier handler", "winsorize.cpp",
     "p2=2nd pct, p98=98th pct. Clip: s = max(p2, min(p98, s)). O(n log n).",
     "void winsorize(float* scores, int n, float low_pct, float high_pct);"),
    ("meta-32-isolation-forest-filter", "META-32 -- Isolation Forest Filter", "Outlier handler", "iso_forest.cpp",
     "a(x) = -log2(h(x)) + log2(c(n)). h=avg path length. Down-weight if a>threshold. O(n*trees*log(n)).",
     "void iso_forest_score(const float* feats, int n, int d, int trees, float* anomaly);"),
    ("meta-33-equal-frequency-binner", "META-33 -- Equal Frequency Binner", "Discretizer", "eq_freq_bin.cpp",
     "Sort. bin = floor(rank * K / n), K=20. Output bin/K. O(n log n).",
     "void eq_freq_bin(const float* scores, int n, int K, float* out);"),
    ("meta-34-adam-optimizer", "META-34 -- Adam Weight Optimizer", "Gradient optimizer", "adam_opt.cpp",
     "m = b1*m+(1-b1)*g. v = b2*v+(1-b2)*g^2. w -= lr*m_hat/sqrt(v_hat+eps). b1=0.9, b2=0.999. O(d).",
     "void adam_step(float* w, float* m, float* v, const float* grad, int d, float lr, float b1, float b2, float eps, int t);"),
    ("meta-35-sgd-momentum", "META-35 -- SGD+Momentum Optimizer", "Gradient optimizer", "sgd_mom.cpp",
     "v = gamma*v + lr*grad. w -= v. Nesterov: grad at w-gamma*v. gamma=0.9, lr=0.001. O(d).",
     "void sgd_step(float* w, float* v, const float* grad, int d, float lr, float gamma, bool nesterov);"),
    ("meta-36-rmsprop-optimizer", "META-36 -- RMSProp Weight Optimizer", "Gradient optimizer", "rmsprop_opt.cpp",
     "v = rho*v+(1-rho)*g^2. w -= lr*g/sqrt(v+eps). rho=0.9. O(d).",
     "void rmsprop_step(float* w, float* v, const float* grad, int d, float lr, float rho, float eps);"),
    ("meta-37-kfold-weight-selector", "META-37 -- K-Fold Weight Selector", "Cross-validator", "kfold_sel.cpp",
     "K=5 folds. Train on 4, eval on 1. w* = argmax mean NDCG. O(K * train_cost).",
     "std::vector<float> kfold_select(const float* feats, const int* labels, int n, int d, int K);"),
    ("meta-38-successive-halving", "META-38 -- Successive Halving Tuner", "Cross-validator", "succ_halve.cpp",
     "n0 configs, B budget. Each round: eval B_r, halve configs. eta=3. O(n0 * log(n0)).",
     "std::vector<float> succ_halving(int n_configs, int d, int budget, int eta, uint64_t seed);"),
    ("meta-39-query-cluster-router", "META-39 -- Query Cluster Weight Router", "Query specializer", "qcluster_route.cpp",
     "K-Means(K=16) on source embeddings. Per-cluster weight vector. Route by nearest centroid. O(K*d).",
     "int route_query(const float* emb, const float* centroids, int K, int d);"),
]

# ── OPT-01 to OPT-72 (72 files) ──

OPTS = [
    ("opt-01-embedding-memory-pool", "OPT-01 -- Embedding Memory Pool", "Memory allocator", "embpool.cpp",
     "Pre-alloc arena: ptr = malloc(MAX). slice = arena.alloc(n*d*4). No realloc, no copy. O(1) alloc.", "<20 MB"),
    ("opt-02-fast-vector-deserializer", "OPT-02 -- Fast Vector Deserializer", "Serialization", "vecdeser.cpp",
     "Parse [f1,f2,...,fd] wire string in one C pass: strtof per token, write to float*. O(d).", "<2 MB"),
    ("opt-03-avx2-jaccard", "OPT-03 -- AVX2 Jaccard Similarity", "SIMD vectorization", "jaccard_avx.cpp",
     "A_bits AND B_bits -> popcount(AND) / popcount(OR). _mm256_and_si256 + popcountll. O(n/256).", "<1 MB"),
    ("opt-04-cluster-union-find", "OPT-04 -- Cluster Union-Find", "Data structure", "clustuf.cpp",
     "find(i) with path compression. union(a,b) by rank. O(alpha(n)) amortised.", "<5 MB"),
    ("opt-05-simd-candidate-filter", "OPT-05 -- SIMD Candidate Filter", "SIMD vectorization", "candfilter.cpp",
     "Load 5 threshold arrays. _mm256_cmp_ps all 5 in parallel. AND masks -> survivors. O(n/8).", "<2 MB"),
    ("opt-06-int8-embedding-quantizer", "OPT-06 -- Int8 Embedding Quantizer", "Compression", "quantemb.cpp",
     "int8 = round((float - min) / (max - min) * 255) - 128. Store min,max per dim. O(n*d).", "<5 MB"),
    ("opt-07-slab-allocator", "OPT-07 -- Slab Allocator", "Memory allocator", "slab_alloc.cpp",
     "Fixed slab size S. Free list per size. O(1) alloc/free via pointer pop/push.", "<10 MB"),
    ("opt-08-buddy-allocator", "OPT-08 -- Buddy Allocator", "Memory allocator", "buddy_alloc.cpp",
     "Round to power-of-2. Split buddy blocks. Merge free buddies. O(log N).", "<10 MB"),
    ("opt-09-copy-on-write-buffer", "OPT-09 -- Copy-on-Write Buffer", "Memory allocator", "cow_buffer.cpp",
     "ref_count per buffer. Copy on write: if ref>1, deep-copy before mutate. O(1) share, O(n) copy.", "<5 MB"),
    ("opt-10-object-recycler", "OPT-10 -- Object Recycler", "Memory allocator", "obj_recycle.cpp",
     "Intrusive linked list of free objects. new() = pop. delete() = push. O(1).", "<5 MB"),
    ("opt-11-stack-scratch-allocator", "OPT-11 -- Stack Scratch Allocator", "Memory allocator", "stack_scratch.cpp",
     "Bump allocator: ptr += size. Reset to base after frame. No free needed. O(1).", "<5 MB"),
    ("opt-12-compact-heap", "OPT-12 -- Compact Heap", "Memory allocator", "compact_heap.cpp",
     "Mark-compact: mark live, compute new addresses, move objects, update pointers. O(n).", "<10 MB"),
    ("opt-13-robin-hood-map", "OPT-13 -- Robin Hood Hash Map", "Data structure", "robin_map.cpp",
     "Open addressing. Probe: (h + i + i^2) % cap. Store displacement. 40-50% less memory than dict. O(1) avg.", "<12 MB"),
    ("opt-14-btree-range-map", "OPT-14 -- B-Tree Range Map", "Data structure", "btree_map.cpp",
     "B-tree order=32. Node = 32 keys + 33 children. All data in leaves. 5-8x faster range scans. O(log n).", "<6 MB"),
    ("opt-15-skip-list-topk", "OPT-15 -- Skip List Top-K", "Data structure", "skip_rank.cpp",
     "L=16 levels. O(log n) insert/delete/extract-top.", "<4 MB"),
    ("opt-16-patricia-trie", "OPT-16 -- Patricia Trie", "Data structure", "trie_prefix.cpp",
     "Each node stores bit position for branching. O(key_len) lookup. 60% less memory for shared prefixes.", "<8 MB"),
    ("opt-17-compact-hash-set", "OPT-17 -- Compact Hash Set", "Data structure", "compact_set.cpp",
     "Open addressing load 0.7. Quadratic probe. Keys only. 75% less memory than Python set. O(1) avg.", "<10 MB"),
    ("opt-18-bloom-filter", "OPT-18 -- Bloom Filter", "Data structure", "bitset_bloom.cpp",
     "k=3 hashes, M bits. Insert: set h1,h2,h3. Query: check all 3. Filters 95%+ redundant checks. O(k).", "<3 MB"),
    ("opt-19-sparse-bit-vector", "OPT-19 -- Sparse Bit Vector", "Data structure", "sparse_bitvec.cpp",
     "Dense for dense regions. Sparse hash for <10% fill. Rank via popcount prefix sum. 90% less when sparse.", "<1 MB"),
    ("opt-20-lock-free-ring-buffer", "OPT-20 -- Lock-Free Ring Buffer", "Data structure", "ring_queue.cpp",
     "Power-of-2 capacity. head/tail atomic uint64. mask: idx = tail & (cap-1). O(1) push/pop.", "<2 MB"),
    ("opt-21-avx2-cosine-similarity", "OPT-21 -- AVX2 Cosine Similarity", "SIMD vectorization", "simd_cosine.cpp",
     "dot = _mm256_fmadd_ps(a,b,dot). norm = fmadd. result = dot/sqrt(na*nb). 6-8x faster. O(d/8).", "<1 MB"),
    ("opt-22-avx2-topk-selection", "OPT-22 -- AVX2 Top-K Selection", "SIMD vectorization", "simd_topk.cpp",
     "Floyd's heap tournament. Final: _mm256 partial sort of K=20 survivors. 4-5x faster. O(n).", "<2 MB"),
    ("opt-23-avx2-batched-dot-product", "OPT-23 -- AVX2 Batched Dot Product", "SIMD vectorization", "simd_dotbatch.cpp",
     "Matrix-vector: _mm256_fmadd_ps(row, q, acc). 8 floats per instruction. 5-7x faster. O(n*d/8).", "<1 MB"),
    ("opt-24-avx2-hamming-distance", "OPT-24 -- AVX2 Hamming Distance", "SIMD vectorization", "simd_hamming.cpp",
     "XOR 256-bit chunks: _mm256_xor_si256. popcount via _mm_popcnt_u64. 20-30x faster. O(n/256).", "<1 MB"),
    ("opt-25-simd-string-length", "OPT-25 -- SIMD String Length", "SIMD vectorization", "simd_strlen.cpp",
     "_mm256_cmpeq_epi8 vs null. movemask. tzcnt gives position. 8-10x faster bulk. O(n/32).", "<1 MB"),
    ("opt-26-avx2-minmax-reduction", "OPT-26 -- AVX2 Min/Max Reduction", "SIMD vectorization", "simd_minmax.cpp",
     "_mm256_min_ps / _mm256_max_ps reduction tree. log2(8) passes. 6x faster. O(n/8).", "<1 MB"),
    ("opt-27-avx2-gather", "OPT-27 -- AVX2 Gather", "SIMD vectorization", "simd_gather.cpp",
     "_mm256_i32gather_ps(base, vindex, scale). 8 non-contiguous floats. 3-4x faster. O(n/8).", "<1 MB"),
    ("opt-28-varint-encoder", "OPT-28 -- Varint Encoder", "Compression", "varint_enc.cpp",
     "value < 128: 1 byte. Else emit (value & 0x7F | 0x80), shift right 7. 50-60% smaller IDs. O(n).", "<1 MB"),
    ("opt-29-delta-encoder", "OPT-29 -- Delta Encoder", "Compression", "delta_enc.cpp",
     "First value raw. Each next: emit (current - previous). Combine with varint. 80% smaller sorted lists. O(n).", "<1 MB"),
    ("opt-30-dictionary-encoder", "OPT-30 -- Dictionary Encoder", "Compression", "dict_enc.cpp",
     "Sort uniques. Assign int16 ID. Replace strings with ID arrays + table. 70-90% less memory. O(n).", "<4 MB"),
    ("opt-31-run-length-encoder", "OPT-31 -- Run-Length Encoder", "Compression", "rle_flags.cpp",
     "(value, run_length) pairs. run_length as varint. 95% compression when mostly uniform. O(n).", "<1 MB"),
    ("opt-32-float16-converter", "OPT-32 -- Float16 Converter", "Compression", "fp16_vec.cpp",
     "_cvtss_sh per float -> uint16. _cvtsh_ss back. 50% size, <0.1% precision loss. O(n).", "<2 MB"),
    ("opt-33-nibble-score-packer", "OPT-33 -- 4-Bit Score Packer", "Compression", "nibble_score.cpp",
     "byte = (s1 << 4) | s2. Unpack: s1=(b>>4), s2=(b&0xF). 87% less for 1M entries. O(n).", "<1 MB"),
    ("opt-34-lz4-block-compressor", "OPT-34 -- LZ4 Block Compressor", "Compression", "lz4_block.cpp",
     "LZ4 FAST: 64-byte hash table match finder. Literal + match offset. 60-70% smaller payloads. O(n).", "<2 MB"),
    ("opt-35-struct-of-arrays", "OPT-35 -- Struct-of-Arrays Layout", "Cache-friendly layout", "soa_candidate.cpp",
     "Split {id,score,url,text} into arrays: float scores[N], int ids[N]. 2-3x faster filter/sort. O(n).", "<10 MB"),
    ("opt-36-cache-aligned-vectors", "OPT-36 -- Cache-Aligned Vectors", "Cache-friendly layout", "padded_vec.cpp",
     "row_stride = ceil(d*4/64)*64. posix_memalign. 10-15% faster SIMD. O(n*d).", "<1 MB"),
    ("opt-37-hot-cold-split", "OPT-37 -- Hot/Cold Field Splitter", "Cache-friendly layout", "hot_cold_split.cpp",
     "Hot fields (id, score, cluster): contiguous. Cold (text, metadata): separate arena. O(n).", "<8 MB"),
    ("opt-38-cache-tiled-matrix", "OPT-38 -- Cache-Tiled Matrix Ops", "Cache-friendly layout", "tile_matrix.cpp",
     "Tile T=64. Loop: for(ii+=T) for(jj+=T) inner tile. 2-4x faster than naive. O(M*N).", "<2 MB"),
    ("opt-39-sso-string", "OPT-39 -- Small-String Optimized Container", "String optimization", "sso_string.cpp",
     "len<=22: inline 23-byte buffer. Else: {ptr, len} heap. 60% fewer allocs for anchors. O(1) short.", "<6 MB"),
    ("opt-40-string-interning", "OPT-40 -- String Interning Table", "String optimization", "str_intern.cpp",
     "Global hash map: string -> canonical pointer. intern(s) = find or insert. Compare by pointer. 30-50% less. O(1) avg.", "<10 MB"),
    ("opt-41-rope-data-structure", "OPT-41 -- Rope Data Structure", "String optimization", "rope_text.cpp",
     "Binary tree of chunks. concat = new node(left,right) O(1). Iterate leaves for full string. O(log n) index.", "<4 MB"),
    ("opt-42-suffix-array", "OPT-42 -- Suffix Array", "String optimization", "suffix_arr.cpp",
     "SA-IS O(n) construction. LCP array. Binary search on SA using LCP. 100x faster substring search.", "<20 MB"),
    ("opt-43-url-canonicalizer", "OPT-43 -- URL Canonicalizer", "String optimization", "url_canon.cpp",
     "Lowercase host. Strip trailing /. Sort query params. Remove default port. 20-30% fewer uniques. O(len).", "<4 MB"),
    ("opt-44-flatbuffers-zerocopy", "OPT-44 -- FlatBuffers Zero-Copy", "Serialization", "flatvec.cpp",
     "table Embedding {dims:uint16; data:[float32]}. Zero-copy access via offset. 10x faster than pickle. O(1) access.", "<2 MB"),
    ("opt-45-zerocopy-buffer-protocol", "OPT-45 -- Zero-Copy Buffer Protocol", "Serialization", "zerocopy_buf.cpp",
     "PyBUF_SIMPLE: return Py_buffer{buf=c_ptr, len=n*d*4} without memcpy. 50% less peak RAM. O(1).", "<1 MB"),
    ("opt-46-fast-msgpack", "OPT-46 -- Fast MessagePack", "Serialization", "msgpack_fast.cpp",
     "fixarray header + float32 per element. SIMD-copy with bswap. 5-10x faster than Python msgpack. O(n).", "<1 MB"),
    ("opt-47-lightweight-protobuf", "OPT-47 -- Lightweight Protobuf", "Serialization", "proto_lite.cpp",
     "Hand-coded varint field encoding. field_id<<3 | wire_type. No reflection. O(n).", "<1 MB"),
    ("opt-48-work-stealing-pool", "OPT-48 -- Work-Stealing Thread Pool", "Parallel processing", "worksteal_pool.cpp",
     "Deque per thread. Steal from random victim when empty. task = std::function<void()>. O(1) push/steal.", "<5 MB"),
    ("opt-49-lockfree-sharded-map", "OPT-49 -- Lock-Free Sharded Map", "Parallel processing", "lockfree_map.cpp",
     "256 shards. shard = hash(key) & 0xFF. CAS on bucket list per shard. O(1) avg.", "<10 MB"),
    ("opt-50-parallel-merge-sort", "OPT-50 -- Parallel Merge Sort", "Parallel processing", "par_merge.cpp",
     "Divide halves. Binary search for median split. Merge in parallel. O(n log n / threads).", "<10 MB"),
    ("opt-51-reader-writer-spinlock", "OPT-51 -- Reader-Writer Spinlock", "Parallel processing", "rw_spinlock.cpp",
     "Read: fetch_add(readers). Write: CAS(0 -> -1). _mm_pause() spin. O(1).", "<1 MB"),
    ("opt-52-atomic-counter", "OPT-52 -- Cache-Aligned Atomic Counter", "Parallel processing", "atomic_counter.cpp",
     "alignas(64) atomic<uint64_t>. fetch_add(1, relaxed). Prevents false sharing. O(1).", "<1 MB"),
    ("opt-53-io-uring-async-reader", "OPT-53 -- io_uring Async Reader", "I/O prefetch", "async_reader.cpp",
     "io_uring: prep_readv -> submit -> wait cqe. Overlap next read with processing. O(1) submit.", "<5 MB"),
    ("opt-54-mmap-embeddings", "OPT-54 -- Memory-Mapped Embeddings", "I/O prefetch", "mmap_embed.cpp",
     "mmap(MAP_SHARED, PROT_READ). OS page-faults only accessed rows. MADV_SEQUENTIAL. O(1) open.", "<1 MB"),
    ("opt-55-cache-prefetch", "OPT-55 -- Cache Prefetch Hints", "I/O prefetch", "prefetch_hint.cpp",
     "__builtin_prefetch(addr + 16*64, 0, 1). 16 cache lines ahead. O(1) per hint.", "<1 MB"),
    ("opt-56-buffered-writer", "OPT-56 -- Buffered Writer", "I/O prefetch", "buffered_write.cpp",
     "64 KB buffer. Flush on full. Single write() syscall. O(1) amortised append.", "<1 MB"),
    ("opt-57-page-prefault", "OPT-57 -- Page Pre-Fault", "I/O prefetch", "page_touch.cpp",
     "Sequential memset in background thread before hot path. O(pages).", "<1 MB"),
    ("opt-58-fixed-point-scoring", "OPT-58 -- Fixed-Point Scoring", "Numerical optimization", "fixedpt_score.cpp",
     "Q16.16: store as int32. Multiply: (int64(a)*b)>>16. 4x faster without FPU. O(n).", "<1 MB"),
    ("opt-59-lookup-table-sigmoid", "OPT-59 -- Lookup-Table Sigmoid", "Numerical optimization", "lut_sigmoid.cpp",
     "T[1024] for x in [-6,+6]. idx=((x+6)/12)*1024. Lerp entries. O(1) per call.", "<1 MB"),
    ("opt-60-fast-ieee754-log", "OPT-60 -- Fast IEEE754 Log2", "Numerical optimization", "fast_log.cpp",
     "log2(x) = exponent(x) + log2(mantissa). Mantissa polynomial (3 terms). O(1).", "<1 MB"),
    ("opt-61-fast-inverse-sqrt", "OPT-61 -- Fast Inverse Sqrt", "Numerical optimization", "rsqrt_norm.cpp",
     "y = 0x5f3759df - (*(int*)&x >> 1). Newton step. Then y*2 for rsqrt. O(1).", "<1 MB"),
    ("opt-62-radix-tree-url-index", "OPT-62 -- Radix Tree URL Index", "Index structure", "radix_tree.cpp",
     "Compressed trie on URL path bytes. Shared prefix = one node. O(path_len) lookup.", "<10 MB"),
    ("opt-63-bitmap-index-filter", "OPT-63 -- Bitmap Index Filter", "Index structure", "bitmap_idx.cpp",
     "One bit per item per attribute. AND bitmaps for multi-filter. popcount for count. O(n/64).", "<5 MB"),
    ("opt-64-sparse-csr-matrix", "OPT-64 -- Sparse CSR Matrix", "Index structure", "sparse_matrix.cpp",
     "CSR: values[], col_indices[], row_ptrs[]. y[i] += val*x[col]. O(nnz).", "<10 MB"),
    ("opt-65-interval-tree", "OPT-65 -- Interval Tree", "Index structure", "interval_tree.cpp",
     "Augmented BST. node.max = max endpoint. Recurse if max >= query.low. O(log n + k).", "<5 MB"),
    ("opt-66-redis-pipeline-batcher", "OPT-66 -- Redis Pipeline Batcher", "Network IPC", "redis_pipe.cpp",
     "Accumulate N=100 commands. One TCP write. Read N replies. O(1) amortised per cmd.", "<2 MB"),
    ("opt-67-postgres-copy-batcher", "OPT-67 -- PostgreSQL COPY Batcher", "SQL optimization", "pg_batch.cpp",
     "COPY FROM STDIN binary. Header + tuple data. 100x faster than INSERT per-row. O(n).", "<5 MB"),
    ("opt-68-shared-memory-ipc", "OPT-68 -- Shared Memory IPC", "Network IPC", "ipc_shm.cpp",
     "shm_open + ftruncate + mmap. Producer writes. Consumers read by offset. O(1) access.", "<10 MB"),
    ("opt-69-prepared-statement-cache", "OPT-69 -- Prepared Statement Cache", "SQL optimization", "prepared_stmt.cpp",
     "PQprepare once. PQexecPrepared per call. Skip parse+plan. O(1) per call.", "<2 MB"),
    ("opt-70-binary-result-decoder", "OPT-70 -- Binary Result Decoder", "SQL optimization", "result_codec.cpp",
     "resultFormat=1 (binary). Parse int4/float8 direct from bytes. O(n).", "<1 MB"),
    ("opt-71-incremental-content-differ", "OPT-71 -- Incremental Content Differ", "Pipeline optimization", "incr_diff.cpp",
     "Hash(content) per page. Skip if unchanged. Process only changed set. O(n) hash, O(delta) process.", "<5 MB"),
    ("opt-72-two-tier-result-cache", "OPT-72 -- Two-Tier Result Cache", "Pipeline optimization", "result_cache.cpp",
     "L1: unordered_map in-process. L2: Redis. Key = xxHash(input). O(1) lookup.", "<20 MB"),
]

for fname, title, cat, cppfile, algo, ram in OPTS:
    sig = f"// See CPP-RULES.md for interface requirements\n// Specific signatures defined during implementation"
    write_spec(fname, title, cat, cppfile, algo, sig, ram)

for args in METAS:
    write_spec(*args)

# Count what we wrote
written = len([f for f in os.listdir(SPECS_DIR) if f.startswith(('meta-', 'opt-')) and f.endswith('.md')])
print(f"Total META+OPT spec files in docs/specs/: {written}")
