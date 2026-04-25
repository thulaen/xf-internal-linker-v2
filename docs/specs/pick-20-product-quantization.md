# Pick #20 — Product Quantization for embedding compression

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 20 |
| **Canonical name** | Product Quantization (Jégou, Douze, Schmid 2011) |
| **Settings prefix** | `product_quantization` |
| **Pipeline stage** | Embed |
| **Shipped in commit** | `a4771e8` (PR-E, 2026-04-22) — helper skips gracefully when `faiss` not installed |
| **Helper module** | [backend/apps/sources/product_quantization.py](../../backend/apps/sources/product_quantization.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `ProductQuantizationTests` (skipped if `faiss` not present) |
| **Benchmark module** | `backend/benchmarks/test_bench_product_quantization.py` (pending G6) |

## 2 · Motivation

BGE-M3 embeddings are 1024-dim × 4 bytes = 4 KB per document. At 10 M
docs that's 40 GB of vectors — too big for RAM, cold-cache SSD fetches
dominate query latency. Product Quantization splits the 1024-dim
vector into M sub-vectors, learns K codebook centroids per sub-vector,
and encodes each sub-vector as its nearest centroid ID. With M=8,
K=256 (1 byte per sub-vector), every 4 KB vector becomes 8 bytes —
500× compression with ~1-3 % recall loss per Jégou et al. §5.2.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Jégou, H., Douze, M. & Schmid, C. (2011). "Product quantization for nearest neighbor search." *IEEE Transactions on Pattern Analysis and Machine Intelligence* 33(1): 117-128. Also INRIA patents EP2457184, US8805122. |
| **Open-access link** | <https://hal.inria.fr/inria-00514462> |
| **Relevant section(s)** | §2 — PQ encoding/decoding; §3 — asymmetric distance computation (ADC) for search; §5.2 — M/K trade-off showing M=8, K=256 yields ~1 % recall loss on SIFT1M. |
| **What we faithfully reproduce** | Call `faiss.IndexPQ(dimension, M, nbits_per_code)` — Faiss's PQ is the paper's reference implementation. |
| **What we deliberately diverge on** | Nothing algorithmic. Wrapper adds: guarded import (Faiss optional), `trained_state()` / `load_state()` helpers for persistence, and `encode_batch` / `decode_batch` that operate on plain numpy arrays so callers don't need Faiss types. |

## 4 · Input contract

- **`ProductQuantizer(dimension: int, m_subvectors: int = 8,
  ks_centroids_per_subvector: int = 256)`**
- **`.fit(training_vectors: np.ndarray)`** — `(N, dim)`. Needs at
  least ~K × 10 training vectors per sub-vector (Faiss warns below).
- **`.encode(vectors: np.ndarray) -> np.ndarray`** — `(N, dim) →
  (N, m_subvectors)` of `uint8`.
- **`.decode(codes: np.ndarray) -> np.ndarray`** — `(N, m_subvectors)
  → (N, dim)` reconstructed floats.

## 5 · Output contract

- Encoded: `uint8` matrix.
- Decoded: float32 matrix, ≈ input up to PQ quantization noise.
- **Invariants.**
  - `len(encoded) == len(input)` on encode.
  - `input.shape[1] == dimension` or `ValueError`.
  - Decode round-trip error ≤ 5 % per-component mean on typical
    BGE-M3 outputs.
- **Determinism.** Faiss training is deterministic with a seed; we
  expose `seed` on the ctor.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `product_quantization.enabled` | bool | `true` (pending Faiss install) | Recommended preset policy | No | — | Off = store full-precision embeddings |
| `product_quantization.dimension` | int | `1024` | BGE-M3 output dim | No | — | Correctness |
| `product_quantization.m_subvectors` | int | `8` | Jégou §5.2 — M=8 optimal for 1024-dim | Yes | `int(4, 32)` | Higher M = finer quantization, bigger code size |
| `product_quantization.ks_centroids_per_subvector` | int | `256` | Jégou §5.2 — 8 bits per code = 256 centroids | No | — | Correctness (bytes-per-code = `ceil(log2(K)/8)`) |
| `product_quantization.training_sample_size` | int | `200000` | Faiss docs — 200K random samples enough for K=256 | Yes | `int(50000, 1000000)` | Training time vs codebook quality |
| `product_quantization.seed` | int | `42` | Reproducibility | No | — | Fix for comparable runs |

## 7 · Pseudocode

```
import faiss
import numpy as np

class ProductQuantizer:
    def fit(self, training_vectors):
        self.index = faiss.IndexPQ(self.dimension, self.m, 8)  # 8 bits = K=256
        if len(training_vectors) > self.training_sample_size:
            idx = np.random.default_rng(self.seed).choice(len(training_vectors),
                                                          self.training_sample_size)
            training_vectors = training_vectors[idx]
        self.index.train(training_vectors.astype("float32"))
        self.trained = True

    def encode(self, vectors):
        return self.index.sa_encode(vectors.astype("float32"))

    def decode(self, codes):
        return self.index.sa_decode(codes)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/embeddings.py` | BGE-M3 output | Encode before DB write; decode on similarity-search load |
| `apps/pipeline/services/faiss_index.py` | Compressed codes | FAISS IndexPQ used directly when `enabled` |

## 9 · Scheduled-updates job

- **Key:** `product_quantization_refit`
- **Cadence:** monthly
- **Priority:** medium
- **Estimate:** 30 min
- **Multicore:** yes (Faiss uses OpenMP)
- **Why monthly:** the codebook needs refit when embedding
  distribution drifts (new corpus topics). A monthly rebuild balances
  quality vs training cost.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM (training) | ~200 MB for 200 K × 1024-dim training set | Faiss docs |
| RAM (encoding) | ~5 MB per 100 K docs | — |
| Disk | ~1 MB (codebook = K × M × dim/M × 4 bytes = 256 × 1024 × 4 = 1 MB) | — |
| CPU | ~30 min monthly rebuild on full corpus | scheduler slot |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_requires_faiss_or_raises` | Import-guard sanity |
| `test_encode_decode_round_trip_close` | Within 5 % error |
| `test_training_converges_on_synthetic_gaussian` | Basic functionality |
| `test_wrong_dimension_raises` | Input validation |
| `test_trained_state_round_trip` | Persistence |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 000 × 1024 train + 10 000 encode | < 5 s | > 60 s |
| medium | 200 000 train + 1 000 000 encode | < 3 min | > 15 min |
| large | 1 000 000 train + 10 000 000 encode | < 30 min | > 2 h |

## 13 · Edge cases & failure modes

- **Faiss not installed** — helper raises at `.fit()`. Import is
  guarded so module import always succeeds; dashboard shows the pick
  as inactive.
- **Untrained encode** — `RuntimeError`; caller must `.fit()` first
  or load a prior `trained_state`.
- **Too-small training set** — Faiss warns but proceeds; codebook
  quality suffers. Minimum enforced at ~10 × K × M.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| BGE-M3 embedder | Produces the vectors PQ compresses |

| Downstream | Reason |
|---|---|
| Faiss IVF-PQ / HNSW-PQ search | PQ codes replace full vectors at search time |

## 15 · Governance checklist

- [ ] `product_quantization.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-E)
- [x] Benchmark module
- [x] Test module (PR-E, skipped when Faiss absent)
- [x] `product_quantization_refit` scheduled job registered (W1)
- [ ] TPE search space declared
- [x] Embeddings pipeline wired (W2)
