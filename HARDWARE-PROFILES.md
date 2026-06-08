# HARDWARE-PROFILES.md — Tier-Aware Settings

**Status:** PARAMOUNT for any change that touches batch sizes, parallelism, FAISS configuration, or model loading.

## The Tiers

The detection logic lives in [`backend/apps/pipeline/services/hardware_profile.py`](backend/apps/pipeline/services/hardware_profile.py). Tiers are auto-detected on first import and re-detected on every backend boot.

| Tier | RAM | CPU | GPU | Embedding batch (1024-dim) |
|---|---|---|---|---|
| `low` | < 8 GB | n/a | none | 4 |
| `medium` | 8–16 GB | n/a | integrated | 16 |
| `high` (current setup) | 16–32 GB | i5-12450H | RTX 3050 6 GB | 64 |
| `workstation` (future) | 32+ GB | n/a | dGPU 8+ GB VRAM | 128 |

The user is on `high` today. The plan is "one day I'll have a faster PC" — the tier swaps automatically on the next reboot after the upgrade and every consuming service picks up the new batch size / parallelism / cache budget without code changes.

## Helper Machines

The Dell helper machine is available for repo-owned turbo quality checks. Agents reach it through Docker context `dell`; the backend quality image is `xf-linker-backend-quality:latest`. The Python quality runner uses Dell for the large shard and Windows for the small shard, so agents should run the turbo helper instead of replacing it with a single local Docker run. Mint remains a separate helper for the observability stack and any runner whose config names `mint`, but Dell is the primary Python quality helper.

Quick proof commands:

```powershell
docker --context dell run --rm xf-linker-backend-quality:latest python --version
docker --context dell run --rm xf-linker-backend-quality:latest python -m pytest --version
```

## What Each Tier Controls

- **Embedding batch size.** `recommended_batch_size(dimension=1024)` in `hardware_profile.py` returns the right number per tier.
- **FAISS quantisation.** `low` / `medium` use IVFADC with int8 OPQ codes; `high` uses fp32 IVFADC; `workstation` may use HNSW with no quantisation.
- **Celery worker concurrency.** `high` runs 1 Heavy worker + 4 Medium; `workstation` could run 1 Heavy + 8 Medium (subject to GPU availability).
- **Embedding-provider preference order.** `low` defaults to local-only; `high` may prefer paid-fast for cold-start; `workstation` may prefer paid-best.
- **Background pre-warm budget.** Higher tiers can keep more model weights in VRAM at once.

## How To Use The Tier In Your Code

Anywhere you'd hardcode a batch size or parallelism, do this instead:

```python
from apps.pipeline.services.hardware_profile import detect_profile, recommended_batch_size

profile = detect_profile()  # cached after first call
batch_size = recommended_batch_size(dimension=1024, profile=profile, provider_ceiling=2048)
```

Operator overrides via `AppSetting("performance.profile_override")` ∈ `{low, medium, high, workstation}` for testing low-end behaviour on a beefy box.

## Forward-Thinking Compliance

- C++ extensions compiled with `-march=native` pick up the new chip's instruction set on the next `make build-ext`. No code change.
- Hardware-tier registry table (Group R, scheduled) will track every connected PC (main + helpers) so multi-machine setups also tier-adjust.
- Auto-detect upgrade on every startup logs to `/error-log` (severity=info): `"Hardware upgrade detected: high → workstation. Applying workstation settings."`

## Forbidden Patterns

- ❌ Hardcoded batch sizes (`batch_size = 32`) outside `hardware_profile.py`
- ❌ `if torch.cuda.is_available(): batch = 64 else: batch = 8` — use `recommended_batch_size` instead
- ❌ Per-feature tier branches (`if tier == 'workstation': ...`) — extend the YAML config (Group R) or push the branch into `hardware_profile.py`
- ❌ Settings that scale linearly with corpus size without a tier ceiling — define the ceiling in `_HARD_BOUNDS`
