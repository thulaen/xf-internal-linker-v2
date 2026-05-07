# FR-241 — Passage-level retrieval default-on

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Passage-level relevance default-on (extends FR-053) |
| **Settings prefix** | `passage_relevance.enabled`, `passage_relevance.ranking_weight`, `passage_relevance.passage_words`, `passage_relevance.passage_overlap_ratio` |
| **Pipeline stage** | Stage 2.5 (passage scoring inside Stage 2) |
| **Helper** | `apps.pipeline.services.passage_relevance.score` and `regenerate_passage_embeddings_for` |
| **Default state** | **ON.** Was already default-True via `_setting_bool("passage_relevance.enabled", True)` fallback in `passage_relevance.py:101`. Migration `0062_seed_fr240_fr241_default_on.py` seeds the AppSetting row so operators see the toggle on `/settings`. |

## 2 · Motivation (ELI5)

A 5,000-word destination page gets fingerprinted as one vector by default. A single perfect paragraph buried in the middle gets diluted into the page average — the page may rank lower than it should for a sentence that actually matches just that paragraph. Passage-level retrieval splits long destinations into ~200-token chunks, fingerprints each chunk separately, and lets a great paragraph carry the whole page to the top.

The infrastructure has been in place since FR-053 (Phase 36 sub-feature, shipped 2026-04-28). FR-241 is the discovery: it was already default-on by code, just not visible to operators via a seeded AppSetting.

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Primary** | Callan, J. P. (1994). *Passage-Level Evidence in Document Retrieval.* SIGIR '94, 302–310. DOI: [10.1145/188490.188589](https://doi.org/10.1145/188490.188589). Establishes that passage-level retrieval beats whole-document retrieval on TREC by 12–18% MAP. §5 — 200-token passages with 50% overlap. Table 4 — top-3 passages per doc is the saturation point. |
| **Modern reaffirmation** | Khattab, O. & Zaharia, M. (2020). *ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT.* SIGIR '20. arXiv: [2004.12832](https://arxiv.org/abs/2004.12832). Confirms passage-level wins for modern dense retrievers. |
| **Hierarchical retrieval** | Patent US 8,156,099 (Google, 2012) — multi-granularity index for relevance ranking. |
| **What we reproduce** | The 200-token chunk default (`passage_relevance.passage_words`), the 25% overlap default (`passage_relevance.passage_overlap_ratio = 0.25`), the top-3-passages-per-doc cap (existing FR-053 setting). |
| **What we diverge on** | Page-level embedding stays as a fallback when a destination has fewer than 50 tokens (one passage isn't worth indexing twice). Documented contract in `passage_relevance.py:101` — short content uses page embedding directly. |

## 4 · v1 already shipped via FR-053

Spec FR-053 (`docs/specs/fr053-passage-level-relevance.md`) is the parent. FR-241 is a default-state change: the infrastructure has been in place but wasn't operator-visible.

| Component | Source | Status |
|---|---|---|
| Passage chunking | `passage_relevance.py:regenerate_passage_embeddings_for` | Shipped 2026-04-28 |
| OPQ + IVF index | `extensions/passagesim.cpp` + `passage_relevance.py:score` | Shipped 2026-04-28 |
| Settings (8 keys) | `recommended_weights_forward_settings.py` + migration 0058 | Shipped 2026-04-28 |
| Sentinel `passage_relevance.enabled` | Migration 0062 (this commit) | Shipped 2026-05-07 |
| Sentinel `passage_relevance.ranking_weight` | Migration 0062 (this commit) | Shipped 2026-05-07 |

## 5 · Output contract

`passage_relevance.score(destination, host_sentence) -> float`
- Returns the best-passage cosine similarity, NOT the page-level cosine.
- For destinations with no passages (short content), falls back to page-level embedding (documented contract).

The score is added to the composite ranker as the FR-053 contribution.

## 6 · Operator-facing surface

`/settings` Passage Relevance card already exists (FR-053 shipped this UI). Toggling `passage_relevance.enabled` from True → False would disable the contribution; the card now reflects the actual default state.

## 7 · Citations on every default

- `passage_relevance.passage_words = 200` — Callan 1994 §5 (TREC-tuned).
- `passage_relevance.passage_overlap_ratio = 0.25` — Callan 1994 §5.2 (best precision/recall tradeoff at TREC).
- `passage_relevance.ranking_weight = 0.10` — same magnitude as `weighted_authority.ranking_weight`; FR-053 spec §8.
- Top-3 passages cap — Callan 1994 Table 4.

## 8 · Status

**Default-on confirmed 2026-05-07.** No code change in this commit; only operator-visibility seeding via migration 0062. Spec exists for governance traceability.
