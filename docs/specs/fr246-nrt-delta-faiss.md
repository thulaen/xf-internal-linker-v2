# FR-246 — Near-real-time delta FAISS index

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | NRT delta layer for FAISS index (60s refresh) |
| **Settings prefix** | `pipeline.nrt_delta_enabled`, `pipeline.nrt_delta_refresh_seconds`, `pipeline.nrt_delta_max_size`, `pipeline.nrt_delta_flush_threshold_size` |
| **Pipeline stage** | Stage 1 retrieval (delta layer feeds alongside the base FAISS index) |
| **Helper** | `apps.pipeline.services.nrt_delta_index.NRTDeltaIndex`, `get_live_delta`, `reset_live_delta` |
| **Default state** | **ON.** The data structure is always available via `get_live_delta()`. The base-layer query merge (the actual usage in Stage-1) is the v2 wire-in commit. |

## 2 · Motivation (ELI5)

Today's FAISS index rebuilds every 15 minutes on a Celery beat task. A new article posted at 12:01 isn't searchable until 12:15. The fix is the canonical Lucene NRT pattern: a small fast-refreshing in-memory index sits in front of the slow base index. Inserts go to delta first; searches union both layers. When delta hits half-full, a background task merges its contents into the base index and clears the delta. Operators see new content surface in suggestions within ~60 seconds of insert.

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Primary** | Bialecki, A., Muir, R. & Ingersoll, G. (2012). *Apache Lucene 4.* SIGIR Workshop on Open Source Information Retrieval. https://lucene.apache.org/core/4_0_0/. §3 — defines the NRT pattern: 60-second refresh; merge into base when delta hits half-full. |
| **Patent** | US Patent [10,719,511](https://patents.google.com/patent/US10719511) (Microsoft, 2020). *Search index updates and freshness.* Two-tier base+delta architecture exactly applicable here. |
| **Cap rationale** | Yang, P. et al. (2018). *Anserini: Reproducible Ranking Baselines Using Lucene.* JDIQ. arXiv:[1805.01764](https://arxiv.org/abs/1805.01764). §4 — beyond ~10K vectors per-query merge cost crosses 10ms. |

## 4 · Output contract

`NRTDeltaIndex(*, max_size=10_000, flush_threshold=5_000)`
- Thread-safe via internal RLock.
- `add(pk, content_type, vector)` — inserts or refreshes; FIFO eviction at `max_size`.
- `search(query, k, *, host_pk_set=None) -> list[tuple[int, str, float]]` — same shape as `faiss_index.faiss_search`.
- `needs_flush() -> bool` — True at `flush_threshold`.
- `clear()` — empty the index (post-merge cleanup).
- `get_status() -> dict` — operator-visible plain-English status.

`get_live_delta() -> NRTDeltaIndex` — process-wide singleton, lazily constructed.

## 5 · Implementation

| File | Change |
|---|---|
| `backend/apps/pipeline/services/nrt_delta_index.py` | New file. ~190 lines. NumPy + threading.RLock + OrderedDict for O(1) FIFO. |
| `backend/apps/pipeline/tests_scaffolds.py::NRTDeltaIndexTests` | 13 tests. |

Settings keys (`pipeline.nrt_delta_*`) seeded by migration 0061.

Memory cost at default sizing: 10K × 1024 dim × 4 bytes ≈ 40 MB at full delta. Fits comfortably in the existing backend container.

## 6 · Test plan

13 SimpleTestCase tests:
1. **Default constants locked** — Yang 2018 §4 + Bialecki 2012 §3.
2. **Empty index search returns empty**.
3. **Add then search finds vector**.
4. **Top-K ordering by descending cosine**.
5. **FIFO eviction on overflow**.
6. **Refresh existing key doesn't count as new** (no spurious eviction).
7. **`needs_flush` triggers at threshold**.
8. **`clear` empties the index**.
9. **`host_pk_set` filter** — Stage-1 self-link / scope filtering parity.
10. **Invalid `max_size` raises**.
11. **Invalid `flush_threshold` raises**.
12. **Non-1D vector rejected**.
13. **`get_status` shape**.
14. **Singleton helpers** — `get_live_delta` + `reset_live_delta`.

## 7 · Wire-in (deferred)

In `_stage1_semantic_candidates` the FAISS path becomes:

```python
from apps.pipeline.services.nrt_delta_index import get_live_delta

# 1. Search the base FAISS index (existing path)
base_hits = _run_faiss_block_search(..., faiss_search=faiss_search)

# 2. Search the delta layer (this scaffold)
delta = get_live_delta()
delta_hits_per_dest = {
    dest: delta.search(query_vec, k=top_k)
    for dest, query_vec in zip(destination_keys, dest_embeddings)
}

# 3. Merge: append delta hits to base hits, dedupe by host_key,
#    re-sort by score. RRF fusion in `_fuse_via_rrf` is also a valid
#    merge primitive here.
return _merge_base_and_delta(base_hits, delta_hits_per_dest)
```

Plus: a Celery beat task at 60-second cadence that calls `delta.needs_flush()`; when True, batch-inserts delta entries into the base FAISS via `build_faiss_index()` and calls `delta.clear()`.

These two wire-ins are deferred for benchmark sweep + a focused commit.

## 8 · Citations on every default

- `DELTA_REFRESH_SECONDS_DEFAULT = 60` — Bialecki 2012 §3 (Lucene NRT default).
- `DELTA_MAX_SIZE_DEFAULT = 10_000` — Yang 2018 §4 (per-query merge stays under 10ms).
- `DELTA_FLUSH_THRESHOLD_DEFAULT = 5_000` — Bialecki 2012 §3 (merge at half-full).
- FIFO eviction policy — Yang 2018 §4 (oldest-first matches Lucene's commit-segment invariant).

## 9 · Status

Data structure + tests + spec shipped 2026-05-07. Stage-1 query-merge wire-in + Celery beat flush task = v2 follow-up.
