# Pick #16 — spaCy `en_core_web_sm` linguistic parser

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 16 |
| **Canonical name** | spaCy en_core_web_sm NER + POS + deps |
| **Settings prefix** | `spacy_pipeline` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | **REUSED** — `spacy==3.8.3` already pinned; `en_core_web_sm` downloaded in the Docker build |
| **Helper module** | [backend/apps/pipeline/services/spacy_loader.py](../../backend/apps/pipeline/services/spacy_loader.py) |
| **Tests module** | existing pipeline tests |
| **Benchmark module** | `backend/benchmarks/test_bench_spacy_pipeline.py` (pending G6) |

## 2 · Motivation

The linker needs named-entity recognition (to identify organisation,
person, and product mentions), part-of-speech tagging (so readability
formulas can count nouns/adjectives), and dependency parsing (for
some style features). spaCy's `en_core_web_sm` is the minimal model
that covers all three at ~40 MB RAM and 13 MB disk. Larger models
trade disk/RAM for ~1-2 F1 points — not worth it for our use case.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Honnibal, M. & Montani, I. (2017). "spaCy 2: Natural language understanding with Bloom embeddings, convolutional neural networks and incremental parsing." (spaCy white paper). |
| **Open-access link** | <https://spacy.io/> ; model card: <https://spacy.io/models/en#en_core_web_sm> |
| **Relevant section(s)** | spaCy docs "Pipeline Architecture"; model card accuracy table (~85 F1 NER on OntoNotes 5). |
| **What we faithfully reproduce** | We use spaCy's `nlp` pipeline as-is. Loader provides an lru-cached singleton to avoid the 500 ms+ load cost on every call. |
| **What we deliberately diverge on** | Disable components we don't use (`lemmatizer` if not needed) at load time to save RAM. Document this in the loader code. |

## 4 · Input contract

- **`get_nlp(model: str = "en_core_web_sm") -> spacy.Language`** —
  cached loader.
- **`nlp_pipe(texts: Iterable[str], batch_size: int = 64) -> Iterator[Doc]`**
  — batch processing via spaCy's `nlp.pipe()`.
- Empty strings produce empty `Doc` objects.

## 5 · Output contract

- `spacy.tokens.Doc` objects with `doc.ents`, `doc.sents` (if
  `sentencizer` component is enabled — we leave PySBD as the sentence
  splitter and only use spaCy for entities/POS/deps).
- **Determinism.** spaCy's neural models are deterministic on CPU.
- **Empty input** → empty `Doc`.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `spacy_pipeline.enabled` | bool | `true` | Recommended preset policy | No | — | Off = skip NER / POS (many downstream picks degrade) |
| `spacy_pipeline.model_name` | str | `"en_core_web_sm"` | Plan §Parse & Embed — smallest model covering all needed components | No | — | Changing to `md` / `lg` adds 40-500 MB disk; only worth it if NER F1 proves insufficient |
| `spacy_pipeline.batch_size` | int | `64` | spaCy docs — 64 is the sweet spot on CPU | Yes | `int(16, 256)` | Higher = more throughput, more RAM |
| `spacy_pipeline.disable_components` | str (comma-sep) | `""` | We keep the default pipeline | No | — | Disabling unused components (e.g. `lemmatizer`) saves ~5 MB RAM per load |
| `spacy_pipeline.n_process` | int | `1` | Single-process safest under Celery; multi-process needs start-method care on Windows | No | — | Increasing parallelises at cost of RAM duplication |

## 7 · Pseudocode

```
import spacy
from functools import lru_cache

@lru_cache(maxsize=4)
def get_nlp(model):
    nlp = spacy.load(model, disable=settings.disable_components.split(","))
    return nlp

function nlp_pipe(texts, batch_size):
    nlp = get_nlp(settings.model_name)
    yield from nlp.pipe(texts, batch_size=batch_size, n_process=settings.n_process)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/sources/entity_salience.py` (pick #26) | `doc` object | Uses `doc.ents` + `doc.sents` for ranking |
| `apps/pipeline/services/text_cleaner.py` | Batch of cleaned texts | Enriches each `ContentItem` with entity list + POS stats |
| `apps/sources/readability.py` (pick #19) | `doc` for complex-word counts | Future enhancement — current `readability.py` is stdlib-only |

**Wiring status.** Already used in production paths.

## 9 · Scheduled-updates job

None — inline per-document processing.

The **weekly `entity_salience_retrain` job** (pick #26) uses spaCy
batch-inference to rebuild salience tables.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~40 MB per loaded model + batch | spaCy docs |
| Disk | 13 MB (`en_core_web_sm`) | model card |
| CPU | ~5 ms per 1 KB of text | benchmark medium |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_loader_cached` | Singleton loader |
| `test_ents_present` | NER works |
| `test_pos_tags_present` | POS works |
| `test_empty_returns_empty_doc` | Degenerate input |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 docs × 1 KB | < 100 ms | > 1 s |
| medium | 1 000 docs × 5 KB | < 30 s | > 5 min |
| large | 100 000 docs × 5 KB | < 60 min | > 4 h |

## 13 · Edge cases & failure modes

- **Model not downloaded** — `OSError`; Docker build must include
  `python -m spacy download en_core_web_sm`.
- **Very long docs (> 1 M chars)** — spaCy's default `max_length` is
  1_000_000. We increase to 5M for forum archives.
- **Memory pressure under parallel Celery workers** — each worker
  has its own loaded model. Budget accordingly when scaling.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #13 NFKC | Normalised text |
| #15 PySBD | spaCy is called per sentence batch in some paths |

| Downstream | Reason |
|---|---|
| #26 Entity salience | Primary consumer |
| #19 Readability | Future POS-based features |

## 15 · Governance checklist

- [ ] `spacy_pipeline.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Loader module (existing)
- [ ] Benchmark module
- [x] Test coverage (existing pipeline tests)
- [ ] Entity-salience wiring via spaCy `Doc` objects (W2)
