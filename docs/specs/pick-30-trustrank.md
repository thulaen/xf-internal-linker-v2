# Pick #30 — TrustRank (Gyöngyi-Garcia-Pedersen 2004)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 30 |
| **Canonical name** | TrustRank — seeded trust propagation |
| **Settings prefix** | `trustrank` |
| **Pipeline stage** | Score |
| **Shipped in commit** | `552fdd3` (PR-M, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/trustrank.py](../../backend/apps/pipeline/services/trustrank.py) |
| **Tests module** | [backend/apps/pipeline/test_graph_signals.py](../../backend/apps/pipeline/test_graph_signals.py) — `TrustRankTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_trustrank.py` (pending G6) |

## 2 · Motivation

PageRank treats every page as a potential source of trust. Spammers
exploit this by building link farms that vote each other up. TrustRank
starts trust at a curated seed set (trusted authorities identified by
editors or by pick #51 auto-seeder) and propagates it through the
graph — non-seed pages only receive trust via link paths from seeds.
Link farms not reachable from seeds end up with ~0 trust and get
down-ranked.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Gyöngyi, Z., Garcia-Molina, H. & Pedersen, J. (2004). "Combating web spam with TrustRank." *VLDB*, pp. 576-587. |
| **Open-access link** | <http://infolab.stanford.edu/~gyongyi/publications/vldb2004_trust.pdf> |
| **Relevant section(s)** | §2 — trust propagation model; §3 — seed selection; §4.1 — inverse-PageRank seed picker (pick #51). |
| **What we faithfully reproduce** | TrustRank as personalised PageRank with the teleport distribution concentrated on trusted seeds. |
| **What we deliberately diverge on** | Nothing algorithmic — we delegate the numerics to pick #36 (Personalized PageRank) to avoid code duplication. |

## 4 · Input contract

- **`compute(graph: nx.DiGraph, *, trusted_seeds: Iterable[Hashable],
  damping: float = 0.85, tolerance: float = 1e-6,
  max_iterations: int = 100) -> TrustRankScores`**
- Unknown seeds silently dropped.
- Empty graph → empty scores.

## 5 · Output contract

- `TrustRankScores(scores, seed_nodes, reason)`.
- `reason` is one of `empty_graph`, `no_trusted_seeds_fallback_uniform`,
  `trust_propagated_from_seeds` — for operator diagnostics.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `trustrank.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no trust signal |
| `trustrank.damping` | float | `0.85` | Page-Brin 1998 and Gyöngyi 2004 — 0.85 is the universal default | Yes | `uniform(0.6, 0.95)` | Higher = flatter distribution |
| `trustrank.tolerance` | float | `1e-6` | Delegated PPR default | No | — | Convergence precision |
| `trustrank.max_iterations` | int | `100` | Delegated PPR default | Yes | `int(30, 500)` | Higher = more patience on large graphs |

## 7 · Pseudocode

```
from apps.pipeline.services.personalized_pagerank import compute as ppr

function compute(graph, trusted_seeds, damping, tolerance, max_iter):
    if graph.number_of_nodes() == 0:
        return TrustRankScores({}, frozenset(), "empty_graph")
    seeds = {s for s in trusted_seeds if graph.has_node(s)}
    reason = "no_trusted_seeds_fallback_uniform" if not seeds else "trust_propagated_from_seeds"
    p = ppr(graph, seeds=seeds, damping=damping, tolerance=tolerance, max_iterations=max_iter)
    return TrustRankScores(p.scores, p.seed_nodes, reason)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/ranker.py` | Candidate destination ID | TrustRank score as spam-mitigation feature |

## 9 · Scheduled-updates job

- **Key:** `trustrank_propagation`
- **Cadence:** daily 15:05
- **Priority:** high
- **Estimate:** 5 min
- **Multicore:** yes
- **Depends on:** `trustrank_auto_seeder` (pick #51) + `pagerank_refresh`
- **RAM:** ≤ 256 MB @ 10M nodes

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | Same order as HITS / PageRank | — |
| Disk | N × 16 bytes per score | — |
| CPU | 5 min daily rebuild | scheduler slot |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_returns_trust_scores_for_every_node` | Coverage |
| `test_trust_flows_to_seeds_neighbours` | Propagation |
| `test_no_valid_seeds_fallback_noted` | Reason field |
| `test_empty_graph` | Degenerate |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 000 nodes × 5 seeds | < 50 ms | > 500 ms |
| medium | 100 000 nodes × 50 seeds | < 5 s | > 60 s |
| large | 10 000 000 nodes × 500 seeds | < 10 min | > 1 h |

## 13 · Edge cases & failure modes

- **No valid seeds** — falls back to uniform PageRank (reason field
  says so). Caller decides whether to accept or skip.
- **Single seed** — trust concentrates heavily on its local cluster.
  Operators should provide ≥ 20 seeds (pick #51 default).

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #36 Personalized PageRank | Delegates numerics |
| #51 Auto-Seeder | Supplies the seed set |

| Downstream | Reason |
|---|---|
| Ranker trust-score feature | Primary consumer |
| META-25 spam_guard | Complementary spam signal |

## 15 · Governance checklist

- [ ] `trustrank.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-M)
- [ ] Benchmark module
- [x] Test module (PR-M)
- [ ] `trustrank_propagation` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Ranker wired (W3)
