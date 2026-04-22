# Pick #37 — Node2Vec graph embeddings (Grover & Leskovec 2016)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 37 |
| **Canonical name** | Node2Vec — biased random-walk graph embeddings |
| **Settings prefix** | `node2vec` |
| **Pipeline stage** | Embed |
| **Shipped in commit** | **DEFERRED** — needs `node2vec` or `gensim` pip dep |
| **Helper module** | `backend/apps/ranking/graph/node2vec.py` (plan path) |
| **Tests module** | pending |
| **Benchmark module** | pending G6 |

## 2 · Motivation

Turn each node in the link graph into a 128-dim vector capturing its
structural role — nodes that are "similar in graph position" end up
near each other in embedding space. This gives the ranker a graph-
similarity feature that complements text cosine: two articles with
no shared words but many shared neighbours score high.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Grover, A. & Leskovec, J. (2016). "node2vec: Scalable feature learning for networks." *KDD*, pp. 855-864. |
| **Open-access link** | <https://arxiv.org/abs/1607.00653> |
| **Relevant section(s)** | §3.2 — biased random walks with `p` and `q` params; §4 — Skip-gram training. |
| **What we faithfully reproduce** | Use the `node2vec` PyPI package which implements biased walks + gensim Word2Vec training. |

## 4 · Input contract

- **`train(graph: nx.DiGraph, *, dimensions=128, walk_length=30,
  num_walks=200, p=1.0, q=1.0, window=10, min_count=1,
  workers=4) -> Node2VecModel`**
- Empty graph → `ValueError` (no walks possible).

## 5 · Output contract

- Model with `.wv[node_id]` → 128-dim numpy array.
- **Determinism.** Stochastic by default — set seed for reproducible
  runs.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `node2vec.enabled` | bool | `true` (once dep approved) | Recommended preset policy | No | — | Off = no graph embeddings |
| `node2vec.dimensions` | int | `128` | Grover-Leskovec §4.2 — 128 is the standard | Yes | `int(64, 512)` | Higher = more capacity, bigger DB footprint |
| `node2vec.walk_length` | int | `30` | Grover-Leskovec §4.2 | Yes | `int(10, 100)` | Longer walks see more context |
| `node2vec.num_walks_per_node` | int | `200` | Grover-Leskovec §4.2 | Yes | `int(50, 1000)` | More walks = better embedding, slower training |
| `node2vec.p_return` | float | `1.0` | Grover-Leskovec §3.2 — neutral | Yes | `loguniform(0.25, 4.0)` | p<1 encourages backtracking |
| `node2vec.q_in_out` | float | `1.0` | Grover-Leskovec §3.2 — neutral | Yes | `loguniform(0.25, 4.0)` | q<1 encourages outward exploration (structural) |
| `node2vec.window` | int | `10` | Skip-gram default | Yes | `int(3, 20)` | — |

## 7 · Pseudocode

```
from node2vec import Node2Vec

function train(graph, dimensions, walk_length, num_walks, p, q, window, workers):
    n2v = Node2Vec(graph, dimensions=dimensions, walk_length=walk_length,
                   num_walks=num_walks, p=p, q=q, workers=workers)
    model = n2v.fit(window=window, min_count=1, batch_words=4)
    return model
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/ranker.py` | Pair of node vectors | Cosine similarity as graph-structure feature |

## 9 · Scheduled-updates job

- **Key:** `node2vec_walks`
- **Cadence:** weekly (Thu 15:30)
- **Priority:** medium
- **Estimate:** 20-45 min
- **Multicore:** yes (gensim Word2Vec uses OpenMP)
- **RAM:** ≤ 128 MB @ 1M nodes
- **Disk:** 128-dim × 4 bytes × N nodes = ~500 MB at 1M nodes (large!)

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM (training) | ~128 MB @ 1M nodes | Grover-Leskovec §5 |
| Disk | 512 bytes × N nodes | — |
| CPU | 20-45 min weekly | scheduler slot |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_returns_model_with_correct_dimensions` | Shape |
| `test_similar_structural_nodes_close_in_embedding_space` | Direction |
| `test_empty_graph_raises` | Validation |
| `test_reproducible_under_seed` | Determinism |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100-node graph | < 5 s | > 60 s |
| medium | 10 000-node graph | < 2 min | > 20 min |
| large | 1 000 000-node graph | < 45 min | > 4 h |

## 13 · Edge cases & failure modes

- **Disconnected graph** — walks don't cross components; each
  component gets its own local embedding space.
- **Very sparse graph** (avg degree < 2) — walks degenerate; embeddings
  less informative.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| META-06 PageRank graph | Same adjacency |

| Downstream | Reason |
|---|---|
| Ranker graph-similarity feature | Primary consumer |

## 15 · Governance checklist

- [ ] Approve `node2vec` or `gensim` pip dep
- [ ] `node2vec.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry (big! 500 MB disk at 1M nodes)
- [ ] Helper module written
- [ ] Benchmark module written
- [ ] Test module written
- [ ] `node2vec_walks` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Ranker wired (W3)
