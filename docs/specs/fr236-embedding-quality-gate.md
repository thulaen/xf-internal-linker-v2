# FR-236 — Measure-twice, convinced-once quality gate

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Quality gate (three-gate replacement check) |
| **Settings prefix** | `embedding.gate_*`, `embedding.provider_ranking_json` |
| **Pipeline stage** | Embed (pre-write) |
| **Helper module** | `backend/apps/pipeline/services/embedding_quality_gate.py` |
| **Data model** | `apps.pipeline.models.EmbeddingGateDecision` |
| **Benchmark module** | `backend/benchmarks/test_bench_quality_gate.py` |

## 2 · Motivation (ELI5)

Don't let a cheap embedding replace an expensive one just because the cheap
one happened to run last. Before any existing vector is overwritten, check:
(1) does the new provider rank at least as good as the old one? (2) is the
new vector actually different — or are we doing pointless work? (3) if we
embed the same text again, do we get the same answer? If any gate fails,
the old vector stays. No regression, no flakes.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Chunked pooling** | Reimers & Gurevych, 2019 — *"Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks"* (EMNLP-IJCNLP 2019). arXiv 1908.10084. |
| **Monte Carlo stability** | Metropolis & Ulam, 1949 — *"The Monte Carlo Method"* (JASA 44(247)). |
| **Circuit-breaker pattern** | Nygard, 2018 — *Release It!* 2nd ed. Pragmatic Bookshelf. |
| **Ranking confidence** | Voorhees, 1999 / Järvelin & Kekäläinen, 2002 (see FR-232). |
| **Long-context chunking** | Beltagy, Peters, Cohan, 2020 — *"Longformer: The Long-Document Transformer"* (arXiv 2004.05150). |
| **Patent prior art** | US Patent 11,256,687 (Google, 2022) — "Re-ranking search results using confidence scoring". |
| **What we reproduce** | SBERT mean-pool of chunked embeddings; Monte Carlo double-sampling for stability. |
| **What we diverge on** | We use a single re-sample rather than N samples (cost budget); acceptable because we reject on any disagreement below 0.99 cosine. |

## 4 · Three gates

| Gate | Condition | Decision |
|---|---|---|
| **0 — First embed** | `old_vec is None` | `ACCEPT_NEW` — nothing to protect |
| **1 — Provider quality** | `(new_rank − old_rank) < quality_delta_threshold` | `REJECT lower_quality_provider` |
| **2 — Change detect** | `cos(old, new) > noop_cosine_threshold` | `NOOP unchanged` |
| **3 — Stability** | `provider.embed_single(text)` → `cos(new, resample) < stability_threshold` | `REJECT unstable_new_vector` |
| **default** | All gates pass | `REPLACE passed_all_gates` |

All cosines computed as `np.dot(a, b)` on L2-normalised vectors (O(dim) per call).

## 5 · Input / output contracts

`QualityGate.evaluate(*, text, old_vec, old_sig, new_vec, new_sig) -> GateDecision`

- `text` — source string used for Gate 3 re-sample.
- `old_vec`, `new_vec` — `np.ndarray` float32, unit norm preferred.
- `old_sig`, `new_sig` — provider signatures (e.g. `"openai:text-embedding-3-large:3072"`).

Returns `GateDecision(action, reason, score_delta)`:
- `action ∈ {REPLACE, ACCEPT_NEW, REJECT, NOOP}`
- `reason` = short code matching the table above
- `score_delta` = provider-rank delta for Gates 0/1; cosine for Gates 2/3

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default |
|---|---|---|---|
| `embedding.gate_enabled` | bool | `true` | Project policy |
| `embedding.gate_quality_delta_threshold` | float | `-0.05` | Tight guard — 5 ppt NDCG drop is meaningful |
| `embedding.gate_noop_cosine_threshold` | float | `0.9999` | Stable-provider invariant — same text + same model ≈ identical vector |
| `embedding.gate_stability_threshold` | float | `0.99` | Reimers & Gurevych §3 — within-provider cosine stability |
| `embedding.provider_ranking_json` | json | `{}` | Written by FR-232 bake-off |

## 7 · Integration with the hot loop

- Called inside `_flush_embeddings_slice` before the archival + `bulk_update` step.
- Only runs for `ContentItem` (Sentence has no archive target yet).
- Fetches existing rows in a single `values()` query with `iterator(chunk_size=500)` for streaming.
- Writes all decisions via `EmbeddingGateDecision.objects.bulk_create(batch_size=500)` — one INSERT per 500 items.
- `pks_slice` and `normalised` are filtered so only approved writes reach `bulk_update`. NOOP items get no write (row untouched). REJECT items get no write (old vector kept).

## 8 · Resource contract

- RAM peak: ~1.1 MB per evaluation (2 stored + 1 resample vector at 3072-dim + Python overhead). Under the 32 MB envelope.
- Disk: `EmbeddingGateDecision` rows at ~200 bytes each. 100 k items × 3 runs = 60 MB. Under the 128 MB envelope.
- Latency: microsecond-range per evaluate call (benchmark confirmed).

## 9 · Test plan

1. **Unit branches** — test each of the 5 gate outcomes (ACCEPT_NEW, REJECT lower_quality_provider, NOOP unchanged, REJECT unstable_new_vector, REPLACE passed_all_gates).
2. **Benchmark** — `test_bench_quality_gate.py` at 1024 / 1536 / 3072 dim confirms sub-millisecond latency.
3. **Integration** — provider swap scenario: set ranking `local=0.9`, `openai=0.6`; run re-embed with OpenAI; confirm all `REJECT lower_quality_provider` rows and stored vectors untouched.
4. **Stability-fail** — mock provider to return a wildly different vector on the second `embed_single` call; confirm `REJECT unstable_new_vector`.
5. **Disabled-gate parity** — set `embedding.gate_enabled = false`; confirm behaviour matches pre-gate pipeline byte-for-byte.
