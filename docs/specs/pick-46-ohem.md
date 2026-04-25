# Pick #46 — Online Hard Example Mining (Shrivastava et al. 2016)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 46 |
| **Canonical name** | OHEM — focus training on the hardest mini-batch examples |
| **Settings prefix** | `ohem` |
| **Pipeline stage** | Training |
| **Shipped in commit** | **DEFERRED** — needs torch training loop |
| **Helper module** | `backend/apps/training/sample/ohem.py` (Phase 6 — sanctioned `apps.training` Django app, see Completion Plan §Architecture Principles rule 1) |
| **Tests module** | pending |
| **Benchmark module** | pending G6 |

## 2 · Motivation

Many training examples are already well-learned after a few epochs —
their gradients are tiny and their compute is wasted. OHEM picks the
**top-k hardest** (highest-loss) examples in each mini-batch and
back-props only through those. Wins: faster convergence, better
worst-case performance. Standard in modern computer-vision training
loops.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Shrivastava, A., Gupta, A. & Girshick, R. (2016). "Training region-based object detectors with online hard example mining." *CVPR*, pp. 761-769. |
| **Open-access link** | <https://arxiv.org/abs/1604.03540> |
| **Relevant section(s)** | §3 — OHEM algorithm; §5 — wins on object-detection benchmarks. |

## 4 · Input contract

- **`select_hardest(losses: torch.Tensor, k: int | float) ->
  torch.Tensor`** — returns indices of the top-k examples.
- `k` can be absolute count or fraction (`0.25` = top 25 %).

## 5 · Output contract

- Index tensor.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `ohem.enabled` | bool | `true` (once training loop exists) | Recommended preset policy | No | — | Off = train on full batch |
| `ohem.keep_fraction` | float | `0.25` | Shrivastava et al. §3 — keeping top 25 % is the empirical sweet spot | Yes | `uniform(0.1, 0.75)` | Lower = sharper focus, lower effective batch |

## 7 · Pseudocode

```
function select_hardest(losses, k):
    if isinstance(k, float):
        k = int(len(losses) * k)
    return torch.topk(losses, k).indices
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| (none yet — awaits torch training loop) | — | — |

## 9 · Scheduled-updates job

None — inside training.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 1 KB (index tensor) | — |
| Disk | 0 | — |
| CPU | top-k is O(n log k) | — |

## 11 · Tests

Deferred.

## 12 · Benchmark inputs

Deferred.

## 13 · Edge cases & failure modes

- **All-easy batch** — still returns the top-k, they're just all
  easy; no problem.
- **k > batch size** — clamp to batch size.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| Torch training loop | Required consumer |
| #44 LambdaLoss | Loss provider |

## 15 · Governance checklist

- [ ] Pick remains deferred until training loop is built
