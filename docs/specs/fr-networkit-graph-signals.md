# FR — NetworKit graph-structure signals for internal-link suggestions

[SPEC FRESHNESS: reviewed_at=2026-06-07 next_review=2026-06-30]

[SPEC CITED: feature=networkit-graph-signals kind=academic_paper id=doi:10.1017/nws.2016.20 verified_at=2026-06-07]
[SPEC CITED: feature=link-prediction kind=academic_paper id=doi:10.1002/asi.20591 verified_at=2026-06-07]
[SPEC CITED: feature=community-louvain kind=academic_paper id=doi:10.1088/1742-5468/2008/10/P10008 verified_at=2026-06-07]
[SPEC CITED: feature=betweenness kind=academic_paper id=doi:10.1080/0022250X.2001.9990249 verified_at=2026-06-07]
[SPEC CITED: feature=node2vec kind=academic_paper id=doi:10.1145/2939672.2939754 verified_at=2026-06-07]
[SPEC CITED: feature=submodular-coverage kind=academic_paper id=doi:10.1007/BF01588971 verified_at=2026-06-07]

> **Phase NK — Graph-structure signals.** Add the NetworKit network-analysis library as an
> **offline, Python-side** signal source for the `graph` module, producing **10 graph-structural
> signals** that feed the link-suggestion ranker as registered, Optuna-tunable features. This is
> NOT a hot-path change: NetworKit runs in a scheduled batch job, writes versioned signal rows, and
> the Rust `ranking_core` consumes those rows as features (§F boundary preserved). Built DRY + KISS +
> TDD; every signal is wired end-to-end and default-on, never a stub.

---

## 0. Why (the gap) and the boundary

Internal linking is a directed graph: **nodes = `content.ContentItem`**, **edges = `graph.ExistingLink`**
(`from_content_item → to_content_item`). The ranker today scores candidate links from content/semantic
signals plus a few structural ones (`pagerank` Rust kernel, `trustrank_auto_seeder`, co-occurrence/PMI).
It does **not** exploit most of the link graph's structure. NetworKit (a network-analysis toolkit with a
fast native core and a Python API — Staudt, Sazonovs & Meyerhenke 2016, doi:10.1017/nws.2016.20) closes
that gap at scale.

**Architecture boundary (binds this phase — §F of the two-language plan):**
- **Python owns** the NetworKit computation: it is **offline / batch only**, lives in the `graph`
  module, runs on a Celery-beat schedule, and writes versioned signal rows. NetworKit is a **third-party
  Python dependency** (its native core is internal to the package, like NumPy's) — it is NOT first-party
  C++/Go and does not violate ADR 0007.
- **Rust owns** live scoring + activation: `ranking_core` reads the precomputed signal rows as features;
  `ranking_governance` governs whether each signal's weight is active. NetworKit **never live-scores**.
- **Optuna** (offline, `ranking_train`) tunes the signal weights via the existing `tunable_registry`.

## 1. Sources of truth (source-backed — no guessing)

- NetworKit toolkit & algorithms: Staudt, Sazonovs, Meyerhenke, *NetworKit: A Tool Suite for Large-scale
  Complex Network Analysis*, Network Science 2016, **doi:10.1017/nws.2016.20**; docs <https://networkit.github.io>.
- Link prediction: Liben-Nowell & Kleinberg 2007, **doi:10.1002/asi.20591**; Adamic & Adar 2003,
  **doi:10.1016/S0378-8733(03)00009-1**.
- Community detection (Louvain / PLM): Blondel et al. 2008, **doi:10.1088/1742-5468/2008/10/P10008**.
- Betweenness: Brandes 2001, **doi:10.1080/0022250X.2001.9990249**; structural holes: Burt, *Structural
  Holes*, 1992, ISBN 978-0674843714.
- PageRank: Page, Brin, Motwani, Winograd 1999 (Stanford InfoLab 1999-66); Katz centrality: Katz 1953,
  **doi:10.1007/BF02289026**; eigenvector centrality: Bonacich 1972, **doi:10.1080/0022250X.1972.9989806**.
- k-core: Seidman 1983, **doi:10.1016/0378-8733(83)90028-X**; Batagelj & Zaveršnik 2003, **arXiv:cs/0310049**.
- Local clustering: Watts & Strogatz 1998, **doi:10.1038/30918**.
- Node embeddings: Grover & Leskovec, *node2vec*, KDD 2016, **doi:10.1145/2939672.2939754**.
- Greedy submodular max-coverage (group-closeness seed selection): Nemhauser, Wolsey & Fisher 1978,
  **doi:10.1007/BF01588971**.
- Crawl depth & internal links for discoverability: Najork & Wiener, *Breadth-first crawling yields
  high-quality pages*, WWW 2001, **doi:10.1145/371920.371965**.

## 2. The 10 signals (5 originally-named gaps + 5 more) — each → a suggestion improvement

Each signal maps to a concrete improvement, a NetworKit algorithm, a citation, and where it enters the
ranker. `node` signals are per-`ContentItem`; `pair` signals are per-(source,target) candidate.

| # | Signal | Kind | NetworKit | Improves suggestions by | Cite |
|---|---|---|---|---|---|
| 1 | **Structural link prediction** (Adamic-Adar, common-neighbors, Jaccard-neighbourhood) | pair | `linkprediction.*` | Generating *candidate missing links* from link structure (pairs that share neighbours but don't link yet) | LN-K 2007 |
| 2 | **Community / topic cluster** (PLM/Louvain) | node (cluster id) + pair (same/diff) | `community.PLM` | Boosting within-cluster links and surfacing under-connected **bridge** links between related clusters | Blondel 2008 |
| 3 | **Betweenness (bridge / structural hole)** | node | `centrality.Betweenness` / `EstimateBetweenness` | Prioritising links that strengthen weak bridges (authority flow + crawlability) | Brandes 2001; Burt 1992 |
| 4 | **Reach & click-depth** (BFS/SSSP from hub seeds) | node (depth, inbound-reachable) | `distance.BFS` / `MultiTargetDijkstra` | Prioritising inbound links to **orphans** and pages buried deep from hubs | Najork 2001 |
| 5 | **Multi-centrality authority panel** (eigenvector, Katz, closeness — additive to the existing Rust PageRank) | node | `centrality.EigenvectorCentrality` / `KatzCentrality` / `Closeness` | Richer authority signal than PageRank alone for "link FROM authority TO under-linked" | Bonacich 1972; Katz 1953 |
| 6 | **k-core / core-periphery** | node (core number) | `centrality.CoreDecomposition` | Integrating **periphery** pages (low core number) that the site under-links | Seidman 1983; Batagelj 2003 |
| 7 | **Connected-component / island id** | node (component id, is-main) | `components.WeaklyConnectedComponents` / `StronglyConnectedComponents` | Bridging **disconnected islands** back to the main component (discoverability) | Tarjan 1972 |
| 8 | **Local clustering coefficient (triangle-closing)** | node | `centrality.LocalClusteringCoefficient` | Suggesting **triangle-closing** links in sparse neighbourhoods (A→B, A→C ⇒ B↔C) | Watts-Strogatz 1998 |
| 9 | **Structural node embedding (node2vec)** | node (vector) + pair (cosine) | `embedding.Node2Vec` | "Structurally similar pages" suggestions complementing the existing *semantic* similarity | Grover-Leskovec 2016 |
| 10 | **Group-closeness max-coverage seeds** | site-level set + per-node membership | `centrality.GroupCloseness` / greedy submodular | Ranking the highest-impact *source* pages to add links from (max reach / min click-depth per link) | Nemhauser 1978 |

**Signals 1–5** are the five originally-named gaps (link prediction, communities, bridges,
orphan/click-depth, scale-grade authority). **Signals 6–10** are the five additional ones.

## 3. DRY / overlap analysis (mandatory — no duplicates)

- **Reuse the graph, don't rebuild it.** The NetworKit graph is built **once per run** directly from
  `graph.ExistingLink` (active edges) over `content.ContentItem` ids → a `networkit.Graph` via an integer
  node-id map. No new edge store; `LinkFreshnessEdge`/`ExistingLink` remain the source of truth.
- **Do NOT duplicate PageRank.** The production hot-path PageRank stays the Rust `pagerank` kernel. Signal
  5 adds *eigenvector / Katz / closeness* (which we do **not** have) — NetworKit is configured to **skip**
  PageRank. A one-off offline NetworKit-vs-Rust PageRank parity check is run once for validation only.
- **Do NOT duplicate TrustRank or co-occurrence.** `trustrank_auto_seeder` (seeded trust propagation) and
  co-occurrence/PMI (content co-mention) are **content/seed** signals; signals 1–10 are **pure link
  structure**. They are complementary inputs, registered alongside, not replacing.
- **Reuse the signal plumbing.** Signals register through the existing `diagnostics/signal_registry.py`
  and become Optuna-tunable weights via `suggestions/tunable_registry.py` — the same path `pagerank`/
  `trustrank` use. No new ranker; the ranker reads new feature columns.
- **Reuse the no-duplicates storage pattern** (NO-DUPLICATES.md): every signal row is keyed by
  `(graph_hash, signal_version)` with skip-if-unchanged + supersede + retention.

## 4. Data model (versioned, no-duplicates)

New, in the `graph` module (FKs to `content.ContentItem` are allowed cross-module per ADR 0003):

- **`GraphSignalRun`** — one row per recompute: `graph_hash` (sha256 of the sorted active edge list),
  `signal_version` (int, bumped when an algorithm/params change), `node_count`, `edge_count`,
  `status` (`computing|current|superseded`), `computed_at`, `params_json`. Skip-if-unchanged: if a
  `current` run already has this `graph_hash` + `signal_version`, the job no-ops.
- **`NodeGraphSignal`** — per `(run, content_item)`: the node signals 2–8,10 (community_id, betweenness,
  click_depth, eigenvector, katz, closeness, core_number, component_id, is_main_component,
  local_clustering, group_seed_rank) + a `node2vec` vector (pgvector column). Unique
  `(run, content_item)`; superseded runs pruned past retention.
- **`LinkPredictionCandidate`** — per `(run, from_item, to_item)`: signal 1 scores (adamic_adar,
  common_neighbors, jaccard) + signal 9 embedding-cosine + signal 2 same/bridge flags. Only the top-K per
  source are persisted (KISS — bounded growth). Feeds candidate generation.

All three follow `(content_hash≈graph_hash, signal_version)` supersede + retention; bounded growth is
explicit (top-K candidates, single `current` run). Default-on seed values via `get_or_create`.

## 5. Wiring (end-to-end, not cosmetic)

1. **Dependency:** add `networkit` to `backend/requirements*.txt` and the backend image (Docker-managed,
   FUTURE-READY-TESTING-TOOLS rule — the test/coverage/lint wiring discovers the new `graph/services/`
   code). Pin the version; a smoke import test guards it.
2. **Builder:** `graph/services/networkit_graph.py` — `build_nk_graph()` maps `ExistingLink` → `nk.Graph`
   (pure, unit-testable in `SimpleTestCase`, no DB needed for the algorithm functions).
3. **Signal computors:** `graph/services/signals/<signal>.py` — one small pure function per signal
   (≤50 lines), each taking `(nk_graph, node_map)` and returning a dict/array. KISS + independently
   testable.
4. **Orchestrator + job:** `graph/services/graph_signal_job.py` builds the graph once, runs all 10
   computors, writes a `GraphSignalRun` + rows (skip-if-unchanged). Registered as a Celery-beat
   scheduled task (`scheduled_updates`), `--dry-run` supported (H.25).
5. **Registry + ranker features:** register all 10 in `diagnostics/signal_registry.py`; expose them to
   `pipeline/services/ranker.py` as feature columns read from `NodeGraphSignal`/`LinkPredictionCandidate`;
   add default-on, non-zero weights to `suggestions/tunable_registry.py` (DEFAULT-ON-RULE) so Optuna tunes
   them. The §G registry-driven Optuna search space (already built) picks them up automatically.
6. **Candidate generation:** `LinkPredictionCandidate` (signals 1+9) feeds the suggestion candidate set,
   so the engine can propose *structurally-likely missing links*, not only content-matched ones.
7. **Public API surface:** the `graph` module's `api.py` exposes `latest_node_signal(item)` and
   `link_prediction_candidates(item)` for cross-module reads (boundary rule).
8. **Truthful states (§F):** when no `current` run exists, the ranker treats graph signals as
   `rebuild-required` (neutral weight), never a fake zero; a repair command recomputes.

## 6. TDD plan (DRY + KISS + TDD — every signal proven)

- **Per signal:** a focused test over a small hand-built `nk.Graph` (≈6–8 nodes) with **hand-computed
  expected values** (e.g. Adamic-Adar of a known triad; betweenness of a known bridge; core numbers of a
  known k-core; component ids of two islands). RED first → implement the computor → GREEN. Test layers per
  TDD-STRICT: edge cases (empty graph, single node, self-loop, disconnected), latency budget on a
  synthetic 10k-edge graph, smoke (job writes rows), e2e (signal appears as a ranker feature).
- **Parity:** signal 5's optional NetworKit-vs-Rust-PageRank check is a one-off validation test, not a
  production path.
- **No-duplicates:** a test proves re-running with an unchanged `graph_hash` no-ops (skip-if-unchanged).
- **Default-on:** a test proves all 10 weights seed non-zero (DEFAULT-ON-RULE) and that a new signal is
  auto-included in the Optuna search space.
- Python tests run on the Dell quality path; coverage target ≥95% on the new `graph/services/` code.

## 7. Business-logic checklist & ranking gates (addressed before code)

- **Patent/paper support:** §1 (every signal cited). **Duplicate/overlap:** §3. **Regression risk:** the
  ranker gains feature columns that default to tunable weights — existing presets unchanged until Optuna
  proposes + Rust governance + GUI approval promote them (no silent ranking change). **Architecture
  alignment:** §0 (Python offline / Rust governs). **Conflicts:** none — additive signals.
- **Ranking Gate A/B:** new signals + weights; all are registry-driven, never-zero, Optuna-tuned,
  governance-gated for activation — satisfied by §5.

## 8. Build order (phase steps, each independently green + TDD'd)

1. Dependency + `build_nk_graph()` + smoke import (foundation).
2. Data model (`GraphSignalRun`, `NodeGraphSignal`, `LinkPredictionCandidate`) + migration + no-dup test.
3. Signals 1–5 (the named gaps): computors + TDD + registry + tunable weights.
4. Signals 6–10 (the additional gaps): same.
5. Orchestrator + Celery-beat job + skip-if-unchanged + dry-run.
6. Ranker wiring + candidate generation + `graph/api.py` surface + e2e test.
7. Default-on seeds + Optuna auto-inclusion + coverage ≥95% + the business-logic/ranking-gate proof.

## 9. Honest scope notes / risks

- **Dependency weight:** `networkit` ships a native core (~tens of MB). Justified by the 10 signals + scale;
  if the link graph is small (<~10k pages) the same signals are computable, just less essential — they
  still add value (link prediction, communities, embeddings are *not* size-dependent wins).
- **node2vec (signal 9)** is the heaviest; it is gated behind a config flag and a size threshold so small
  graphs skip it (KISS), but it is implemented and tested, not stubbed.
- **Sequencing:** this phase touches `graph/`, `analytics/`, `suggestions/tunable_registry.py`, and lightly
  `pipeline/services/ranker.py`. It is built **after / fenced from** the in-flight C++→Rust kernel
  migration (which owns `rust/`, `backend/extensions/`, and the pipeline kernel-callers) to avoid edit
  collisions.
