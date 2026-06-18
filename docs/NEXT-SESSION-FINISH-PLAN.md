# Finish-Everything Plan — Next Session (Python + Rust backend, NetworKit, full close-out)

> **How to use this file when vibe-coding with an LLM.** Paste **§0 FRAMEWORK** once at the
> start of a working session, then paste **exactly one slice** and let the model finish it
> end-to-end before moving on. Each slice is self-contained: it states its goal, boundaries,
> the decision (ADR) and product intent (PRD), the source-backed spec, the files, the BDD test
> cases, the edge cases, the libraries to reuse, the resource budget (memory / CPU / disk /
> parallelism / helper-PC routing), and the mandatory code review that closes it. Do the slices
> **in order** — later slices depend on earlier ones. Never start the next slice until the
> current one is green, reviewed, and committed.

---

## §0. FRAMEWORK (paste this first, every session)

### 0.1 Where we are
The C++→Rust kernel migration is **done** (23 kernels + the `ranking_decision_engine` crate are all
Rust; backend boots healthy). A large amount of work is **staged on `master` but not committed**
(~428 files). The remaining work is: land the staged baseline, build NetworKit end-to-end, fold the
Go services to Python, strip the dead-language tooling, materialize the modular-monolith `api.py`
boundaries, raise coverage to 95%, and clear a handful of stragglers. This plan finishes all of it.

### 0.2 The three machines (helper-PC support — applies to every slice)
- **MSI (this Windows host) = consumer only.** It RUNS the app and observability stack; it **cannot
  build or test** — two guards (`.claude/hooks/block-msi-build-test.py`,
  `.claude/hooks/block-local-docker-build.py`) hard-block local builds/tests/quality there.
- **Dell = the build + test machine.** All Rust compiles, Python tests, coverage, mutation, and image
  builds run here.
- **Mint = storage + profiling helper** (NFS, registry mirror, Pyroscope). Not a primary worker.
- **Commands you will use everywhere:**
  - Rust build/test/clippy: `/usr/bin/bash scripts/dell-rust.sh <cargo-args>` (e.g. `test -p <crate>`,
    `clippy -p <crate> --all-targets -- -D warnings`, `fmt --check`). Always Git-Bash full path
    `/usr/bin/bash`; bare `bash` is broken WSL bash.
  - Python tests on Dell: `XF_PYTEST_SPLIT=1 python scripts/run_pytest_on_context.py --targets <paths>`.
  - Python quality (ruff/mypy/bandit/coverage/mutmut): `docker --context dell run --rm
    xf-linker-backend-quality:latest <tool> ...` (NEVER `docker compose run backend-quality` on MSI).
  - Image build: `python scripts/smart_build.py --target <service>` (routes Dell/Mint; if you hit a
    transient Dell SSH "Connection reset" mid-build, just retry).
  - Runtime management commands (NOT `test`) on the live backend are allowed on MSI:
    `docker compose exec -T backend python manage.py <cmd>`.

### 0.3 The kernel-`.so` recovery ritual (only if a slice rebuilds a Rust kernel)
The `/opt/xf/compiled/active/extensions` store is root-owned, and the non-root backend can't write
its boot-time activation temp files (`PermissionError on .activate-*.so`). `chmod` is forbidden. After
any kernel `.so` change: (1) stage it via `XF_SYNC_NO_RESTART=1 /usr/bin/bash
scripts/sync-rust-kernels-from-dell.sh <kernel>` (the stager runs as root); (2) refresh the manifest as
root with the **host backend mounted** so it builds nothing and writes "current":
```
MSYS_NO_PATHCONV=1 docker run --rm --user 0 \
  -v xf-internal-linker-v2_compiled_artifacts:/opt/xf/compiled \
  -v "$(pwd)/backend:/app" -v "$(pwd):/repo" \
  -e XF_COMPILED_ARTIFACT_ROOT=/opt/xf/compiled -e REPO_ROOT=/repo -w /app \
  xf-linker-backend-runtime:latest python /repo/scripts/ensure_compiled_artifacts.py
```
then `docker compose restart backend` and poll `docker ps ... xf_linker_backend` until `(healthy)`.
`EXTENSION_NAMES` in `scripts/ensure_compiled_artifacts.py` MUST stay an explicit `set()` (an empty
`{}` is a dict and crashes boot).

### 0.4 Universal engineering rules (every slice obeys these)
- **TDD, strict Red→Green→Refactor.** Write the failing test first and *observe it fail*, write the
  minimum code to pass, then refactor while green. Test code is held to production standard. Cite Beck,
  *Test-Driven Development by Example*, 2002 (ISBN 978-0321146533).
- **KISS.** Simplest thing that works. No speculative abstraction. ≤50 lines/function, ≤1500/file,
  ≤10 cyclomatic complexity, ≤7 args, ≤4 nesting levels.
- **DRY.** Search the codebase before writing anything new; reuse or extend. No duplicated 6+ line block.
- **Spec-first.** No code without a source-backed spec in `docs/specs/<id>.md` citing a patent / DOI /
  RFC / standard, with a current-month `[SPEC FRESHNESS: reviewed_at=YYYY-MM-DD next_review=...]`.
- **Default-on + no-duplicates.** New features/weights/signals default ON with a non-zero seed; every
  per-artefact table uses the `(content_hash, signal_version)` skip-if-unchanged + supersede + retention
  pattern with bounded growth.
- **No-deferral.** Anything you decide not to do is filed (don't silently drop it); but in this plan,
  the slices *are* the work — do them.
- **Plain English** in commit messages and any human-facing surface; define every acronym.

### 0.5 Resource discipline (the memory / CPU / disk / parallel block in each slice)
- **Memory:** never hold an unbounded collection. Graph signal rows are bounded by top-K + retention.
  NetworKit's native graph is O(nodes+edges) — fine for this site's scale; gate `node2vec` behind a
  size threshold. Use `apps/pipeline/services/hardware_profile.py` for batch sizes — never hardcode.
- **CPU:** NetworKit parallelizes internally (OpenMP); cap its threads to
  `hardware_profile.cpu_cores // 2` so Celery workers keep headroom (mirror the Polars startup cap in
  `apps.core.apps.CoreConfig`). Heavy batch jobs run on Dell/Mint, never block the request path.
- **Disk:** pre-flight any large write with `apps/pipeline/services/disk_pressure.require_free_disk()`.
  Prune superseded signal runs past retention.
- **Parallel:** offline signal computors over one graph can run concurrently; use Celery groups/canvas
  (cite Celery docs) — but each signal is deterministic and idempotent so retries are safe.
- **Helper PCs:** all tests/builds/coverage/mutation on Dell; heavy graph batch jobs may be scheduled to
  Dell/Mint; MSI only runs the live app + the scheduled trigger.

### 0.6 Mandatory code review (closes EVERY slice — do not skip)
After GREEN + static + lint, review the diff and answer, in writing, all of:
1. **Matches the spec?** Every requirement and BDD case implemented; citations honored.
2. **Errors handled?** Every failure path has an explicit branch (no bare `except`, no silent skip,
   no fake "all good" state). Truthful frontend states (ready / empty / blocked / rebuild-required /
   access-denied).
3. **No spaghetti / no verbose / no over-engineering?** Functions small and single-purpose; names
   self-documenting; no dead code, no premature generalization, no copy-paste.
4. **DRY + reuse honored?** No duplicate of existing code; shared helpers used.
5. **Resource budget respected?** Bounded growth; no unbounded loops/tables; hardware-aware.
6. **Tests real?** Red was observed; tests assert behavior (not just "it runs"); edge cases covered;
   coverage ≥ target; static analysis + lint clean.
Log the review as the repo's code-review lesson (`manage.py log_code_review_lessons`) and only then
commit. **One slice = one commit** through the full pre-commit gauntlet, never `--no-verify`.

### 0.7 Per-slice template (what every slice below contains)
`Goal · Boundaries · ADR · PRD · Spec (cited) · Files · Requirements · BDD test cases · Edge cases ·
Libraries (reuse/new) · Resources (mem/CPU/disk/parallel/helper) · Implementation (TDD/KISS/DRY) ·
Verify (unit + static + lint) · Code review`.

---

# GROUP A — Baseline: land what's already built, then a quick fix

## Slice A1 — New-session start + verify the landed kernel state
**Goal:** confirm the migration really landed and the tree is in a known state before touching anything.
**Boundaries:** read-only verification + the session-start ritual; change no source.
**ADR:** none (verification slice).
**PRD:** the operator must know, in plain English, that all 24 Rust kernels load, the backend is
healthy, and what is staged-but-uncommitted, before building further.
**Spec:** repo session-start protocol (`AI-CONTEXT.md` Session Gate); no external citation needed.
**Files:** none modified.
**Requirements:** run `python scripts/session_start_payload.py`; read the latest `AGENT-HANDOFF.md`
entry (the 2026-06-07 one); confirm `docker ps` shows `xf_linker_backend (healthy)`; confirm
`python .githooks/check-cpp-lifecycle.py` exits 0; list `git status --short | wc -l`.
**BDD test cases:**
- *Given* a fresh session, *When* the start payload runs, *Then* it prints the markers and the handoff
  summary without error.
- *Given* the backend container, *When* status is checked, *Then* it reports `(healthy)`.
- *Given* the kernels, *When* one imports (`docker compose exec -T backend python -c "import
  extensions.scoring as s; print(s.__file__)"`), *Then* the path ends in bare `.so` (Rust), not
  `.cpython-*.so`.
**Edge cases:** backend mid-restart (retry the health check); a kernel reporting `cpp` runtime_path
(run the §0.3 recovery).
**Libraries:** none new.
**Resources:** trivial; no Dell needed.
**Implementation:** no TDD (read-only). Record findings in the session's handoff entry.
**Verify:** the three BDD checks pass.
**Code review:** confirm the state matches the handoff; flag any drift.

## Slice A2 — Land the staged kernel-migration + infra baseline (clean working tree)
**Goal:** commit the existing ~428 staged files as honest, test-proved subsystem commits so the tree is
clean and every later slice commits cleanly.
**Boundaries:** commit only what's already staged; write no new features here. Touch `AGENT-HANDOFF.md`,
the commit markers, and the staged files' proof only.
**ADR:** record that the kernel migration + infra hardening land as a series of honest subsystem commits
(rust/, scripts/, .githooks/, .claude/, docs/), never one mega-commit, never `--no-verify`.
**PRD:** the repo owner needs `master` to reflect the completed migration so collaborators and CI see it.
**Spec:** the repo's commit-ritual rules (`AGENTS.md` Trigger discipline; the gauntlet hooks).
**Files (modify):** `AGENT-HANDOFF.md` (closing entry + per-file proof markers); re-stage the migration
files in subsystem groups.
**Requirements:** pre-flight every gate first — `COMMIT_SCOPE_PATHS=$(python scripts/commit_scope.py
paths --mode staged) python .githooks/check-<gate>.py </dev/null` for each hook — collect ALL failures,
fix them, then commit once per subsystem. Satisfy the 30-AutoIssue + 10-paper-trail quotas
(reconciliation mode). Per-touched-file TDD / coverage / code-review markers as the hooks require.
**BDD test cases:**
- *Given* the staged migration, *When* the pre-commit chain runs, *Then* it passes with no `--no-verify`.
- *Given* a committed subsystem, *When* `git log` is read, *Then* the commit carries the required proof
  markers.
- *Given* all subsystems committed, *When* `git status` runs, *Then* the tree is clean.
**Edge cases:** a stale `test_xf_linker` DB blocking coverage (drop the held DB); a surviving mutant on a
changed line (strengthen the test); a gate demanding a marker (add it honestly).
**Libraries:** reuse `scripts/commit_scope.py`, the existing hook suite.
**Resources:** mutation/coverage on Dell (turbo); serialize the scoped-mutation runs.
**Parallel/helper:** route mutation to Dell for speed.
**Implementation:** commit smallest coherent subsystem first (`rust/extensions/*`), then
`scripts/ensure_compiled_artifacts.py` + `setup.py`, then `.githooks/` + `.claude/`, then `docs/`.
Auto-iterate on each hook block until green.
**Verify:** `git status` clean; each commit passed the chain.
**Code review:** confirm no functional code was tagged trivial; markers are honest; no gate bypassed.

## Slice A3 — Pagerank divide-by-zero guard (+ regression test)
**Goal:** make `pagerank_step_core` match its sibling and the C++ reference by guarding the normalization.
**Boundaries:** touch ONLY `rust/extensions/pagerank/src/lib.rs` (+ its tests). Then the §0.3 restage.
**ADR:** the un-guarded division was a parity miss vs the C++ kernel; the guard restores parity and
prevents a divide-by-zero panic on a degenerate graph.
**PRD:** the ranker's PageRank signal must never panic on an empty/degenerate link graph.
**Spec:** Page, Brin, Motwani, Winograd 1999 (PageRank, Stanford InfoLab 1999-66) — the canonical guard
`if total_mass > 0.0`.
**Files (modify):** `rust/extensions/pagerank/src/lib.rs`.
**Requirements:** in `pagerank_step_core`, wrap the `*value /= total_mass` loop in `if total_mass > 0.0
{ ... }`, identical to `personalized_pagerank_step_core`.
**BDD test cases:**
- *Given* a degenerate graph (damping 0, ranks summing to 0, no dangling nodes), *When*
  `pagerank_step_core` runs, *Then* it returns without panicking and leaves values unchanged.
- *Given* a normal graph, *When* a step runs, *Then* the output equals the pre-guard output (no
  regression).
**Edge cases:** single-node graph; all-zero rank vector; fully-connected small graph.
**Libraries:** none new.
**Resources:** Dell `cargo test -p pagerank`; one `.so` restage via §0.3.
**Implementation (TDD):** add the failing degenerate-graph test (Red) → add the guard (Green) →
`clippy -D warnings` clean.
**Verify:** `/usr/bin/bash scripts/dell-rust.sh test -p pagerank` + `clippy -p pagerank ... -D warnings`;
restage + backend healthy.
**Code review:** parity with the sibling function; guard is the documented C++ form; no new branches
elsewhere.

---

# GROUP B — NetworKit Phase NK (offline graph signals → suggestion ranker)

> Cross-slice spec: `docs/specs/fr-networkit-graph-signals.md` (already written). Library:
> `networkit==11.0` (installed + verified on Dell). Graph builder
> `backend/apps/graph/services/networkit_graph.py` already exists + tested. All NK slices are **offline
> Python in the `graph` module**; Rust governs activation; Optuna tunes weights (§F boundary). DRY: the
> graph is built once from `graph.ExistingLink`; PageRank stays the Rust kernel (NetworKit skips it);
> signal #9 reuses the existing `node2vec` package.

## Slice NK-1 — Versioned signal data model + migration
**Goal:** the three tables that hold graph signals, with the no-duplicates pattern.
**Boundaries:** touch ONLY `backend/apps/graph/models.py`, a new migration, and the model tests.
**ADR:** signals are stored as versioned snapshots keyed by `(graph_hash, signal_version)`; only one
`current` run exists; superseded runs are pruned past retention; per-pair candidates are bounded top-K.
**PRD:** the ranker needs fast per-page and per-pair structural features that survive restarts and never
grow unbounded.
**Spec:** the repo's `NO-DUPLICATES.md` pattern; pgvector for the node2vec column (pgvector docs).
**Files (create/modify):** `backend/apps/graph/models.py` (+ `GraphSignalRun`, `NodeGraphSignal`,
`LinkPredictionCandidate`); `backend/apps/graph/migrations/000X_graph_signals.py`;
`backend/apps/graph/tests_graph_signal_models.py`.
**Requirements:** `GraphSignalRun(graph_hash, signal_version, node_count, edge_count, status
[computing|current|superseded], computed_at, params_json)`; `NodeGraphSignal(run FK, content_item FK,
+ the node signals + a pgvector embedding col)` unique `(run, content_item)`; `LinkPredictionCandidate(run
FK, from_item FK, to_item FK, adamic_adar, common_neighbors, jaccard, embed_cosine, same_community,
is_bridge)` with a per-source top-K cap. FK `on_delete` set explicitly (Rule H22). All cross-module FKs
to `content.ContentItem` are allowed (ADR 0003).
**BDD test cases:**
- *Given* a graph_hash + signal_version, *When* a second `current` run with the same key is created,
  *Then* the unique/skip logic prevents a duplicate.
- *Given* a node signal row, *When* it is saved, *Then* `(run, content_item)` is unique.
- *Given* >K candidates for a source, *When* persisted, *Then* only the top-K survive.
**Edge cases:** a content item deleted mid-run (CASCADE); an empty graph (a run with 0 nodes is valid);
NaN/inf guards on float columns.
**Libraries:** reuse pgvector (already a dep); Django models.
**Resources:** bounded growth (top-K + single current run + retention); migration is metadata-only.
**Implementation (TDD):** model tests Red → models + migration → Green. `manage.py makemigrations`
(on the live backend, allowed) then test on Dell.
**Verify:** `XF_PYTEST_SPLIT=1 python scripts/run_pytest_on_context.py --targets
backend/apps/graph/tests_graph_signal_models.py`; `manage.py check`; ruff/mypy on Dell.
**Code review:** FK on_delete present; bounded growth enforced; no-dup pattern correct; truthful nullability.

## Slice NK-2 — Orchestrator skeleton + DB→graph adapter
**Goal:** read `ExistingLink` → build the NetworKit graph once → create a `GraphSignalRun`, with
skip-if-unchanged.
**Boundaries:** new `backend/apps/graph/services/graph_signal_job.py` + its test; reuse the existing
`networkit_graph.build_nk_graph`.
**ADR:** the graph is built exactly once per run and shared by all signal computors; the run is skipped
when `graph_hash` (sha256 of the sorted active edge list) + `signal_version` already match a `current` run.
**PRD:** recomputation must be cheap when the link graph hasn't changed and must never double-run.
**Spec:** content-addressed skip-if-unchanged (`NO-DUPLICATES.md`); sha256 (FIPS 180-4).
**Files (create):** `backend/apps/graph/services/graph_signal_job.py`,
`backend/apps/graph/tests_graph_signal_job.py`.
**Requirements:** `load_active_edges()` (selector over `ExistingLink` active edges → list of (from_id,
to_id) + the isolated content-item ids); `graph_hash(edges)`; `run_signals(force=False)` that builds the
graph, opens a `computing` run (or skips), and returns the run + the `(graph, id_to_idx, idx_to_id)`.
**BDD test cases:**
- *Given* an unchanged graph with a `current` run, *When* `run_signals()` is called, *Then* it no-ops and
  logs "unchanged".
- *Given* a changed graph, *When* `run_signals()` runs, *Then* a new `computing` run is created and the
  prior `current` is marked `superseded` on completion.
- *Given* the active edges, *When* the graph is built, *Then* node/edge counts match the deduped edge set.
**Edge cases:** zero active links (valid empty run → ranker treats signals as `rebuild-required`); a huge
graph (log node/edge counts; honor disk pre-flight before writing rows in NK-8).
**Libraries:** reuse `build_nk_graph`; Django selectors.
**Resources:** the graph is the only big in-memory object; cap NetworKit threads (§0.5).
**Parallel/helper:** the job runs on a Celery worker (Dell-schedulable); read-only DB query, batched.
**Implementation (TDD):** test the skip + hash + counts Red → implement → Green.
**Verify:** Dell pytest; ruff/mypy.
**Code review:** single build; skip logic correct; no N+1 query on the edge load (use `.values_list`).

## Slice NK-3 — Signal 1: structural link prediction (candidate generator)
**Goal:** score candidate missing links (Adamic-Adar, common-neighbors, Jaccard-neighbourhood) and persist
the top-K per source.
**Boundaries:** new `backend/apps/graph/services/signals/link_prediction.py` + test; writes
`LinkPredictionCandidate` rows.
**ADR:** link prediction is the structural candidate-generator; it proposes pairs that share neighbours but
don't yet link, complementing the content/semantic candidate path.
**PRD:** the suggestion engine should propose "pages that should link but don't" from link structure, not
only content matching.
**Spec:** Liben-Nowell & Kleinberg 2007 (doi:10.1002/asi.20591); Adamic & Adar 2003
(doi:10.1016/S0378-8733(03)00009-1). Use NetworKit `linkprediction.AdamicAdarIndex`,
`CommonNeighborsIndex`, `JaccardIndex`.
**Files (create):** `signals/link_prediction.py`, `tests_signal_link_prediction.py`.
**Requirements:** pure function `compute_link_prediction(graph, id_to_idx, idx_to_id, top_k)` →
list of dicts `{from_id, to_id, adamic_adar, common_neighbors, jaccard}`, top-K by Adamic-Adar per source,
excluding existing edges and self-pairs.
**BDD test cases:**
- *Given* a triad where A→C and B→C exist but A↔B don't, *When* link prediction runs, *Then* (A,B) scores
  > 0 on common-neighbors (hand-computed) and appears as a candidate.
- *Given* an existing edge, *When* prediction runs, *Then* it is excluded from candidates.
- *Given* >K candidates for a source, *When* persisted, *Then* exactly K survive, highest first.
**Edge cases:** isolated node (no candidates); a node with thousands of neighbours (cap work, still top-K);
ties broken deterministically by `(from_id, to_id)`.
**Libraries:** NetworKit `linkprediction`; no new dep.
**Resources:** prediction over a large neighbourhood is the heaviest signal — bound by top-K and a
per-source neighbour cap; runs on Dell/Mint batch.
**Implementation (TDD):** hand-compute Adamic-Adar for a 5-node fixture → assert exact (Red→Green).
**Verify:** Dell pytest; ruff/mypy.
**Code review:** exact-value assertions; existing edges excluded; bounded; deterministic ties.

## Slice NK-4 — Signals 2 & 3: communities (Louvain) + betweenness (bridges)
**Goal:** assign each page a community id and a betweenness score; flag bridge pages.
**Boundaries:** new `signals/community.py` + `signals/betweenness.py` + tests; writes `NodeGraphSignal`
fields + the `same_community`/`is_bridge` flags on candidates.
**ADR:** communities drive within-cluster reinforcement + bridge suggestions; betweenness ranks
structural-hole/bridge value.
**PRD:** suggestions should prefer within-topic links and under-connected bridges between related topics.
**Spec:** Blondel et al. 2008 (Louvain, doi:10.1088/1742-5468/2008/10/P10008) via NetworKit
`community.PLM`; Brandes 2001 (betweenness, doi:10.1080/0022250X.2001.9990249) via
`centrality.Betweenness` / `EstimateBetweenness`; structural holes — Burt 1992 (ISBN 978-0674843714).
**Files (create):** `signals/community.py`, `signals/betweenness.py`, their tests.
**Requirements:** `compute_communities(graph) -> dict[node_idx, community_id]`;
`compute_betweenness(graph) -> dict[node_idx, score]` (use the exact algorithm for small graphs, the
estimator above a node threshold); a helper to set `same_community`/`is_bridge` on candidate pairs.
**BDD test cases:**
- *Given* two dense clusters joined by one bridge node, *When* Louvain runs, *Then* the two clusters get
  distinct community ids.
- *Given* the same graph, *When* betweenness runs, *Then* the bridge node has the highest score (hand-
  reasoned).
- *Given* a candidate pair in the same community, *When* flagged, *Then* `same_community=True`.
**Edge cases:** a fully-connected graph (one community); a disconnected graph (per-island communities);
the estimator threshold boundary.
**Libraries:** NetworKit `community`, `centrality`.
**Resources:** betweenness is O(V·E) exact — switch to `EstimateBetweenness` above a node threshold from
`hardware_profile`; parallel internally.
**Implementation (TDD):** two-cluster + bridge fixture; assert distinct communities + the bridge's
top betweenness.
**Verify:** Dell pytest; ruff/mypy.
**Code review:** estimator threshold justified; deterministic community labelling (seed); flags correct.

## Slice NK-5 — Signals 4 & 5: reach/click-depth (BFS) + multi-centrality panel
**Goal:** compute click-depth from hub seeds + orphan flags, and the eigenvector/Katz/closeness panel.
**Boundaries:** new `signals/reach.py` + `signals/centrality_panel.py` + tests.
**ADR:** click-depth + orphan detection prioritise inbound links to buried pages; the multi-centrality
panel adds authority signals PageRank alone misses (eigenvector, Katz, closeness) — **NetworKit does NOT
recompute PageRank** (that stays the Rust kernel).
**PRD:** the ranker should boost links that pull orphans/deep pages closer to hubs, and link from
genuinely authoritative pages.
**Spec:** Najork & Wiener 2001 (crawl depth, doi:10.1145/371920.371965) via `distance.BFS` /
`MultiTargetBFS`; eigenvector — Bonacich 1972 (doi:10.1080/0022250X.1972.9989806); Katz 1953
(doi:10.1007/BF02289026); closeness — `centrality.Closeness` / `ApproxCloseness`.
**Files (create):** `signals/reach.py`, `signals/centrality_panel.py`, their tests.
**Requirements:** `compute_click_depth(graph, hub_seeds) -> dict[node_idx, depth]` (+ `inbound_reachable`,
`is_orphan` = in-degree 0); `compute_centrality_panel(graph) -> dict[node_idx, {eigenvector, katz,
closeness}]`.
**BDD test cases:**
- *Given* a hub and a chain hub→A→B, *When* click-depth runs, *Then* A=1, B=2.
- *Given* a node with no inbound links, *When* reach runs, *Then* `is_orphan=True`.
- *Given* a star graph, *When* the panel runs, *Then* the centre has the highest closeness (hand-reasoned).
**Edge cases:** unreachable nodes (depth = ∞ → a documented sentinel + `inbound_reachable=False`); no hub
seeds configured (use top-PageRank pages from the Rust kernel as seeds, default-on); Katz non-convergence
guard.
**Libraries:** NetworKit `distance`, `centrality`.
**Resources:** BFS from K seeds is cheap (multi-source); closeness uses the approximate variant above a
threshold.
**Implementation (TDD):** chain + star fixtures with hand-computed depths/closeness.
**Verify:** Dell pytest; ruff/mypy.
**Code review:** sentinel for unreachable handled everywhere downstream; seed-selection default-on; no
PageRank duplication.

## Slice NK-6 — Signals 6,7,8,10: k-core, components, local clustering, group-closeness
**Goal:** the four remaining per-node/site structural signals in one cohesive slice.
**Boundaries:** new `signals/core_components.py` (k-core + components), `signals/clustering.py`,
`signals/group_seeds.py` + tests.
**ADR:** k-core finds the periphery to integrate; components find islands to bridge; local clustering finds
triangle-closing opportunities; group-closeness ranks the highest-impact *source* pages to link from.
**PRD:** the engine should integrate peripheral pages, bridge disconnected islands, suggest triangle-closing
links, and rank which pages, if linked-from, most reduce site-wide click-depth.
**Spec:** Seidman 1983 + Batagelj-Zaversnik 2003 (k-core, arXiv:cs/0310049) via
`centrality.CoreDecomposition`; Tarjan 1972 (components, doi:10.1137/0201010) via
`components.WeaklyConnectedComponents`/`StronglyConnectedComponents`; Watts-Strogatz 1998 (clustering,
doi:10.1038/30918) via `centrality.LocalClusteringCoefficient`; Nemhauser-Wolsey-Fisher 1978 (greedy
submodular, doi:10.1007/BF01588971) via `centrality.GroupCloseness`.
**Files (create):** `signals/core_components.py`, `signals/clustering.py`, `signals/group_seeds.py`, tests.
**Requirements:** `compute_core_numbers`; `compute_components` (component id + `is_main_component`);
`compute_local_clustering`; `compute_group_closeness_seeds(graph, k)` → ranked source-page set + per-node
`group_seed_rank`.
**BDD test cases:**
- *Given* a 3-core embedded in a sparser graph, *When* k-core runs, *Then* the core nodes get core_number
  3 (hand-computed).
- *Given* two disconnected islands, *When* components run, *Then* they get different component ids and only
  the larger is `is_main_component`.
- *Given* A→B and A→C with no B↔C, *When* clustering runs, *Then* A's neighbourhood is flagged
  triangle-closeable.
**Edge cases:** single node (core 0, its own component); a complete graph (clustering 1.0); group-closeness
on a disconnected graph (per-component seeds).
**Libraries:** NetworKit `centrality`, `components`.
**Resources:** all are near-linear except group-closeness (greedy submodular, bound k from
`hardware_profile`); parallel internally.
**Implementation (TDD):** k-core + two-island fixtures with hand-computed values.
**Verify:** Dell pytest; ruff/mypy.
**Code review:** exact core numbers; deterministic component ids; group-k bounded.

## Slice NK-7 — Signal 9: node2vec structural embedding (REUSE existing package)
**Goal:** structural-similarity embeddings + per-pair cosine, reusing the repo's existing `node2vec`.
**Boundaries:** new `signals/structural_embedding.py` + test; **reuse** the existing
`apps/pipeline/services/node2vec_embeddings.py` / `node2vec` package — do NOT add NetworKit's embedding.
**ADR:** structural similarity complements the existing *semantic* similarity; node2vec is already a
dependency (Pick #37), so we reuse it rather than duplicating with NetworKit's `embedding.Node2Vec`.
**PRD:** "structurally similar pages" become a related-pages suggestion source alongside semantic matches.
**Spec:** Grover & Leskovec 2016 (node2vec, doi:10.1145/2939672.2939754).
**Files (create):** `signals/structural_embedding.py`, its test. **Reuse:**
`apps/pipeline/services/node2vec_embeddings.py`.
**Requirements:** build node2vec embeddings from the link graph; write the pgvector column on
`NodeGraphSignal`; compute `embed_cosine` for candidate pairs; gate behind a config flag + a node-count
threshold (KISS — small graphs skip it but it is implemented + tested).
**BDD test cases:**
- *Given* two structurally-equivalent nodes, *When* embeddings are computed, *Then* their cosine is high
  (relative assertion, fixed seed).
- *Given* a graph below the size threshold, *When* the signal runs, *Then* it is skipped cleanly and rows
  record "skipped: below threshold" (truthful state, not a fake zero).
**Edge cases:** disconnected graph (walks stay within components); seed fixed for determinism; threshold
boundary.
**Libraries:** **reuse** `node2vec` (existing); pgvector.
**Resources:** node2vec is the heaviest signal — flag-gated + threshold-gated; runs on Dell/Mint batch;
embedding dim bounded.
**Implementation (TDD):** seeded small-graph fixture; assert relative cosine ordering + the skip path.
**Verify:** Dell pytest; ruff/mypy.
**Code review:** confirm REUSE (no NetworKit-embedding duplication); skip path truthful; seed fixed.

## Slice NK-8 — Celery-beat job: compute-all + persist + skip-if-unchanged + retention
**Goal:** wire the 10 computors into the orchestrator, persist rows transactionally, and schedule it.
**Boundaries:** finish `graph_signal_job.py`; add a `scheduled_updates` job; add a `--dry-run` management
command; writes the signal tables.
**ADR:** one scheduled run builds the graph once, runs all signals (parallelizable), writes rows in a
transaction, flips the run to `current`, supersedes the prior, and prunes past retention.
**PRD:** signals refresh automatically when the link graph changes, bounded and idempotent.
**Spec:** Celery canvas (Celery docs) for parallel signal tasks; `NO-DUPLICATES.md` retention.
**Files (modify/create):** `graph_signal_job.py`,
`backend/apps/graph/management/commands/recompute_graph_signals.py` (with `--dry-run`),
`backend/apps/scheduled_updates/jobs.py` (register the beat job), tests.
**Requirements:** `disk_pressure.require_free_disk()` before the bulk write; `bulk_create` the rows;
transaction wraps the flip-to-`current` + supersede + prune; the job is idempotent (re-run no-ops on an
unchanged graph).
**BDD test cases:**
- *Given* a changed graph, *When* the job runs, *Then* a `current` run with all signals exists and the
  prior run is `superseded`.
- *Given* the same graph, *When* the job re-runs, *Then* it no-ops.
- *Given* runs older than retention, *When* the job completes, *Then* they are pruned.
**Edge cases:** a signal computor raising (the run is rolled back, status `failed`, logged loudly — no
half-written `current`); disk pressure (abort before writing); empty graph (a valid empty `current` run).
**Libraries:** Celery, Django transactions, reuse `disk_pressure`, `hardware_profile`.
**Resources:** the heavy part; cap threads; schedule to Dell/Mint; bounded writes; pre-flight disk.
**Parallel:** run the cheap node signals concurrently via a Celery group; keep the heavy ones sequential.
**Implementation (TDD):** job test with a fixture DB graph; assert the full lifecycle + rollback on a
forced computor error.
**Verify:** Dell pytest; `manage.py recompute_graph_signals --dry-run` on the live backend.
**Code review:** transactional integrity; rollback on failure; bounded + disk-guarded; no partial `current`.

## Slice NK-9 — Ranker wiring: signal registry + tunable weights + `graph/api.py`
**Goal:** expose the signals to the ranker as registered, Optuna-tunable, default-on features, behind the
module boundary.
**Boundaries:** register in `diagnostics/signal_registry.py`; add default-on weights to
`suggestions/tunable_registry.py`; read the signal rows in `pipeline/services/ranker.py`; add
`backend/apps/graph/api.py`. Do NOT change activation/governance (Rust owns that).
**ADR:** signals enter the ranker as features with default-on, non-zero, Optuna-tunable weights; the
registry-driven Optuna search space (already built) auto-includes them; **Rust governance gates
activation** — Optuna only proposes.
**PRD:** the live ranker uses the graph signals to improve suggestions, with weights the autotuner can
optimise and governance can approve.
**Spec:** Parnas 1972 (information hiding / module API, doi:10.1145/361598.361623); the §F/§G boundary.
**Files (create/modify):** `backend/apps/graph/api.py` (`latest_node_signal(item)`,
`link_prediction_candidates(item)`); `diagnostics/signal_registry.py`; `suggestions/tunable_registry.py`
(+ default-on weights via `get_or_create`); `pipeline/services/ranker.py` (read features); tests.
**Requirements:** the ranker reads `NodeGraphSignal`/`LinkPredictionCandidate` via `graph/api.py` only
(no reaching into graph internals); each weight seeds non-zero (DEFAULT-ON-RULE); a `rebuild-required`
state when no `current` run exists (neutral weight, never a fake zero).
**BDD test cases:**
- *Given* a new graph signal registered, *When* the Optuna search space is rebuilt, *Then* it auto-includes
  the weight with no tuner-code change.
- *Given* a current run, *When* the ranker scores a candidate, *Then* the graph features contribute per
  their weights.
- *Given* no current run, *When* the ranker scores, *Then* graph features are neutral and the state is
  `rebuild-required` (no silent zero).
**Edge cases:** a content item with no signal row (neutral, reported); a weight at the floor (never-zero
enforced by Rust governance); cross-module import must go through `graph/api.py`.
**Libraries:** reuse the registries + the Optuna search space from this session's work.
**Resources:** the ranker read is per-candidate hot path — read signals from a per-run cache, not per-row
queries; no NetworKit in the hot path.
**Implementation (TDD):** test auto-inclusion in the search space + the neutral/rebuild-required path Red →
wire → Green.
**Verify:** Dell pytest across graph + suggestions + pipeline; `manage.py check`.
**Code review:** boundary respected (api.py only); default-on; truthful rebuild state; no per-row N+1 in the
hot path; activation still Rust-governed.

## Slice NK-10 — Frontend: graph-signal visualization (ECharts) + truthful states + deep-link
**Goal:** surface the new signals in the GUI (an ECharts view) with truthful states and a registered route.
**Boundaries:** frontend only (`frontend/src/app/...`); a read API endpoint in `graph/api` + views.
**ADR:** every chart uses Apache ECharts (the app standard), GA4 styling, truthful empty/blocked/
rebuild-required/access-denied states, registered in the deep-link catalog with a plain-English tooltip.
**PRD:** the operator can see link-prediction candidates, communities, orphans, and authority on a page,
in plain English.
**Spec:** the repo's `frontend/GSC-DESIGN-SYSTEM.md` + `DEEP-LINKING-CATALOG.md` +
`PLAIN-ENGLISH-HELPER-RULE.md`.
**Files (create/modify):** an Angular component + service under `frontend/src/app/`, the DRF endpoint in
`backend/apps/graph/views.py` + `urls.py`, `frontend/src/app/core/routing/deep-link-catalog.ts`, specs.
**Requirements:** ECharts (no chart.js/d3); CSS tokens only (no hex); 4px-grid spacing; `peHelper`/tooltip
on every technical element; truthful states; register the route + scroll targets in the catalog.
**BDD test cases:**
- *Given* a page with a current run, *When* the view loads, *Then* the ECharts graph renders its
  link-prediction candidates + community colouring.
- *Given* no current run, *When* the view loads, *Then* it shows a "rebuild required — recompute graph
  signals" state, not a blank chart.
- *Given* the route, *When* a deep-link with a fragment is opened, *Then* it auto-reveals + highlights the
  target.
**Edge cases:** empty graph (empty-state card); access-denied (explicit state); large candidate set
(virtual scroll / top-K only).
**Libraries:** ECharts (existing); reuse shared components in `frontend/src/app/shared/`.
**Resources:** render top-K only; no unbounded DOM; lazy-load the heavy chart.
**Implementation (TDD):** Angular spec for the three states (`npm --prefix frontend run test:ci`).
**Verify:** `npm --prefix frontend run test:ci -- --include='<spec>'` + `build:prod`; Dell pytest for the
endpoint.
**Code review:** ECharts + tokens + 4px grid; truthful states; deep-link registered; peHelper present; no
hardcoded styles.

---

# GROUP C — Phase 2: fold the Go services into Python

> Cross-slice spec: `backend/tmp/recon/phase2_go_fold_plan.md` (already written) + ADR 0006 (Go-services
> tier superseded by ADR 0007). Rule: **zero-fallback, single commit per service** — add the Python path,
> delete the Go service + its compose block + its Go lifecycle hooks, refactor every caller, in the same
> change. `services/speccheck` is **Rust** — leave it. `startupd` is **load-bearing** (session gateway) —
> fold it LAST and most carefully. Each fold ends with the app still booting healthy.

## Slice GO-1 — Go-fold recon freeze + safety net
**Goal:** confirm each Go service's exact interface, callers, and the replacing infra before touching code.
**Boundaries:** read-only; produce/refresh the fold plan; add a smoke test that asserts the app's realtime/
sidecar behaviors so each fold is verifiable.
**ADR:** record the final per-service mapping (streamd→Redis Streams, sidecars→Celery/Python,
go-scaffold→delete, startupd→Django startup gate) and the fold order (load-bearing last).
**PRD:** the migration must not break realtime updates, sidecar features, or the session/startup gate.
**Spec:** Redis Streams (redis.io/docs/data-types/streams); transaction-outbox pattern
(microservices.io/patterns/data/transactional-outbox); Celery canvas (Celery docs).
**Files (modify):** `backend/tmp/recon/phase2_go_fold_plan.md`; new characterization tests under the
relevant apps.
**Requirements:** for each Go service: its `api.proto`/`api.http.md`, its Python client(s), the exact
behavior to preserve, and the replacing infra. Add a passing characterization test per behavior.
**BDD test cases:**
- *Given* the realtime client, *When* a characterization test runs, *Then* it asserts the current
  end-to-end behavior (so the fold can prove parity).
- *Given* the recon doc, *When* read, *Then* every Go service has a concrete replacement + caller list.
**Edge cases:** a Go service with no live caller (delete-only); a service publishing over a Unix socket the
Python client dials.
**Libraries:** reuse existing Python clients; Redis/Celery (already deps).
**Resources:** trivial.
**Implementation:** read-only + characterization tests (these are the "Red" baselines for GO-2..5).
**Verify:** characterization tests pass on Dell.
**Code review:** every behavior captured; fold order load-bearing-last; speccheck excluded.

## Slice GO-2 — Fold `streamd` → Redis Streams + Postgres outbox
**Goal:** replace the streamd Go broker with Redis Streams + a Postgres outbox; delete streamd.
**Boundaries:** `backend/apps/realtime/` (the client + a new Python broker), `docker-compose.yml` (remove
the streamd service + socket volume), delete `services/streamd/`, remove the streamd Go hook.
**ADR:** realtime events move to Redis Streams (already running) with a transactional outbox for delivery
guarantees; no Go broker.
**PRD:** realtime updates keep working with at-least-once delivery, fewer moving parts.
**Spec:** Redis Streams (redis.io docs); transactional outbox (microservices.io).
**Files (create/modify/delete):** new `backend/apps/realtime/services/redis_stream_broker.py`; modify the
`_streamd_client.py` callers; `docker-compose.yml`; delete `services/streamd/`,
`backend/apps/realtime/_streamd_pb2/`, `.githooks/check-go-service-*` references to streamd.
**Requirements:** zero-fallback (delete the Go path + stubs in the same commit); the GO-1 characterization
test must pass against the Python broker (parity).
**BDD test cases:**
- *Given* an event published, *When* a consumer reads, *Then* it receives it exactly as before (parity test
  green).
- *Given* a publish inside a DB transaction that rolls back, *When* the outbox is checked, *Then* the event
  is not delivered (outbox correctness).
- *Given* the removal, *When* `git grep streamd`, *Then* no live code references the Go service.
**Edge cases:** consumer reconnect (stream offset resume); outbox backlog (bounded drain); Redis down
(retry + truthful degraded state, not silent drop).
**Libraries:** reuse `redis` (dep), Celery for the outbox drainer.
**Resources:** stream length capped (XTRIM); outbox table bounded + retention.
**Parallel/helper:** the outbox drainer is a Celery task (Dell-schedulable).
**Implementation (TDD):** GO-1 parity test is the Red; implement the broker; Green; delete Go.
**Verify:** Dell pytest; `manage.py check`; app boots healthy; `check-removed-languages` + the Go
lifecycle guard pass (or are removed in GROUP D).
**Code review:** zero-fallback; outbox correct; stream bounded; truthful degraded state; no Go residue.

## Slice GO-3 — Fold `sidecars` → Celery/Python services
**Goal:** replace each sidecar daemon (aclsd / anomalyd / etc.) with a Python/Celery equivalent; delete
`services/sidecars/`.
**Boundaries:** the owning Python apps + Celery; `docker-compose.yml`; delete `services/sidecars/` + its
Go hook + the Python gRPC client.
**ADR:** sidecar responsibilities move into Django services + Celery beat; no Go sidecars.
**PRD:** the sidecar features (access-control lists, anomaly detection, etc.) keep working as Python.
**Spec:** the existing sidecar `api.proto` contracts (parity); VictoriaMetrics/vmalert for anomaly
(already running) where applicable.
**Files (create/modify/delete):** new Python services per sidecar under their owning app; modify the
clients; `docker-compose.yml`; delete `services/sidecars/`.
**Requirements:** one sidecar at a time, each zero-fallback + parity-tested; reuse already-running infra
(VictoriaMetrics for anomaly, Postgres for ACLs).
**BDD test cases:**
- *Given* a sidecar behavior, *When* the Python replacement runs, *Then* the GO-1 parity test passes.
- *Given* the removal, *When* `git grep` the sidecar name, *Then* no live caller remains.
**Edge cases:** a sidecar with internal state (migrate it to Postgres); a high-frequency sidecar (Celery
rate-limit / batching).
**Libraries:** reuse Celery, VictoriaMetrics, Postgres; no new deps.
**Resources:** Celery concurrency from `hardware_profile`; bounded queues.
**Implementation (TDD):** parity tests per sidecar Red→Green; delete Go per sidecar.
**Verify:** Dell pytest; app healthy.
**Code review:** each sidecar parity-proved; no Go residue; reuse over rebuild.

## Slice GO-4 — Delete the `go` scaffold + confirm `speccheck` (Rust) stays
**Goal:** remove the empty/dead `services/go` scaffold; document that `services/speccheck` is Rust and
remains.
**Boundaries:** delete `services/go/`; touch nothing in `services/speccheck/`.
**ADR:** the `go` scaffold has no live behavior → delete; `speccheck` is Rust and is the only retained
`services/` module.
**PRD:** no dead Go scaffolding in the tree.
**Spec:** ADR 0007 (Python+Rust only).
**Files (delete/modify):** delete `services/go/`; update `docs/MODULAR-MONOLITH.md` to note speccheck is
the sole retained service.
**BDD test cases:**
- *Given* the deletion, *When* `git grep` the go-scaffold package, *Then* nothing references it.
- *Given* speccheck, *When* its Rust build runs, *Then* it still builds (untouched).
**Edge cases:** a stray import of the scaffold (remove it).
**Libraries:** none.
**Resources:** trivial.
**Implementation:** delete + grep-verify zero callers.
**Verify:** `check-removed-languages` passes; app healthy.
**Code review:** truly dead; speccheck intact.

## Slice GO-5 — Fold `startupd` → Django startup/route gate (LOAD-BEARING — most careful)
**Goal:** replace the startupd session/startup gateway with a Django readiness gate; delete startupd LAST.
**Boundaries:** `backend/apps/...` startup/readiness code; `docker-compose.yml`; delete `services/startupd/`
+ its Go hook ONLY after the Python gate is proven.
**ADR:** startup readiness + the route gate become a Django middleware/management step + a readiness probe;
no Go gateway.
**PRD:** session start + the commit-hook startup checks keep working; the app must not fail to boot.
**Spec:** the modular-monolith "startup + route gates enforce required-module readiness" rule (§F);
Kubernetes-style readiness (informational).
**Files (create/modify/delete):** a Django readiness gate (middleware + management command); modify
callers + the session-start payload if it dials startupd; `docker-compose.yml`; delete
`services/startupd/` last.
**Requirements:** prove the Python gate end-to-end (the GO-1 characterization test) BEFORE deleting
startupd; keep the app booting healthy at every step; do not break `scripts/session_start_payload.py`.
**BDD test cases:**
- *Given* all required modules ready, *When* the gate runs, *Then* it reports ready and the app serves.
- *Given* a not-ready module, *When* the gate runs, *Then* it returns a truthful `rebuild-required`/
  `blocked` state (no fake ready).
- *Given* the removal, *When* the app boots, *Then* it comes up healthy with no startupd.
**Edge cases:** a module slow to initialize (timeout + retry, not hang); the gate itself failing (fail
loud, not silent ready).
**Libraries:** Django middleware/checks; reuse the existing health module.
**Resources:** the gate is cheap + cached.
**Implementation (TDD):** the readiness gate test Red→Green; only then delete startupd; restart + verify
healthy.
**Verify:** Dell pytest; `python scripts/session_start_payload.py` works; app healthy.
**Code review:** truthful states; no hang; session-start unbroken; startupd fully removed.

## Slice GO-6 — Remove Go residue: compose, hooks, proto stubs, deps, docs
**Goal:** delete all remaining Go artefacts and the Go-services tier from docs/config.
**Boundaries:** `docker-compose.yml`, `.githooks/` Go hooks, generated `*_pb2`/`*.pb.go`, `requirements.txt`
grpc lines (if now unused), `docs/MODULAR-MONOLITH.md`, ADR 0006 banner.
**ADR:** the Go-services tier is fully removed; ADR 0006 is superseded; the cross-language boundary section
is deleted from the modular-monolith doc.
**PRD:** no Go anywhere except none; the docs reflect Python + Rust (+ speccheck Rust).
**Spec:** ADR 0007.
**Files (modify/delete):** `docker-compose.yml` (remove all Go service blocks + `*_sock` volumes);
`.githooks/check-go-service-contract.py`, `check-go-service-resource-budget.py`, `check-stubs-not-
regenerated.py` (delete + un-wire from `scripts/precommit-docker.sh`); delete generated Go/py stubs if the
service is gone; `requirements.txt` (drop grpcio/grpcio-tools if no longer used); `config/protected-data-
stores.json` (drop Go socket volumes); `docs/MODULAR-MONOLITH.md`; ADR 0006.
**BDD test cases:**
- *Given* the removal, *When* `git grep -E "\.go$|go.mod|services/streamd|services/startupd|services/
  sidecars"`, *Then* nothing live remains.
- *Given* a commit, *When* the pre-commit chain runs, *Then* the deleted Go hooks no longer fire.
- *Given* the app, *When* it boots, *Then* it is healthy with no Go containers.
**Edge cases:** a still-imported grpc client (remove it before dropping grpcio); a protected-volume entry
for a deleted socket (remove it).
**Libraries:** none.
**Resources:** disk reclaimed (Go images/volumes).
**Implementation:** delete + un-wire + grep-verify zero residue; image prune (safe).
**Verify:** `python .githooks/check-removed-languages.py` exit 0; precommit chain green; app healthy.
**Code review:** zero Go residue; hooks un-wired cleanly; docs truthful; deps trimmed.

---

# GROUP D — Phase 4: strip the dead-language tooling

> Now that all kernels are Rust and (after Group C) all Go is gone, the C++/Go lifecycle gates and
> removed-language tooling are dead. Cross-slice spec: ADR 0007 + the migration plan §E5.
> `backend/tmp/recon/phase4_tooling_strip_plan.md` (already written) is the checklist.

## Slice TS-1 — Delete the removed-language commit hooks + un-wire them
**Goal:** remove the C++/Go lifecycle gates from the pre-commit chain.
**Boundaries:** `.githooks/` + `scripts/precommit-docker.sh` + the hooks' tests. Do NOT delete
`check-rust-mandate`, `check-removed-languages`, `check-dead-code-on-replace`, or `check-xftool-contract`.
**ADR:** with no C++/Go source, `check-compiled-build`, `check-cpp-lifecycle`, `check-c-abi-conformance`,
`check-go-service-contract`, `check-go-service-resource-budget`, `check-native-observability-wired`,
`check-native-inspection-window`, `check-stubs-not-regenerated` are dead and removed.
**PRD:** the commit gauntlet gets lighter + only enforces Python+Rust gates.
**Spec:** ADR 0007.
**Files (delete/modify):** the eight hook files + their `test_*` + their `run_hard_gate` lines in
`scripts/precommit-docker.sh`.
**Requirements:** delete each hook + its test + its wiring together; verify the chain still parses + runs.
**BDD test cases:**
- *Given* the un-wiring, *When* `bash -n scripts/precommit-docker.sh`, *Then* it parses.
- *Given* a trivial commit, *When* the chain runs, *Then* the deleted gates no longer fire and the commit
  proceeds.
- *Given* a staged `.cpp` (test), *When* committed, *Then* `check-removed-languages` still blocks it (the
  kept guard).
**Edge cases:** a hook referenced elsewhere (grep before delete); a meta-test enumerating hooks (update it).
**Libraries:** none.
**Resources:** faster commits.
**Implementation:** delete + un-wire + `bash -n` + a dry chain run.
**Verify:** the chain runs green on a trivial commit.
**Code review:** only dead gates removed; kept gates intact; chain order preserved.

## Slice TS-2 — Revise the kept hooks + mutation/coverage config to Python+Rust only
**Goal:** trim the language-aware hooks + the mutation/coverage config to two languages.
**Boundaries:** `check-language-ownership`, `check-no-cross-language-import`, `check-mint-first-build`,
`check-scoped-mutation`, `check-per-file-coverage`, `check-mutation-score`, `check-glossary`;
`config/mutation-routing.json`; `docs/MUTATION-THRESHOLDS.md`.
**ADR:** the language matrix is Python + Rust; drop C/C++/Go/Haskell/Lua/Java branches; drop
mull/go-mutesting/mucheck.
**PRD:** quality gates reflect the real two-language stack.
**Spec:** ADR 0007; mutation testing — DeMillo, Lipton, Sayward 1978 (doi:10.1109/C-M.1978.218136).
**Files (modify):** the listed hooks + `config/mutation-routing.json` (`languages{}` + `kill_rate_gates{}`
→ python+rust) + `docs/MUTATION-THRESHOLDS.md` + the glossary.
**BDD test cases:**
- *Given* a Python change, *When* `check-scoped-mutation` runs, *Then* it uses mutmut only.
- *Given* a Rust change, *When* mutation runs, *Then* it uses `cargo-mutants` only.
- *Given* the glossary, *When* checked, *Then* removed-language terms are gone and no new acronym is
  undocumented.
**Edge cases:** a config consumer expecting the old keys (update it); a hook with a hardcoded language list.
**Libraries:** mutmut (Python), cargo-mutants (Rust).
**Resources:** mutation on Dell (turbo).
**Implementation (TDD):** the hooks have tests — update them Red→Green.
**Verify:** the hook tests pass; a sample mutation run routes correctly on Dell.
**Code review:** two-language only; no dead branches; thresholds documented.

## Slice TS-3 — Slim the compiled-tools image + remove host toolchains + dead mutation tools
**Goal:** rebuild `compiled-tools` as Rust-only (or fold into backend-quality), remove host Go/CMake/
go-mutesting, drop mull/mucheck.
**Boundaries:** the `compiled-tools` Dockerfile/stage + the Mint/Dell images; host toolchain removal
(verify they aren't used by other projects first); `requirements`/Dockerfile mutation-tool lines.
**ADR:** compiled-language quality tooling is Rust-only (cargo, clippy, cargo-mutants, maturin); C++/Go/
Haskell layers + mull/go-mutesting/mucheck are removed.
**PRD:** smaller images, no dead toolchains, reclaimed disk.
**Spec:** the repo's `COMPILED-LANGUAGE-RULES`/Docker rules (Docker-managed builds).
**Files (modify/delete):** the `compiled-tools` Dockerfile/stage; the Dell/Mint image build; remove
mull/go-mutesting/mucheck wiring; host toolchain uninstall steps (documented, not auto-run without
confirming non-use).
**BDD test cases:**
- *Given* the rebuilt image, *When* `cargo`/`clippy`/`cargo-mutants`/`maturin` run, *Then* they work.
- *Given* the image, *When* `which g++ go ghc`, *Then* the removed toolchains are absent.
- *Given* a Rust mutation run, *When* routed, *Then* it uses the slim image.
**Edge cases:** a host toolchain used by another project (do NOT remove — document the exception);
VHDX compaction after image removal (Docker rules).
**Libraries:** cargo-mutants, maturin.
**Resources:** big disk reclaim; build on Dell/Mint via the router.
**Parallel/helper:** rebuild on Dell + Mint.
**Implementation:** rebuild the slim image; smoke-test the Rust tools; reclaim disk safely (no volume prune).
**Verify:** the Rust quality tools run on Dell; image size dropped.
**Code review:** Rust-only; no dead layers; disk reclaimed safely; host removals confirmed non-breaking.

## Slice TS-4 — Retire removed-language AutoIssues + paper-trail (run E4 `--apply`)
**Goal:** mark all open cpp/go/haskell/lua/native-observability AutoIssues + paper-trail as resolved/stale
with ADR-0007 lessons; retire the dead pickers.
**Boundaries:** `backend/apps/auto_issues/...retire_removed_language_work.py` (already written — run it);
remove `verify_perfetto_autoissues`/`verify_gwp_asan_autoissues` + the removed-language quota feeders.
**ADR:** dead-language governance rows are retired (status-only, no data loss); the 30-pick + 10-paper-
trail feeders stop demanding work on dead languages. KEEP `rust_defect` + Python issues.
**PRD:** the gauntlet stops blocking on dead-language work.
**Spec:** ADR 0007; the paper-trail rules.
**Files (modify):** run `manage.py retire_removed_language_work --apply`; remove the dead verifiers/pickers;
update the quota feeders.
**BDD test cases:**
- *Given* open dead-language AutoIssues, *When* the command runs `--apply`, *Then* they are resolved with
  two-part lessons citing ADR 0007, and `rust_defect`/Python issues are untouched.
- *Given* the pickers, *When* the session-start quota runs, *Then* no dead-language source is required.
**Edge cases:** a mixed Rust/C++ deferral (do NOT retire — it has live Rust value); a false-positive match
(the command already tightened these — verify the dry-run count first).
**Libraries:** reuse the E4 command.
**Resources:** DB status updates only.
**Implementation (TDD):** the command has 13 tests (green) — re-verify, then `--apply`; remove pickers with
their tests.
**Verify:** `print_open_issues` shows the dead-language buckets cleared; quota runs without them.
**Code review:** status-only; lessons present; rust/Python preserved; pickers removed cleanly.

---

# GROUP E — Phase G: materialize the modular-monolith `api.py` boundaries

> The nine modules (`platform`, `content`, `sources`, `pipeline`, `suggestions`, `analytics`, `graph`,
> `operations`, `governance`) must each expose a single public `api.py`; cross-module imports go through
> it only; dependencies flow downward only. Cross-slice spec: `docs/MODULAR-MONOLITH.md` +
> `docs/specs/fr-modular-monolith.md` + Parnas 1972 (doi:10.1145/361598.361623).

## Slice MM-1 — `api.py` for the existing modules (content, sources, pipeline, suggestions, analytics, graph)
**Goal:** create a single public `api.py` per existing module, exposing only its intended surface.
**Boundaries:** add `api.py` to each module root; do NOT yet refactor callers (that's MM-3).
**ADR:** each module declares its public surface in one `api.py`; everything else is private.
**PRD:** modules become substitutable behind a stable public interface (information hiding).
**Spec:** Parnas 1972 (information hiding, doi:10.1145/361598.361623); the modular-monolith ADRs.
**Files (create):** `backend/apps/<module>/api.py` for content, sources, pipeline, suggestions, analytics,
graph (graph's already started in NK-9); a test per module asserting the public surface imports.
**Requirements:** `api.py` re-exports the public functions/selectors the module already offers; KISS (thin
re-export, no new logic).
**BDD test cases:**
- *Given* a module's `api.py`, *When* imported, *Then* the documented public symbols resolve.
- *Given* a private internal, *When* checked, *Then* it is NOT in `api.py`.
**Edge cases:** a circular import risk (re-export lazily if needed); a module with no current cross-module
consumer (still gets a minimal `api.py`).
**Libraries:** none.
**Resources:** trivial.
**Implementation (TDD):** import tests Red→Green.
**Verify:** Dell pytest; `manage.py check`.
**Code review:** surface minimal + intentional; no logic in `api.py`; no circulars.

## Slice MM-2 — Place the `platform` / `operations` / `governance` modules
**Goal:** establish the three modules not yet present as top-level apps (create or map them) with `api.py`.
**Boundaries:** decide per module whether it's a new thin app or a mapping over existing apps; add `api.py`.
**ADR:** record the mapping (e.g. `governance` = the Rust-governance + approval surfaces; `platform` =
core/infra; `operations` = ops_feed/admin) so the nine-module map is real, not aspirational.
**PRD:** the modular-monolith map matches the code so the boundary rule is enforceable.
**Spec:** `docs/specs/fr-modular-monolith.md`; Parnas 1972.
**Files (create/modify):** `backend/apps/<platform|operations|governance>/api.py` (or a documented mapping
in `docs/MODULAR-MONOLITH.md` with the api.py living on the mapped app).
**BDD test cases:**
- *Given* each of the three modules, *When* its `api.py` imports, *Then* it resolves.
- *Given* the module map doc, *When* read, *Then* all nine modules point at a real `api.py`.
**Edge cases:** a module that is genuinely a facade over two apps (document the composition).
**Libraries:** none.
**Resources:** trivial.
**Implementation (TDD):** import + map-consistency tests.
**Verify:** Dell pytest; the boundary check (MM-3) will enforce it.
**Code review:** mapping honest (no skeletons); nine modules real.

## Slice MM-3 — Enforce the boundary: refactor cross-module imports + a boundary check
**Goal:** make every cross-module import go through `api.py`, flowing downward only, and add a gate.
**Boundaries:** refactor offending imports across `backend/apps/`; add/enable a boundary check hook.
**ADR:** cross-module Python imports outside `api.py` are forbidden; dependencies flow Layer1→Layer2→Layer3
only; a pre-commit check enforces it (`check-no-cross-language-import` extended, or a new
`check-module-boundary`).
**PRD:** the monolith stays modular — a violation fails the commit, not code review.
**Spec:** the boundary + dependency-direction rules (`docs/MODULAR-MONOLITH.md`); Parnas 1972.
**Files (modify/create):** refactor the violating imports to `from apps.<module>.api import ...`;
`.githooks/check-module-boundary.py` + test + wire into `scripts/precommit-docker.sh`.
**BDD test cases:**
- *Given* a cross-module import not via `api.py`, *When* the check runs, *Then* it blocks with a plain-
  English message.
- *Given* an upward import (Layer3→Layer1 is fine; Layer1→Layer3 is not), *When* checked, *Then* a wrong-
  direction import is blocked.
- *Given* the refactor, *When* the suite runs, *Then* behavior is unchanged (regression-safe).
**Edge cases:** a legitimate same-layer need (route it through `api.py` or refactor); a shim still present
from the slice rollout (remove per ADR 0005).
**Libraries:** AST parsing in the hook (stdlib `ast`).
**Resources:** the check is fast (per-file AST).
**Implementation (TDD):** the hook's test (allow/block cases) Red→Green; refactor imports until the check
passes tree-wide.
**Verify:** the boundary check passes on the whole tree; full suite green on Dell; behavior unchanged.
**Code review:** no behavior change; boundary enforced; direction correct; shims removed.

---

# GROUP F — Coverage → 95% (E8)

> Two-part: raise the target + wire Rust coverage, then ratchet actual coverage per module. Spec:
> `docs/CODE-COVERAGE-RULES.md` + `AI-CODING-GUIDELINES.md`. Cite the diff-coverage lesson
> (`K8S.26 §6`): coverage gates run on the diff, never whole legacy files; the global 95% floor is the
> per-module ratchet's end-state, never a cliff.

## Slice COV-1 — Wire Rust coverage + raise the per-module floor mechanism to 95%
**Goal:** add `cargo-llvm-cov` to the gate + make the per-file/per-module floor configurable to 95% without
breaking commits.
**Boundaries:** `.githooks/check-per-file-coverage.py`, `config/mutation-routing.json` coverage config,
`docs/CODE-COVERAGE-RULES.md`, the per-task table in `AI-CODING-GUIDELINES.md`; a Rust coverage runner.
**ADR:** coverage is measured for BOTH Python (coverage.py) and Rust (cargo-llvm-cov); the 95% floor is a
**per-module ratchet** (a module's floor rises to 95% once it gets there) — never a global cliff.
**PRD:** quality bar rises to 95% without making the repo un-committable.
**Spec:** `docs/CODE-COVERAGE-RULES.md`; cargo-llvm-cov (docs).
**Files (modify/create):** `scripts/run-rust-coverage.sh` (cargo-llvm-cov on Dell); the coverage hook (add
Rust + the per-module ratchet); the coverage config + docs.
**BDD test cases:**
- *Given* a Rust crate, *When* coverage runs, *Then* cargo-llvm-cov reports a per-crate %.
- *Given* a module below 95%, *When* a diff in it is committed, *Then* only the changed lines must be
  covered (diff gate), not the whole module.
- *Given* a module at 95%, *When* its floor is ratcheted, *Then* a regression below 95% blocks.
**Edge cases:** a legacy file at 28% (diff-only gate, not whole-file); a generated file (exempt); a Rust
crate with no testable surface (documented exempt).
**Libraries:** coverage.py, cargo-llvm-cov.
**Resources:** coverage on Dell (turbo); bounded.
**Implementation (TDD):** the hook's tests for the ratchet + diff gate + Rust path Red→Green.
**Verify:** a sample Python + Rust coverage run on Dell; the hook tests pass.
**Code review:** ratchet not cliff; diff-gate on legacy; Rust wired; docs updated.

## Slice COV-2 — Ratchet the touched modules to ≥95% (real tests)
**Goal:** bring the modules touched this plan (graph, suggestions, pipeline ranker wiring, realtime,
auto_issues, audit, governance) to ≥95% by writing real tests.
**Boundaries:** add/extend tests for the under-covered files identified by the gap report; touch production
code only to fix a real bug found while testing.
**ADR:** each touched module reaches ≥95% with behavior-asserting tests + its floor is ratcheted.
**PRD:** the new + touched code is provably exercised.
**Spec:** `docs/CODE-COVERAGE-RULES.md`; Beck 2002 (TDD).
**Files (create/modify):** test files per under-covered module (e.g. `apps/audit/comments.py` 67%,
`apps/audit/serializers.py` 83% from the gap report); the filed coverage-gap AutoIssues (#22825–28) get
resolved.
**BDD test cases:**
- *Given* an under-covered file, *When* its tests are added, *Then* coverage measures ≥95% and the lines
  are behavior-asserted (not just executed).
- *Given* a coverage-gap AutoIssue, *When* the tests land, *Then* it is resolved with a two-part lesson.
**Edge cases:** a file "could not be measured" (its discovered test errors → fix the test so coverage
measures, per the handoff note); a pure-config module (document exempt).
**Libraries:** pytest, coverage.py.
**Resources:** coverage on Dell; bounded.
**Implementation (TDD):** write the missing tests (assert behavior + edge cases) until each module ≥95%.
**Verify:** per-module coverage ≥95% on Dell; the gap AutoIssues resolved.
**Code review:** tests assert behavior; edge cases covered; no production change beyond real bug fixes.

---

# GROUP G — Stragglers + final close

## Slice CL-1 — Remove the two stray Lua files + fix the stale mutation-wiring test
**Goal:** delete `.githooks/lua/queue_fetcher.lua` + its spec; update `scripts/test_mutation_tool_wiring.py`
which still asserts dead-language wrapper scripts exist.
**Boundaries:** `.githooks/lua/`, `scripts/test_mutation_tool_wiring.py`, the dead wrapper scripts
(`run-cpp-mutation.sh`, `run-go-mutation.sh`, `run-lua-quality.sh`, `run-haskell-quality.sh`).
**ADR:** Lua + the removed-language mutation wrappers are fully gone; the wiring test asserts the
Python+Rust reality.
**PRD:** no Lua or dead wrapper scripts anywhere.
**Spec:** ADR 0007.
**Files (delete/modify):** delete `.githooks/lua/queue_fetcher.lua`, `.githooks/lua/tests/
queue_fetcher_spec.lua`, the four dead wrapper scripts; update `scripts/test_mutation_tool_wiring.py`.
**BDD test cases:**
- *Given* the deletions, *When* `git grep -E "\.lua$|run-cpp-mutation|run-go-mutation"`, *Then* nothing
  live remains.
- *Given* the wiring test, *When* run, *Then* it asserts only mutmut + cargo-mutants (+ Stryker if JS is
  still in scope) and passes.
**Edge cases:** a hook referencing `queue_fetcher.lua` (remove the reference); the wrapper scripts wired
into a hook (un-wire first).
**Libraries:** none.
**Resources:** trivial.
**Implementation (TDD):** update the wiring test Red→Green; delete; grep-verify.
**Verify:** the wiring test passes on Dell; `check-removed-languages` exit 0.
**Code review:** zero Lua residue; wiring test truthful.

## Slice CL-2 — Repo-wide doc/config sweep: supersede the stale 5-language spec + final pass
**Goal:** update `docs/specs/fr-approved-library-expansion-bank.md` (still prescribes C/C++/Go/Haskell/Lua)
+ sweep any remaining removed-language references in docs/config/rule files.
**Boundaries:** `docs/`, `config/`, the root rule `.md` files; do NOT restructure `CLAUDE.md`/`AGENTS.md`
beyond correcting dead-language references.
**ADR:** the library-bank spec is Python+Rust only (with the approved Python/Rust libs); a SUPERSEDED
banner removed once corrected; no doc claims a removed language is current.
**PRD:** the docs reflect the real two-language stack so no future agent rebuilds a dead language.
**Spec:** ADR 0007; `GLOSSARY-RULE.md`.
**Files (modify):** `docs/specs/fr-approved-library-expansion-bank.md`; grep-driven fixes across `docs/`,
`config/`, the rule files; the glossary (drop dead-language terms).
**BDD test cases:**
- *Given* the library-bank spec, *When* read, *Then* it lists only Python + Rust lanes/libs.
- *Given* a tree-wide grep for "C++ first"/"Go services tier"/Haskell/Lua as current, *Then* only
  superseded/historical mentions remain.
- *Given* the glossary, *When* checked, *Then* no removed-language acronym is presented as live.
**Edge cases:** a doc that's an intentional historical record (banner, don't delete); a config key still
read by code (fix the code first).
**Libraries:** none.
**Resources:** trivial.
**Implementation:** scripted grep sweep + per-file review where a rule changes.
**Verify:** the grep sweep shows no live removed-language reference; `check-glossary` passes.
**Code review:** truthful docs; no live dead-language prescription; glossary clean.

## Slice CL-3 — FINAL: full-stack verification, clean tree, session close
**Goal:** prove the whole system is green end-to-end, everything committed, and close the session.
**Boundaries:** verification + the session-close ritual; no new features.
**ADR:** the migration + NetworKit + close-out are complete; record the final state.
**PRD:** the owner has a single green, committed, fully-Python+Rust repo with NetworKit live and the
suggestion engine using graph signals.
**Spec:** the repo's session-close protocol.
**Files (modify):** `AGENT-HANDOFF.md` (final closing entry); `docs/PYTHON-RUST-MIGRATION-PLAN.md` (mark
phases done); the REPORT-REGISTRY if a report is due.
**Requirements:** full backend suite green on Dell; full frontend suite + `build:prod` green; mutation gate
on changed code; coverage ≥95% on touched modules; backend boots healthy with all-Rust kernels + NetworKit
+ no Go; `git status` clean.
**BDD test cases:**
- *Given* the whole backend suite, *When* run on Dell, *Then* it is green.
- *Given* the frontend, *When* `test:ci` + `build:prod` run, *Then* both pass.
- *Given* the app, *When* booted, *Then* it is healthy with Rust kernels + NetworKit signals + zero Go/C++.
- *Given* the repo, *When* `git status` runs, *Then* the tree is clean (everything committed).
**Edge cases:** a flaky test (run `-p randomly`, fix the order leak); a deferred item discovered (file it
via `defer_work` with citations); a residual uncommitted file (commit or explain).
**Libraries:** none.
**Resources:** turbo on Dell.
**Implementation:** run every suite; fix to green; write the close-out handoff + session-close marker.
**Verify:** all suites green; tree clean; app healthy.
**Code review:** the meta-review — every prior slice's review passed, no spaghetti/verbose/over-engineering
crept in, the system matches every spec, and there is genuinely no stone left unturned.

---

## Appendix — order, dependencies, and definition of done
- **Order:** A1 → A2 → A3 → NK-1…NK-10 → GO-1…GO-6 → TS-1…TS-4 → MM-1…MM-3 → COV-1…COV-2 →
  CL-1 → CL-2 → CL-3. NK depends on A2 (clean tree). GO-6/TS depend on GO-1…GO-5. MM-3 depends on
  MM-1/MM-2. COV-2 depends on COV-1. CL-3 depends on all.
- **Per-slice definition of done:** spec cited + current-month fresh; BDD cases + edge cases all covered
  by real (Red-first) tests; unit tests + static analysis + lint green on Dell; coverage ≥ target;
  resource budget respected; the mandatory §0.6 code review answered in writing and logged; one clean
  commit through the full gauntlet (never `--no-verify`).
- **Overall definition of done (CL-3):** zero C++/Go/Haskell/Lua source; all kernels Rust + healthy;
  NetworKit's 10 signals live and feeding the Optuna-tunable, governance-gated ranker; the nine modules
  behind enforced `api.py` boundaries; coverage ≥95% on touched modules; the docs/config/glossary truthful;
  `git status` clean; the close-out handoff written.
Historical note: this document describes an older Docker-era finish plan. Current MSI commands must use Kubernetes, `python scripts/backend_manage.py`, or SSH to Dell/Mint helpers.
