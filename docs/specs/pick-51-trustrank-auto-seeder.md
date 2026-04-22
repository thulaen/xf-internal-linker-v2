# Pick #51 — Inverse-PageRank Auto-Seeder for TrustRank

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 51 |
| **Canonical name** | Auto-seeder — pick TrustRank seeds via inverse PageRank + quality filters |
| **Settings prefix** | `trustrank_auto_seeder` |
| **Pipeline stage** | Score |
| **Shipped in commit** | `552fdd3` (PR-M, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/trustrank_auto_seeder.py](../../backend/apps/pipeline/services/trustrank_auto_seeder.py) |
| **Tests module** | [backend/apps/pipeline/test_graph_signals.py](../../backend/apps/pipeline/test_graph_signals.py) — `AutoSeederTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_auto_seeder.py` (pending G6) |

## 2 · Motivation

TrustRank (pick #30) depends on a seed set of trusted pages. Asking
an editor to hand-curate 20 trusted pages across 10 M docs is
tedious and biased. Gyöngyi 2004 §4.1 proposes **inverse PageRank**:
run PageRank on the edge-reversed graph, the top nodes are pages
that many other pages link *to* with high authority — ideal seeds.
Filter through quality gates (spam guard, post quality,
readability) to avoid seeding on link farms. Fallback to top-K
forward-PageRank when filters starve the pool.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Gyöngyi, Z., Garcia-Molina, H. & Pedersen, J. (2004). "Combating web spam with TrustRank." *VLDB*, §4.1. |
| **Open-access link** | <http://infolab.stanford.edu/~gyongyi/publications/vldb2004_trust.pdf> |
| **Relevant section(s)** | §4.1 — "Seed Selection via Inverse PageRank". |
| **What we faithfully reproduce** | The inverse-PageRank idea. |
| **What we deliberately diverge on** | Added the quality-filter cascade + fallback — operator directive to avoid spam / nonsense seeds even if they look "structurally good". |

## 4 · Input contract

- **`pick_seeds(graph, *, candidate_pool_size=100, seed_count_k=20,
  spam_flagged=None, post_quality=None, post_quality_min=0.6,
  readability_grade=None, readability_grade_max=16.0) ->
  AutoSeedResult`**

## 5 · Output contract

- `AutoSeedResult(seeds, fallback_used, rejected_count, reason)`.
- `reason` ∈ `{empty_graph, filtered_inverse_pagerank,
  fallback_to_top_k_by_pagerank}`.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `trustrank_auto_seeder.enabled` | bool | `true` | Recommended preset policy | No | — | Off = manual seed curation |
| `trustrank_auto_seeder.candidate_pool_size` | int | `100` | Plan §Auto-Seeder — top-100 by inverse PageRank | Yes | `int(50, 500)` | Larger pool survives stricter filters |
| `trustrank_auto_seeder.seed_count_k` | int | `20` | Plan §Auto-Seeder — 20 seeds balance coverage vs dilution | Yes | `int(5, 100)` | More seeds = flatter trust distribution |
| `trustrank_auto_seeder.post_quality_min` | float | `0.6` | Plan §Auto-Seeder | Yes | `uniform(0.3, 0.9)` | Stricter = fewer candidates pass |
| `trustrank_auto_seeder.readability_grade_max` | float | `16.0` | Plan §Auto-Seeder — reject gibberish / grade > 16 | Yes | `uniform(10.0, 22.0)` | Lower = rejects more dense prose |
| `trustrank_auto_seeder.refresh_cadence_days` | int | `1` | Plan — daily refresh in scheduler | Yes | `int(1, 7)` | Faster adapts to new corpus |

## 7 · Pseudocode

See `apps/pipeline/services/trustrank_auto_seeder.py`. Core:

```
function pick_seeds(graph, pool_size, k, spam, quality, quality_min, readability, readability_max):
    inverse_pr = nx.pagerank(graph.reverse(copy=False))
    candidates = top_N_by_score(inverse_pr, N=pool_size)
    survivors = []
    rejected = 0
    for node, _ in candidates:
        if node in spam: rejected += 1; continue
        if quality and quality.get(node, 1.0) < quality_min: rejected += 1; continue
        if readability and readability.get(node, 0.0) > readability_max: rejected += 1; continue
        survivors.append(node)
        if len(survivors) >= k: break
    if len(survivors) >= k:
        return AutoSeedResult(survivors, fallback_used=False, rejected_count=rejected,
                              reason="filtered_inverse_pagerank")
    # Fallback: top-k forward PageRank, skipping already-picked
    forward_pr = nx.pagerank(graph)
    for node, _ in top_by_score(forward_pr):
        if node in survivors: continue
        survivors.append(node)
        if len(survivors) >= k: break
    return AutoSeedResult(survivors, fallback_used=True, rejected_count=rejected,
                          reason="fallback_to_top_k_by_pagerank")
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/trustrank.py` | — | Reads `AppSetting["trustrank.seed_ids"]` populated by this helper |

## 9 · Scheduled-updates job

- **Key:** `trustrank_auto_seeder`
- **Cadence:** daily 15:00
- **Priority:** high
- **Estimate:** 2 min
- **Multicore:** no
- **Depends on:** `pagerank_refresh`
- **RAM:** ≤ 50 MB
- **Disk:** ≤ 50 MB (persisted seed list)

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ≤ 50 MB (graph reverse + pagerank) | — |
| Disk | ≤ 50 MB (seed list + audit trail) | — |
| CPU | 2 min daily rebuild | scheduler slot |

## 11 · Tests

All 7 `AutoSeederTests` pass — including the edge case where `nx.Graph`
(undirected) is rejected with ValueError before the empty-graph
short-circuit.

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100-node graph | < 50 ms | > 500 ms |
| medium | 100 000-node graph | < 5 s | > 60 s |
| large | 10 000 000-node graph | < 5 min | > 30 min |

## 13 · Edge cases & failure modes

- **All candidates filtered out** → fallback kicks in, fallback_used
  is `True`.
- **Empty graph** → empty seed list, reason `empty_graph`.
- **Undirected graph input** → `ValueError`.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| META-06 PageRank, META-20 post_quality, META-25 spam_guard, #19 Readability | Quality signals |

| Downstream | Reason |
|---|---|
| #30 TrustRank | Primary consumer |

## 15 · Governance checklist

- [ ] `trustrank_auto_seeder.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry (50 MB RAM / 50 MB disk)
- [x] Helper module (PR-M)
- [ ] Benchmark module
- [x] Test module (PR-M)
- [ ] `trustrank_auto_seeder` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Seed persistence to `AppSetting["trustrank.seed_ids"]` (W1)
