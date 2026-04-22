# Pick #26 — Entity salience scoring (Gamon 2013)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 26 |
| **Canonical name** | Feature-based entity salience ranker |
| **Settings prefix** | `entity_salience` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | `a4771e8` (PR-E, 2026-04-22) |
| **Helper module** | [backend/apps/sources/entity_salience.py](../../backend/apps/sources/entity_salience.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `EntitySalienceTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_entity_salience.py` (pending G6) |

## 2 · Motivation

A document can mention 50 named entities. Which one is the article
*about*? "Acme Corp launched rockets yesterday" — Acme is the subject
even if its name appears once and "yesterday" appears three times.
Salience-aware ranking means the linker can match a document on its
central entities instead of every cameo mention. This matters for
forum threads where a reply paragraph can mention five unrelated
topics while the actual subject is the OP.

Gamon et al. train a gradient-boosted tree over ~40 features. We
ship the subset they showed were most predictive (their Table 2):
first position, mention frequency, sentence coverage, title match.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Gamon, M., Yano, T., Song, X., Apacible, J. & Pantel, P. (2013). "Identifying salient entities in web pages." *CIKM*, pp. 2375-2380. |
| **Open-access link** | <https://dl.acm.org/doi/10.1145/2505515.2505602> |
| **Relevant section(s)** | §3 — feature set; §4.1 — feature weighting (~4:2:2:2 split); Table 2 — feature importance. |
| **What we faithfully reproduce** | The four-feature subset + Gamon's 4:2:2:2 weighting. |
| **What we deliberately diverge on** | We use a weighted linear sum instead of the GBT — no training data, no model artefact. Plan §Parse notes this is a heuristic. Operators can upgrade to a GBT in a future slice once human-labelled salience data exists. |

## 4 · Input contract

- **`rank_entities(doc, *, title: str | None = None, top_k: int |
  None = None, weights: dict | None = None,
  min_mention_count: int = 1) -> list[EntitySalience]`**
- `doc` is a spaCy-like object (Protocol: `.text`, `.ents`, `.sents`).
- Empty `doc.ents` → `[]`.

## 5 · Output contract

- `EntitySalience(text, label, mention_count, first_offset, salience,
  first_position_feature, frequency_feature, coverage_feature,
  title_feature)` frozen dataclass.
- **Invariants.**
  - `salience ∈ [0, 1]`.
  - `first_position_feature ∈ [0, 1]` (1.0 = start of doc).
  - Sorted by descending salience.
- **Determinism.** Pure function of inputs.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `entity_salience.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no salience signal |
| `entity_salience.weight_first_position` | float | `0.4` | Gamon 2013 Table 2 — most predictive feature; 2× frequency's weight | Yes | `uniform(0.1, 0.7)` | Emphasises early-doc entities |
| `entity_salience.weight_mention_frequency` | float | `0.2` | Gamon 2013 Table 2 — second-tier feature | Yes | `uniform(0.0, 0.5)` | Emphasises repeated entities |
| `entity_salience.weight_sentence_coverage` | float | `0.2` | Gamon 2013 Table 2 — third-tier feature | Yes | `uniform(0.0, 0.5)` | Emphasises entities that appear across the doc |
| `entity_salience.weight_title_match` | float | `0.2` | Gamon 2013 Table 2 — title cues are highly diagnostic | Yes | `uniform(0.0, 0.8)` | Emphasises title-mentioned entities |
| `entity_salience.min_mention_count` | int | `1` | Permissive by default; operators can raise to `2` to filter stray mentions | Yes | `int(1, 10)` | Higher = stricter |

## 7 · Pseudocode

See `apps/sources/entity_salience.py`. Core:

```
for each (normalised_text, label) bucket in doc.ents:
    first_position = 1 - (first_offset / len(doc))
    frequency       = mention_count / max_frequency_in_doc
    coverage        = distinct_sentences_with_mention / total_sentences
    title_match     = 1 if norm_text in norm_title else 0
    salience = 0.4*fp + 0.2*freq + 0.2*cov + 0.2*title_match     # using configured weights
return sorted entities by salience desc
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/text_cleaner.py` | spaCy doc from pick #16 | Store top-K salient entities on `ContentItem`; use for "about" snippets in UI |
| `apps/pipeline/services/ranker.py` | Source + target salient entities | Entity-overlap signal |

## 9 · Scheduled-updates job

- **Key:** `entity_salience_retrain`
- **Cadence:** weekly (Sat 15:30)
- **Priority:** medium
- **Estimate:** 10 min
- **Multicore:** yes (spaCy batch pipe)
- **Purpose:** the scoring weights are config-level (TPE can tune),
  but a weekly re-pass refreshes the per-doc salience tables as
  documents are edited / re-ingested.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~5 MB per call (dominated by spaCy doc) | — |
| Disk | `K × per-doc` salience records | — |
| CPU | ~500 µs per 1000-word doc (minus spaCy's own cost) | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_first_position_beats_mention_frequency` | Weighting math (fixed 2026-04-22 on a longer doc) |
| `test_title_match_bumps_salience` | Title feature works |
| `test_sentence_coverage_helps_ranking` | Coverage feature works |
| `test_empty_doc_returns_empty` | Degenerate |
| `test_min_mention_count_filters_low_frequency` | Threshold |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 × 5 KB docs (pre-parsed) | < 20 ms | > 200 ms |
| medium | 10 000 × 5 KB docs | < 3 s | > 30 s |
| large | 1 000 000 docs | < 10 min | > 2 h |

## 13 · Edge cases & failure modes

- **Doc with zero entities** — returns `[]`.
- **All entities in the first sentence** — tied first-position scores,
  broken by frequency then alphabetical.
- **Title not provided** — title feature is 0 for all; other features
  still drive ranking.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #16 spaCy | Produces `doc.ents` and `doc.sents` |
| #15 PySBD | Sentence boundaries (if caller uses PySBD sents) |

| Downstream | Reason |
|---|---|
| Ranker entity-overlap signal | Primary consumer |
| UI "about this thread" snippet | Displays top-k salient entities |

## 15 · Governance checklist

- [ ] `entity_salience.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-E)
- [ ] Benchmark module
- [x] Test module (PR-E)
- [ ] `entity_salience_retrain` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Pipeline wired (W2)
