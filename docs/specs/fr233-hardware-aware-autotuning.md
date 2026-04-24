# FR-233 — Hardware-aware dynamic batch sizing

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Hardware-aware auto-tuner |
| **Settings prefix** | `performance.profile_override` |
| **Pipeline stage** | Embed |
| **Helper module** | `backend/apps/pipeline/services/hardware_profile.py` |
| **Benchmark module** | `backend/benchmarks/test_bench_hardware_profile.py` |
| **Consumers** | `apps.pipeline.services.embeddings._get_configured_batch_size`; all three `embedding_providers/*` |

## 2 · Motivation (ELI5)

Different laptops have different RAM and VRAM. A 3072-dim OpenAI-large model
needs more memory per row than a 768-dim Gemini model. The auto-tuner looks
at the machine (RAM / CPU / CUDA VRAM), looks at the current model's vector
dimension, and picks a batch size that fits inside 15% of host RAM. No
swap-thrashing on a 4 GB laptop; full throughput on a 32 GB workstation.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Primary** | Smith, Kindermans, Ying, Le, 2018 — *"Don't Decay the Learning Rate, Increase the Batch Size"* (ICLR 2018). arXiv 1711.00489. |
| **FP16 memory** | Micikevicius et al., 2018 — *"Mixed Precision Training"* (ICLR 2018). arXiv 1710.03740. |
| **Public prior art** | NVIDIA Triton Inference Server dynamic-batching (Apache-2.0 open source). |
| **What we reproduce** | Memory-proportional batch sizing. Batch size scales with available memory / bytes-per-item. |
| **What we diverge on** | We don't try to auto-adjust during training (our workload is inference-only) and we clamp per-tier to keep behaviour predictable. |

## 4 · Input contract

`recommended_batch_size(*, dimension, profile=None, provider_ceiling=None)`

- **dimension** — `int ≥ 1` — model output dimension.
- **profile** — optional `HardwareProfile`; auto-detected if omitted.
- **provider_ceiling** — optional per-API cap (OpenAI 2 048, Gemini 100).

Empty / zero dimension → returns `_BATCH_MIN` (4) without error.

## 5 · Output contract

`int` batch size ∈ `[_BATCH_MIN, _BATCH_MAX]` (4 to 256). Clamped to the tier cap:

| Tier | Detected when | Max batch |
|---|---|---|
| `low` | <8 GB RAM, no GPU | 32 |
| `medium` | 8–16 GB RAM, or no dGPU ≥4 GB | 64 |
| `high` | 16–32 GB RAM + dGPU ≥4 GB VRAM | 128 |
| `workstation` | 32+ GB RAM + dGPU ≥8 GB VRAM | 256 |

Formula: `raw = (ram_gb × 1e9 × 0.15) / (dim × 4 bytes × 3)`, then clamp to tier cap, then clamp to `_BATCH_MIN`..`_BATCH_MAX`, then to `provider_ceiling` if given. Deterministic.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default |
|---|---|---|---|
| `performance.profile_override` | str | `""` | Empty = auto-detect. Accepts `low`/`medium`/`high`/`workstation` for testing. |

Internal constants (not user-tunable): `_RAM_BATCH_FRACTION = 0.15`, `_PER_ITEM_MULTIPLIER = 3` (input + intermediate + output buffers). Values come from `docs/PERFORMANCE.md` §3 budget envelope.

## 7 · Resource contract

- Detection cost: one `psutil.virtual_memory()` + one `torch.cuda.mem_get_info()` call. Cached per-process.
- Batch-size calc: pure arithmetic, O(1).
- No I/O, no allocation.

## 8 · Test plan

1. **Benchmark** — `test_bench_hardware_profile.py` at 1024 / 1536 / 3072 dim confirms microsecond-range latency.
2. **Override** — set `AppSetting("performance.profile_override") = "low"` on a workstation; call `detect_profile(force_refresh=True)`; confirm tier flips to `low` and batch size drops.
3. **Real-machine sanity** — `GET /api/embedding/hardware-profile/` (via the `/api/embedding/status/` endpoint) returns a plausible tier for the current host.
4. **No GPU** — on a CPU-only machine, `has_cuda=False` and `vram_gb=0`; tier stays at `medium` or `low` depending on RAM.
