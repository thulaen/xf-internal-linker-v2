# Pick #45 — Stochastic Weight Averaging (Izmailov et al. 2018)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 45 |
| **Canonical name** | Stochastic Weight Averaging — model-weight averaging across epochs |
| **Settings prefix** | `swa` |
| **Pipeline stage** | Training |
| **Shipped in commit** | **DEFERRED** — needs torch training loop |
| **Helper module** | `backend/apps/training/avg/swa.py` (Phase 6 — sanctioned `apps.training` Django app, see Completion Plan §Architecture Principles rule 1) |
| **Tests module** | pending |
| **Benchmark module** | pending G6 |

## 2 · Motivation

Near the end of training, model weights oscillate around a wide
optimum. Averaging the weights of the last N epochs pulls the model
to the centre of that optimum — generalises better than any single
end-of-training checkpoint. Izmailov et al. show 0.5-2 % accuracy
wins on CIFAR / ImageNet benchmarks with basically zero extra
compute.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Izmailov, P., Podoprikhin, D., Garipov, T., Vetrov, D. & Wilson, A. G. (2018). "Averaging weights leads to wider optima and better generalization." *UAI*. |
| **Open-access link** | <https://arxiv.org/abs/1803.05407> |
| **Relevant section(s)** | §2 — SWA algorithm; §3 — flat-minima geometric argument. |
| **What we faithfully reproduce** | `torch.optim.swa_utils.AveragedModel`. |

## 4 · Input contract

- **Wrap the model**: `swa_model = AveragedModel(base_model)`.
- Call `swa_model.update_parameters(base_model)` once per epoch
  (after a burn-in period).
- At eval time use `swa_model` instead of `base_model`.

## 5 · Output contract

- Averaged model weights, same shape as base model.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `swa.enabled` | bool | `true` (once torch training loop exists) | Recommended preset policy | No | — | Off = use last-epoch weights |
| `swa.burn_in_epochs` | int | `10` | Izmailov et al. §3 recommends starting SWA late | Yes | `int(1, 50)` | Wait until loss plateaus |
| `swa.update_every_n_epochs` | int | `1` | Paper default | Yes | `int(1, 5)` | Less frequent = more diversity |

## 7 · Pseudocode

```
from torch.optim.swa_utils import AveragedModel, SWALR

swa_model = AveragedModel(base_model)

for epoch in range(epochs):
    train_one_epoch(base_model, ...)
    if epoch >= swa_burn_in_epochs and (epoch - swa_burn_in_epochs) % swa_update_every == 0:
        swa_model.update_parameters(base_model)

# Evaluate using swa_model at the end
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| (none yet — awaits torch training loop) | — | — |

## 9 · Scheduled-updates job

None — runs inside training.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | +1× model size (the averaged copy) | — |
| Disk | +1× model size (serialised checkpoint) | — |
| CPU | negligible | — |

## 11 · Tests

Deferred.

## 12 · Benchmark inputs

Deferred.

## 13 · Edge cases & failure modes

- **BatchNorm stats** — SWA needs a final "update_bn" pass over
  training data to fix running stats; otherwise eval gives poor
  numbers. `torch.optim.swa_utils.update_bn` handles this.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| Torch training loop | Required consumer |
| #43 Cosine Annealing | Often paired |

## 15 · Governance checklist

- [ ] Pick remains deferred until training loop is built
