# Pick #29 — HITS (Kleinberg 1999)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 29 |
| **Canonical name** | HITS — Hyperlink-Induced Topic Search |
| **Settings prefix** | `hits` |
| **Pipeline stage** | Score |
| **Shipped in commit** | `552fdd3` (PR-M, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/hits.py](../../backend/apps/pipeline/services/hits.py) |
| **Tests module** | [backend/apps/pipeline/test_graph_signals.py](../../backend/apps/pipeline/test_graph_signals.py) — `HitsTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_hits.py` (pending G6) |

## 2 · Motivation

PageRank rewards *popularity* (many incoming links). HITS separately
rewards *authority* (cited by good hubs) and *hub-ness* (citing good
authorities). For internal link graphs the distinction matters —
a FAQ page can be a great hub without being cited much, and a single
definitive reference page can be a high authority without linking
anywhere. Computing both lets the ranker pick the right signal per
context (an operator writing a FAQ wants good hubs surfaced, an
operator writing a cite-this-claim needs good authorities).

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Kleinberg, J. M. (1999). "Authoritative sources in a hyperlinked environment." *Journal of the ACM* 46(5): 604-632. |
| **Open-access link** | <https://www.cs.cornell.edu/home/kleinber/auth.pdf> |
| **Relevant section(s)** | §3 — HITS recurrence `a = A^T h`, `h = A a`; §3.3 convergence to principal eigenvectors of `A^T A` and `A A^T`. |
| **What we faithfully reproduce** | Via `networkx.hits` — NetworkX's implementation mirrors the paper's power-iteration. |
| **What we deliberately diverge on** | We wrap and return a frozen `HitsScores` dataclass with both dicts; NetworkX returns a bare tuple. |

## 4 · Input contract

- **`compute(graph: nx.DiGraph, *, max_iterations=100,
  tolerance=1e-8, normalized=True) -> HitsScores`**
- Graph must be directed (HITS has no meaning on undirected).
- Empty graph → empty scores (not an error).

## 5 · Output contract

- `HitsScores(authority: dict, hub: dict)` — both dicts have the
  same key set (all nodes). Values sum to 1.0 when `normalized=True`.
- **Invariants.**
  - Empty graph → empty dicts.
  - Undirected input → `ValueError`.
- **Determinism.** NetworkX's power iteration is deterministic;
  tolerance controls convergence.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `hits.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no authority/hub signal |
| `hits.max_iterations` | int | `100` | NetworkX default; Kleinberg 1999 §3 shows convergence within ~30 iters for typical graphs | Yes | `int(20, 500)` | Higher = more patience on dense graphs |
| `hits.tolerance` | float | `1e-8` | NetworkX default — precise enough for ranking applications | No | — | Correctness / convergence |
| `hits.normalized` | bool | `true` | Compare scores across graphs of different sizes | No | — | Output semantic |

## 7 · Pseudocode

See `apps/pipeline/services/hits.py`. Core:

```
import networkx as nx

function compute(graph, max_iter, tol, normalized):
    if not graph.is_directed(): raise ValueError("HITS requires directed graph")
    if graph.number_of_nodes() == 0: return HitsScores({}, {})
    hub, authority = nx.hits(graph, max_iter=max_iter, tol=tol, normalized=normalized)
    return HitsScores(authority=dict(authority), hub=dict(hub))
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/ranker.py` | Candidate destinations | Authority score as one of the ranking features; hub score for "best reference" detection |

## 9 · Scheduled-updates job

- **Key:** `hits_refresh`
- **Cadence:** daily 14:50
- **Priority:** high
- **Estimate:** 5 min
- **Multicore:** yes (NetworkX uses numpy)
- **RAM:** ≤ 256 MB @ 10M nodes

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~10-50 MB per 1M-node graph | networkx docs |
| Disk | N × 16 bytes per score row | — |
| CPU | 5 min daily rebuild on full graph | scheduler slot |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_returns_hits_scores_for_every_node` | Coverage |
| `test_hubs_score_highest_for_hub_like_nodes` | Semantics |
| `test_authority_score_highest_for_cited_nodes` | Semantics |
| `test_rejects_undirected_graph` | Input validation |
| `test_empty_graph_returns_empty_scores` | Degenerate |
| `test_top_authorities_returns_sorted_pairs` | Convenience API |
| `test_top_hubs_caps_at_k` | Cap |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 000-node directed graph | < 50 ms | > 500 ms |
| medium | 100 000-node graph | < 5 s | > 60 s |
| large | 10 000 000-node graph | < 10 min | > 1 h |

## 13 · Edge cases & failure modes

- **Graph with isolated components** — HITS runs independently per
  component; scores compare within-component only.
- **Highly skewed graphs** — pathological link farms get inflated
  hub scores. Pair with #30 TrustRank to dampen this effect.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| META-06 existing PageRank | Complementary popularity signal |

| Downstream | Reason |
|---|---|
| Ranker authority feature | Primary consumer |
| #31 RRF | Fuses HITS ranking with other graph signals |

## 15 · Governance checklist

- [ ] `hits.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-M)
- [ ] Benchmark module
- [x] Test module (PR-M)
- [ ] `hits_refresh` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Ranker wired (W3)
