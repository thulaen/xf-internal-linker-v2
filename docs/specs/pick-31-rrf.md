# Pick #31 — Reciprocal Rank Fusion (Cormack-Clarke-Büttcher 2009)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 31 |
| **Canonical name** | RRF — Reciprocal Rank Fusion |
| **Settings prefix** | `reciprocal_rank_fusion` |
| **Pipeline stage** | Score (fusion) |
| **Shipped in commit** | `6cea1ef` (PR-L, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/reciprocal_rank_fusion.py](../../backend/apps/pipeline/services/reciprocal_rank_fusion.py) |
| **Tests module** | [backend/apps/pipeline/test_reciprocal_rank_fusion.py](../../backend/apps/pipeline/test_reciprocal_rank_fusion.py) |
| **Benchmark module** | `backend/benchmarks/test_bench_rrf.py` (pending G6) |

## 2 · Motivation

We run multiple retrievers (BM25, semantic cosine, QL-Dirichlet,
graph signals). Their scores live on incomparable scales — you can't
just sum BM25 + cosine. RRF uses **ranks only**: every doc's score
is `Σ 1 / (k + rank_r(d))` summed across retrievers. Parameter-free
(save `k = 60`), handles unequal list lengths, and — per Cormack et
al. — beats Condorcet / CombSUM / CombMNZ on TREC.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Cormack, G. V., Clarke, C. L. A. & Büttcher, S. (2009). "Reciprocal rank fusion outperforms Condorcet and individual rank learning methods." *SIGIR*, pp. 758-759. |
| **Open-access link** | <https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf> |
| **Relevant section(s)** | §3 — formula; recommended k=60 from cross-validation. |
| **What we faithfully reproduce** | Formula + k=60 default. |
| **What we deliberately diverge on** | Nothing — pure arithmetic. |

## 4 · Input contract

See `apps/pipeline/services/reciprocal_rank_fusion.py`:

- **`fuse(rankings: Mapping[str, Sequence[DocId]], *, k=60,
  top_n=None) -> list[FusedItem]`**
- **`fuse_to_ids(...)` / `iter_fused(...)`** convenience wrappers.
- Empty rankings dict → `[]`.

## 5 · Output contract

- `FusedItem(doc_id, score, contributions: dict[ranker_name, float])`
- Sorted descending by score; deterministic tie-break.
- **Invariants.** `score == sum(contributions.values())`.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `reciprocal_rank_fusion.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no fusion; callers fall back to single-ranker output |
| `reciprocal_rank_fusion.k` | int | `60` | Cormack-Clarke-Büttcher §3 cross-validated default | Yes | `int(10, 300)` | Smaller = more weight to top positions |

## 7 · Pseudocode

See `apps/pipeline/services/reciprocal_rank_fusion.py`. Core:

```
function fuse(rankings, k, top_n):
    scores = defaultdict(float)
    contributions = defaultdict(dict)
    for name, ranked_list in rankings.items():
        for position, doc in enumerate(ranked_list, start=1):
            contribution = 1.0 / (k + position)
            scores[doc] += contribution
            contributions[doc][name] = contribution
    items = [FusedItem(doc, scores[doc], contributions[doc]) for doc in scores]
    items.sort(key = -score, then deterministic tie-break)
    return items[:top_n]
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/ranker.py` | Named ranked lists from BM25, semantic, QL-Dirichlet, HITS, TrustRank, PageRank | Final fused ranking |

## 9 · Scheduled-updates job

None — per-query at search time.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | Proportional to union of doc IDs across lists (~few MB per query) | — |
| Disk | 0 | — |
| CPU | ~1 µs per (doc, ranker) pair | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_single_ranker_preserves_order` | Sanity |
| `test_doc_in_multiple_lists_wins` | Fusion works |
| `test_uneven_list_lengths_ok` | Robustness |
| `test_disjoint_lists_preserve_individual_ranks` | Tie-break |
| `test_contributions_sum_to_score` | Invariant |
| `test_k_changes_score_magnitude` | Knob works |
| `test_duplicate_doc_in_one_list_only_counted_once` | Dedup |
| `test_top_n_truncates` | Cap |
| `test_invalid_k_rejected` | Validation |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 5 rankers × 100 items each | < 2 ms | > 20 ms |
| medium | 5 rankers × 10 000 items | < 200 ms | > 2 s |
| large | 5 rankers × 1 000 000 items | < 30 s | > 5 min |

## 13 · Edge cases & failure modes

- **All rankers return identical ranked lists** — fused equals the
  common list.
- **One ranker returns 1 item, another returns 10 000** — RRF handles
  fine; the short list contributes only to top-ranked.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| BM25, #28 QL-Dirichlet, semantic cosine, #29 HITS, #30 TrustRank, #36 PPR | Rankers that get fused |

| Downstream | Reason |
|---|---|
| #32 Platt calibration | Converts raw RRF score to a probability |
| #47 Kernel SHAP | Explains fused score via per-feature attribution |

## 15 · Governance checklist

- [ ] `reciprocal_rank_fusion.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-L)
- [x] Benchmark module
- [x] Test module (PR-L)
- [ ] TPE search space declared
- [ ] Ranker wired (W3)
