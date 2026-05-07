# FR-242 — Domain adapter via Generative Pseudo-Labelling on top of BGE-M3

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Domain-adapted embedding via LoRA + GPL |
| **Settings prefix** | `EMBEDDING_DOMAIN_ADAPTER_PATH` (env var); inline constants in `domain_adapter.py` |
| **Pipeline stage** | Embed (model-loading wrapper) |
| **Helper** | `apps.pipeline.services.domain_adapter.load_adapted_model` + `should_train_adapter` + `has_trained_adapter` + `get_adapter_status` |
| **Default state** | **ON.** The loader is always called; when no LoRA adapter is present on disk, vanilla BGE-M3 passes through unchanged (Wang et al. 2022 GPL §4 minimum-data threshold — below 10K docs the adapter would be noise, so vanilla is the safe default). |

## 2 · Motivation (ELI5)

BGE-M3 was trained on the open web. Forum-specific words ("mod-hammering", brand product codes, niche slang) have weak fingerprints because the model never saw them in training. We can fine-tune the encoder on **our** content using Generative Pseudo Labelling (GPL): a query generator invents likely queries from each document, mines hard negatives from FAISS, and trains a small LoRA adapter (≈2MB of weights) on top of the frozen encoder. No labelled data needed.

The v1 scaffold ships the *loader* + cold-start fallback; the offline training pipeline ships in a focused follow-up.

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Primary** | Wang, K., Reimers, N. & Gurevych, I. (2022). *GPL: Generative Pseudo Labeling for Unsupervised Domain Adaptation of Dense Retrieval.* NAACL. arXiv:[2112.07577](https://arxiv.org/abs/2112.07577). Reports +9.3 NDCG@10 on out-of-domain BEIR. §3.2 — 3 pseudo-labels per doc. §3.3 — 50 mined hard negatives per query. §4 — 10K-doc minimum data threshold. |
| **Adapter architecture** | Hu, E. J. et al. (2021). *LoRA: Low-Rank Adaptation of Large Language Models.* arXiv:[2106.09685](https://arxiv.org/abs/2106.09685). §4.1 — `rank=8`, `alpha=16` are the size/perf tradeoff defaults. ~2MB per adapter. |
| **Few-shot alternative** | Dai, Z. et al. (2023). *Promptagator: Few-shot Dense Retrieval From 8 Examples.* ICLR. arXiv:[2209.11755](https://arxiv.org/abs/2209.11755). Faster path when labelled examples are available. |

## 4 · Output contract

`load_adapted_model(vanilla_model) -> Any`
- Always returns a usable model object.
- When `has_trained_adapter()` is False (typical fresh install): returns `vanilla_model` unchanged.
- When True but the loader stub raises (v1 raises `NotImplementedError` until the peft swap-in lands): catches, logs, returns vanilla. Pipeline continues.

`should_train_adapter(corpus_size: int) -> bool`
- True iff `corpus_size >= 10_000` (Wang 2022 GPL §4).

`has_trained_adapter() -> bool`
- True iff `<EMBEDDING_DOMAIN_ADAPTER_PATH>/adapter_config.json` exists (peft convention).

## 5 · Implementation

| File | Change |
|---|---|
| `backend/apps/pipeline/services/domain_adapter.py` | New file. ~140 lines. Pure-Python, zero deps. |
| `backend/apps/pipeline/tests_scaffolds.py::DomainAdapterTests` | 7 tests. |

Settings: `EMBEDDING_DOMAIN_ADAPTER_PATH` env var (default `/models/domain_adapter`). No DB migration; the loader is stateless.

## 6 · Test plan

7 SimpleTestCase tests:
1. **Constants locked to paper defaults** — Wang 2022 §4 + Hu 2021 §4.1.
2. **Below minimum returns False** for `should_train_adapter`.
3. **At minimum returns True**.
4. **No adapter → vanilla pass-through** (cold-start happy path).
5. **Adapter present + loader fails → vanilla fallback** (defensive).
6. **Status helper shape** — operator-visible.
7. **Env-var override** for weights path.

## 7 · Wire-in (deferred)

In `embeddings.py` near the existing `SentenceTransformer(DEFAULT_MODEL_NAME)` load:

```python
from apps.pipeline.services.domain_adapter import load_adapted_model
model = SentenceTransformer(DEFAULT_MODEL_NAME)
model = load_adapted_model(model)  # default-on; vanilla pass-through if no adapter
```

The `_attach_lora_weights` stub raises `NotImplementedError` so any
adapter file that *does* show up on disk before the v2 commit gets a
loud failure (not a silent pretend-success). When v2 ships, the stub
will be replaced with `peft.PeftModel.from_pretrained(model, path)`.

## 8 · Citations on every default

- `GPL_MIN_CORPUS_SIZE = 10_000` — Wang 2022 GPL §4.
- `LORA_RANK_DEFAULT = 8` — Hu 2021 LoRA §4.1.
- `LORA_ALPHA_DEFAULT = 16` — Hu 2021 §4.1.
- `PSEUDO_LABELS_PER_DOC_DEFAULT = 3` — Wang 2022 §3.2.
- `NEGATIVES_PER_QUERY_DEFAULT = 50` — Wang 2022 §3.3.
- `MARGIN_MSE_TEMPERATURE_DEFAULT = 1.0` — Wang 2022 §3.4.

## 9 · Status

Loader + tests + spec shipped 2026-05-07 default-on (vanilla pass-through). LoRA-attach implementation + offline training pipeline = v2 follow-up.
