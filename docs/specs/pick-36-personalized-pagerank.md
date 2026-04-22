# Pick #36 — Personalized PageRank (Haveliwala 2002)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 36 |
| **Canonical name** | Personalized PageRank — topic-sensitive authority |
| **Settings prefix** | `personalized_pagerank` |
| **Pipeline stage** | Score |
| **Shipped in commit** | `552fdd3` (PR-M, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/personalized_pagerank.py](../../backend/apps/pipeline/services/personalized_pagerank.py) |
| **Tests module** | [backend/apps/pipeline/test_graph_signals.py](../../backend/apps/pipeline/test_graph_signals.py) — `PersonalizedPageRankTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_personalized_pagerank.py` (pending G6) |

## 2 · Motivation

Standard PageRank assigns one global score per node. Personalized
PageRank (PPR) biases the random-walk teleport toward a caller-
specified seed set — producing scores "from that topic's
perspective". Same recurrence, different teleport vector. Haveliwala
2002 shows topic-sensitive PageRank vectors can be pre-computed
offline and linearly blended at query time for any topic mix.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Haveliwala, T. H. (2002). "Topic-sensitive PageRank." *WWW*, pp. 517-526. |
| **Open-access link** | <http://www-cs-students.stanford.edu/~taherh/papers/topic-sensitive-pagerank.pdf> |
| **Relevant section(s)** | §2 — PPR recurrence; §3 — pre-compute + blend strategy. |
| **What we faithfully reproduce** | `networkx.pagerank(personalization=...)`. |
| **What we deliberately diverge on** | Expose a `build_seed_personalization` helper for the common uniform-over-seeds case; normalise custom weights internally. |

## 4 · Input contract

- **`compute(graph, *, seeds, damping=0.85, tolerance=1e-6,
  max_iterations=100, seed_weights=None) ->
  PersonalizedPageRankScores`**
- Unknown seeds silently dropped. No valid seeds → fallback to
  un-personalised.

## 5 · Output contract

- `PersonalizedPageRankScores(scores, seed_nodes)`.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `personalized_pagerank.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no PPR |
| `personalized_pagerank.damping` | float | `0.85` | Haveliwala 2002 / Page-Brin 1998 | Yes | `uniform(0.6, 0.95)` | Higher = flatter |
| `personalized_pagerank.tolerance` | float | `1e-6` | networkx default | No | — | Convergence precision |
| `personalized_pagerank.max_iterations` | int | `100` | networkx default | Yes | `int(30, 500)` | More patience on large graphs |

## 7 · Pseudocode

See `apps/pipeline/services/personalized_pagerank.py`. Core:

```
import networkx as nx

function compute(graph, seeds, damping, tolerance, max_iter, seed_weights):
    validate directed graph, damping in (0,1)
    seed_set = {s for s in seeds if graph.has_node(s)}
    if not seed_set: personalization = None
    elif not seed_weights: personalization = uniform_over(seed_set)
    else: personalization = normalise(filter(seed_weights to seed_set))
    scores = nx.pagerank(graph, alpha=damping, personalization=personalization, ...)
    return PersonalizedPageRankScores(dict(scores), frozenset(seed_set))
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/ranker.py` | Topic seeds | Per-topic authority signal |
| `apps/pipeline/services/trustrank.py` | Trusted seeds | Shared numerics for TrustRank |

## 9 · Scheduled-updates job

- **Key:** `personalized_pagerank_refresh`
- **Cadence:** daily 14:40
- **Priority:** high
- **Estimate:** 8 min
- **Multicore:** yes
- **Depends on:** `pagerank_refresh`
- **RAM:** ≤ 256 MB @ 10M nodes

## 10 · Resource budget

Same order as HITS / TrustRank — ~10-50 MB per 1M-node graph.

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_returns_scores_for_every_node` | Coverage |
| `test_biases_toward_seeds` | Semantics |
| `test_unknown_seeds_silently_dropped` | Defensive |
| `test_no_valid_seeds_falls_back_to_uniform` | Fallback |
| `test_damping_out_of_range_rejected` | Validation |
| `test_build_seed_personalization_uniform` | Helper works |
| `test_build_seed_personalization_drops_unknown` | Helper defensive |
| `test_custom_seed_weights_respected` | Weight pass-through |

## 12 · Benchmark inputs

Same as HITS — 1K / 100K / 10M node graphs.

## 13 · Edge cases & failure modes

- **Disconnected seeds** — trust/topic mass stranded in their
  component; not necessarily bad but surprising.
- **All-zero custom weights** — fallback to uniform.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| Topic classifier / #30 TrustRank seeds | Seed source |

| Downstream | Reason |
|---|---|
| Ranker topical-authority feature | Primary consumer |
| #30 TrustRank | Delegates numerics here |

## 15 · Governance checklist

- [ ] `personalized_pagerank.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-M)
- [ ] Benchmark module
- [x] Test module (PR-M)
- [ ] `personalized_pagerank_refresh` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Ranker wired (W3)
