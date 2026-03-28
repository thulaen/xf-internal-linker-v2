# FR-030 — FAISS-GPU Vector Similarity Search

**Status:** Pending
**Requested:** 2026-03-28
**Target phase:** Phase 33
**Priority:** Medium
**Depends on:** FR-029 (GPU must be active before FAISS-GPU is worth using)

---

## Problem

Stage 1 of the pipeline (`_stage1_candidates()` in `pipeline.py`) does cosine similarity search by:

1. Fetching ALL host content embeddings from pgvector on every pipeline run (a DB query)
2. Running `dest_block @ host_matrix.T` — a NumPy matrix multiply on CPU

For 50k–100k articles at 1024 dimensions, this is ~400MB of data moving from Postgres → Python RAM → CPU matmul on every run. The GPU sits idle for this step even in HIGH_PERFORMANCE mode.

---

## What This FR Adds

A persistent FAISS-GPU index that:
- Lives in VRAM for the lifetime of the Django process
- Pre-loads all host embeddings once at startup (not on every pipeline run)
- Replaces the CPU NumPy matmul in Stage 1 with a GPU search
- Falls back silently to the existing NumPy path if FAISS-GPU is unavailable

---

## Architecture

### New File: `backend/apps/pipeline/services/faiss_index.py`

Owns the singleton FAISS GPU index and the id-map that translates FAISS integer positions back to Postgres PKs.

```
_faiss_index: faiss.Index | None = None
_faiss_id_map: list[int] = []       # position i -> ContentItem.pk
_faiss_content_type_map: list[str]  # position i -> content_type
_index_lock: threading.Lock
```

**Public API:**

| Function | Description |
|---|---|
| `build_faiss_index() -> None` | Load all embeddings from DB, build IndexFlatIP, move to GPU if available |
| `faiss_search(query_vectors: np.ndarray, k: int) -> list[list[int]]` | Returns list of ContentItem PK lists, one per query vector |
| `is_faiss_gpu_active() -> bool` | Returns True when index is on GPU |
| `get_faiss_status() -> dict` | Returns index size, device, VRAM estimate for FR-028 Diagnostics |

### Index Type: `IndexFlatIP`

- Exact inner product search (cosine on L2-normalized vectors)
- No training required
- Correct for bge-m3 because embeddings are already L2-normalized before storage
- At 100k vectors × 1024 dims × 4 bytes = **391 MB VRAM**

### GPU vs CPU Fallback

```python
if faiss.get_num_gpus() > 0 and ML_PERFORMANCE_MODE == "HIGH_PERFORMANCE":
    res = faiss.StandardGpuResources()
    index = faiss.index_cpu_to_gpu(res, 0, index_cpu)
else:
    index = index_cpu  # CPU fallback, still faster than pgvector for repeated queries
```

---

## Django Lifecycle

### Build on Startup: `backend/apps/pipeline/apps.py`

```python
class PipelineConfig(AppConfig):
    name = "apps.pipeline"

    def ready(self):
        import os
        # Guard: only in main server/worker process, not during migrate/shell
        if os.environ.get("FAISS_INDEX_SKIP_BUILD"):
            return
        from .services.faiss_index import build_faiss_index
        try:
            build_faiss_index()
        except Exception:
            logger.exception("FAISS index build failed at startup — falling back to NumPy path")
```

The `FAISS_INDEX_SKIP_BUILD=1` env var allows management commands and migrations to skip the build.

### Refresh via Celery Beat

Add to `CELERY_BEAT_SCHEDULE` in `backend/config/settings/base.py`:

```python
"refresh-faiss-index": {
    "task": "apps.pipeline.tasks.refresh_faiss_index",
    "schedule": crontab(minute="*/15"),  # every 15 minutes
},
```

New Celery task in `backend/apps/pipeline/tasks.py`:

```python
@shared_task(name="apps.pipeline.tasks.refresh_faiss_index")
def refresh_faiss_index():
    from .services.faiss_index import build_faiss_index
    build_faiss_index()
```

---

## Stage 1 Integration

In `_stage1_candidates()` in `pipeline.py`, replace the CPU matmul block with a FAISS search:

**Before:**
```python
# fetch host embeddings from DB
host_emb_qs = ContentItem.objects.filter(pk__in=host_pks, embedding__isnull=False)...
host_matrix = np.array([...], dtype=np.float32)
sims = dest_block @ host_matrix.T
```

**After:**
```python
from .faiss_index import faiss_search, is_faiss_gpu_active

if is_faiss_gpu_active():
    # returns top-K PKs per dest vector directly from GPU index
    pk_results = faiss_search(dest_block, k=top_k)
    # pk_results[i] = list of top-K ContentItem PKs for dest_block[i]
    # ... map PKs to sentence IDs using content_to_sentence_ids
else:
    # existing NumPy path unchanged
    sims = dest_block @ host_matrix.T
    ...
```

The existing NumPy path must remain intact as the fallback — no removal.

---

## Installation

Add to `backend/requirements.txt`:

```
faiss-gpu-cu12>=1.8.0  # CUDA 12.x — Linux/Docker only
```

Add a conditional import guard in `faiss_index.py`:

```python
try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False
    logger.warning("faiss not installed — FAISS-GPU path disabled")
```

**Important:** `faiss-gpu-cu12` is Linux-only. The Docker container is Linux. Running Django directly on Windows will use the CPU fallback automatically.

---

## VRAM Budget with FR-029 + FR-030 Active

| Item | VRAM |
|---|---|
| bge-m3 fp16 (FR-029) | ~500 MB |
| Inference buffers (batch 128) | ~200 MB |
| FAISS IndexFlatIP, 100k vectors | ~391 MB |
| FAISS search buffers | ~50 MB |
| **Total used** | **~1.14 GB** |
| **Free on RTX 3050 6GB** | **~4.86 GB** |

---

## Boundaries

| In scope | Out of scope |
|---|---|
| Stage 1 candidate retrieval | Stage 2 sentence scoring |
| ContentItem embeddings only | Sentence embeddings |
| `IndexFlatIP` exact search | `IndexIVFFlat`, `IndexIVFPQ` (not needed at this scale) |
| Django process singleton | Shared index across gunicorn workers |
| CPU NumPy fallback preserved | Removing existing pgvector HNSW indexes |
| `get_faiss_status()` for FR-028 | Any FR-028 UI changes |

---

## Files to Create / Change

| File | Change |
|---|---|
| `backend/apps/pipeline/services/faiss_index.py` | **Create** — singleton index, build, search, status |
| `backend/apps/pipeline/apps.py` | Add `build_faiss_index()` call in `ready()` |
| `backend/apps/pipeline/services/pipeline.py` | Replace Stage 1 CPU matmul with `faiss_search()` call, keep NumPy fallback |
| `backend/apps/pipeline/tasks.py` | Add `refresh_faiss_index` Celery task |
| `backend/config/settings/base.py` | Add `refresh-faiss-index` to `CELERY_BEAT_SCHEDULE` |
| `backend/requirements.txt` | Add `faiss-gpu-cu12>=1.8.0` |

---

## Verification

1. Start services. Check Django logs for: `FAISS index built: 50000 vectors, device=GPU`.
2. Run a pipeline task. Confirm Stage 1 log says `FAISS-GPU search active`.
3. Check `nvidia-smi` shows VRAM usage increased by ~400MB after startup.
4. Call `GET /api/diagnostics/weights/` (FR-028) — verify FAISS status appears.
5. Set `FAISS_INDEX_SKIP_BUILD=1` and run `python manage.py migrate` — confirm no error.
6. On a machine without CUDA, confirm the NumPy fallback runs without error.
