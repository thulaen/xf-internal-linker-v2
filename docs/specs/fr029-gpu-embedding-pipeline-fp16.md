# FR-029 — GPU Embedding Pipeline: fp16 Inference + HIGH_PERFORMANCE Mode

**Status:** Pending
**Requested:** 2026-03-28
**Target phase:** Phase 32
**Priority:** Medium
**Depends on:** none (self-contained change to `embeddings.py`)

---

## Problem

`ML_PERFORMANCE_MODE` defaults to `BALANCED`, which means the embedding model runs on CPU with `batch_size=32`. When running on GPU hardware (RTX 3050, 6GB VRAM), this leaves the GPU idle during all embedding tasks. Additionally, even when `HIGH_PERFORMANCE` mode is enabled, the model loads in float32 by default — using ~1GB VRAM and running slower than necessary for inference.

---

## What Already Exists

`backend/apps/pipeline/services/embeddings.py` already has:

- `_resolve_device()` — returns `'cuda'` when `ML_PERFORMANCE_MODE=HIGH_PERFORMANCE` and PyTorch CUDA is available, otherwise `'cpu'`
- `_get_batch_size()` — returns `128` in HIGH_PERFORMANCE mode, `32` in BALANCED
- `_load_model()` — loads `SentenceTransformer` on the resolved device, but **does not enable fp16**

The only missing piece is fp16 (half-precision) inference when running on GPU.

---

## What This FR Adds

### 1. fp16 Inference in `_load_model()`

When `device='cuda'`, convert the model to half-precision immediately after loading:

```python
model = SentenceTransformer(model_name, device=device, trust_remote_code=True)
if device == "cuda":
    model.half()  # convert to float16 in-place
```

**Why:** bge-m3 at float16 uses ~500MB VRAM vs ~1GB at float32. Inference throughput increases by ~1.4–1.8× on Ampere GPUs (RTX 3050 is Ampere, compute capability 8.6). The output embeddings are still stored as float32 in pgvector — the `_l2_normalize()` call already casts back to `np.float32`.

**Safety:** `model.half()` is the sentence-transformers-compatible way to set fp16. Do NOT use `torch_dtype=torch.float16` on the `SentenceTransformer` constructor — it does not accept that kwarg.

### 2. Log fp16 Status

Add a log line confirming fp16 is active:

```python
if device == "cuda":
    model.half()
    logger.info("fp16 inference enabled for CUDA device.")
```

### 3. Set `ML_PERFORMANCE_MODE=HIGH_PERFORMANCE` in Docker Compose

Add to `docker-compose.yml` (or `docker-compose.override.yml`) for the `backend` and `celery` services:

```yaml
environment:
  ML_PERFORMANCE_MODE: HIGH_PERFORMANCE
```

This activates GPU device selection and batch_size=128 in a single env var.

### 4. Update `get_model_status()` to Report fp16

Add `"fp16": device == "cuda"` to the status dict so FR-028 Diagnostics Tab can display it.

---

## Boundaries

| In scope | Out of scope |
|---|---|
| fp16 on CUDA path only | TensorRT, ONNX export |
| `_load_model()` change only | Any change to pgvector storage |
| Docker Compose env var | Kubernetes / production deployment |
| bge-m3 dense head only | Sparse or ColBERT heads |

---

## VRAM Budget After This FR

| Item | VRAM |
|---|---|
| bge-m3 at float16 | ~500 MB |
| Inference buffers (batch 128) | ~200 MB |
| **Subtotal** | **~700 MB** |
| Remaining for FR-030 FAISS-GPU | **~4.8 GB free** |

---

## Files to Change

| File | Change |
|---|---|
| `backend/apps/pipeline/services/embeddings.py` | Add `model.half()` in `_load_model()` when `device == 'cuda'`; add fp16 log line; add `"fp16"` key to `get_model_status()` |
| `docker-compose.yml` | Add `ML_PERFORMANCE_MODE: HIGH_PERFORMANCE` to backend + celery service env |

---

## Verification

1. Run `docker compose up` with the env var set.
2. Check Django logs for: `Loading embedding model 'BAAI/bge-m3' on device='cuda'...` and `fp16 inference enabled for CUDA device.`
3. Call `GET /api/diagnostics/weights/` (FR-028) — verify `"fp16": true` appears in model status.
4. Run an embedding task and confirm `nvidia-smi` shows GPU utilization > 0%.
5. Confirm `get_model_status()` returns `"device": "cuda"` and `"mode": "HIGH_PERFORMANCE"`.
