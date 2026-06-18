# FR-232 — Automated embedding-provider bake-off

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Provider bake-off (MTEB-style) |
| **Settings prefix** | `embedding.bakeoff_*`, `embedding.provider_ranking_json`, `embedding.recommended_provider` |
| **Pipeline stage** | Eval |
| **Helper module** | `backend/apps/pipeline/services/embedding_bakeoff.py` |
| **Celery task** | `backend/apps/pipeline/tasks_embedding_bakeoff.py` (`pipeline.embedding_provider_bakeoff`) |
| **Data model** | `apps.pipeline.models.EmbeddingBakeoffResult` |
| **Benchmark module** | `backend/benchmarks/test_bench_embedding_bakeoff.py` |

## 2 · Motivation (ELI5)

Three embedding providers (local BGE-M3, OpenAI, Gemini) all claim to be
good. We decide which is actually best *for our data* by ranking each one
against the user's own approved/rejected link history. No synthetic data —
if a reviewer has said "yes, this link is good" a thousand times, those are
our positive examples. The winner is written to a setting that the quality
gate consumes to block regressions.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **MTEB** | Muennighoff et al., 2023 — *"MTEB: Massive Text Embedding Benchmark"* (EACL 2023). arXiv 2210.07316. |
| **BEIR** | Thakur et al., 2021 — *"BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models"* (NeurIPS 2021). arXiv 2104.08663. |
| **NDCG** | Järvelin & Kekäläinen, 2002 — *"Cumulated gain-based evaluation of IR techniques"* (ACM TOIS 20(4)). |
| **TREC qrels** | Voorhees, 1999 — *"The TREC-8 Question Answering Track Report"*. |
| **Dual-encoder prior art** | US Patent 10,120,910 — "Vector-based search" (Google, 2018). |
| **Semantic search prior art** | US Patent 9,552,356 — "Embedding for semantic similarity" (Facebook, 2017). |
| **Relevant sections** | MTEB §3.1 retrieval-task metric set; NDCG eq. 4–5; BEIR §4.2 zero-shot protocol. |
| **What we reproduce** | MRR@10, NDCG@10, Recall@10 computed against qrels with binary relevance. |
| **Significance check** | Smucker, Allan, and Carterette 2007 — *A Comparison of Statistical Significance Tests for Information Retrieval Evaluation*. CIKM 2007. DOI: 10.1145/1321440.1321528. |
| **What we diverge on** | We compute cost and latency alongside quality. A provider is only promoted when the paired randomisation test shows the lead is significant, so one noisy run does not switch the live provider. |

## 4 · Input contract

`score_provider(*, provider, positives, negatives, texts, destination_pool_vectors=None)`

- **provider** — any instance satisfying the `EmbeddingProvider` Protocol.
- **positives / negatives** — `list[tuple[int, int]]` — `(host_id, destination_id)` pairs from Suggestion history.
- **texts** — `dict[int, str]` — ContentItem id → display text (title + distilled).
- **destination_pool_vectors** — optional cache across providers (not used by default).

Empty positives → returns a `BakeoffRun` with zero metrics. No error.

## 5 · Output contract

`BakeoffRun(provider_name, signature, sample_size, mrr_at_10, ndcg_at_10, recall_at_10, mean_positive_cosine, mean_negative_cosine, separation_score, cost_usd, latency_ms_p50, latency_ms_p95, verdict, p_value, loss_count, is_banned, explanation)`.

- Invariants: `0 ≤ mrr_at_10 ≤ 1`, `0 ≤ ndcg_at_10 ≤ 1`, `0 ≤ recall_at_10 ≤ 1`, `cost_usd ≥ 0`.
- Persisted via `EmbeddingBakeoffResult` with `unique_together=[job_id, provider]` — resume never duplicates.
- `update_provider_ranking()` normalises NDCG to [0, 1] and writes the map to `AppSetting("embedding.provider_ranking_json")`.
- `embedding.provider_bans_json` stores providers with two significant losses so the next automated run skips them until an operator unbans them.

## 6 · Hyperparameters

| Setting key | Type | Default | Source |
|---|---|---|---|
| `embedding.bakeoff_enabled` | bool | `true` | Project policy |
| `embedding.bakeoff_sample_size` | int | 1000 | BEIR §4.2 — 1K qrels is a representative sample |
| `embedding.bakeoff_cost_cap_usd` | float | 5.0 | Internal budget envelope |
| `embedding.provider_ranking_json` | json | `{}` | Written by `update_provider_ranking()` |
| `embedding.recommended_provider` | str | `""` | Written by the task |
| `embedding.provider_bans_json` | json list | `[]` | Smucker et al. 2007 supports paired significance testing before evaluation decisions; two losses is the conservative project safety rule. |

## 7 · Schedule + catch-up

- Beat: `crontab(minute=30, hour=14, day_of_month=1)` — monthly on the 1st at 14:30 UTC.
- Catch-up: threshold `35 × 24 = 840 h`, priority 38, pipeline queue, weight `medium`.
- Per-provider iteration is ordered so local runs first (free); an API provider's healthcheck failure skips that provider and continues.

## 8 · Resource contract

- Peak RAM: ~256 MB. The pool matrix is built once per provider and dropped — no persistent vector store on disk.
- Disk: tiny. Each `EmbeddingBakeoffResult` row ≈ 500 bytes.
- `pipeline` queue (concurrency=1) so the bake-off yields to the monthly full-sync and other Heavy work.

## 9 · Test plan

1. **Benchmark** — `test_bench_embedding_bakeoff.py` at 100 / 500 / 1 000 positives proves the scoring loop stays under 1 s at 1 000.
2. **Integration** — configure OpenAI + Gemini keys; trigger `embedding_provider_bakeoff.delay()`; verify 3 rows in `EmbeddingBakeoffResult`, unique on `(job_id, provider)`.
3. **Ranking** — after a run, check `AppSetting("embedding.provider_ranking_json")` contains NDCG map and `embedding.recommended_provider` is populated.
4. **Budget** — set `embedding.monthly_budget_usd` to a low value; confirm bake-off aborts with `BudgetExceededError` before making API calls.
5. **Decision** — run `apps/pipeline/tests_embedding_provider_eval.py`; a significant challenger win promotes, and two significant losses ban a provider until the operator unbans it.
