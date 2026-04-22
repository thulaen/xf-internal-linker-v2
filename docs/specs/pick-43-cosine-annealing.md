# Pick #43 — Cosine Annealing LR schedule (Loshchilov-Hutter 2017)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 43 |
| **Canonical name** | Cosine annealing with warm restarts (SGDR) |
| **Settings prefix** | `cosine_annealing` |
| **Pipeline stage** | Training |
| **Shipped in commit** | **DEFERRED** — no torch training loop exists yet |
| **Helper module** | `backend/apps/training/schedule/cosine_annealing.py` (plan path, not yet created) |
| **Tests module** | pending |
| **Benchmark module** | pending G6 |

## 2 · Motivation

Stochastic optimisers (Adam, SGD) benefit from a learning-rate
schedule: start high to explore, anneal low to converge. Cosine
annealing uses a smooth cosine decay that consistently beats step /
exponential schedules in Loshchilov-Hutter's benchmarks. "Warm
restarts" — periodic re-raises of the LR — help escape saddle
points.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Loshchilov, I. & Hutter, F. (2017). "SGDR: Stochastic gradient descent with warm restarts." *ICLR*. |
| **Open-access link** | <https://arxiv.org/abs/1608.03983> |
| **Relevant section(s)** | §2 — `lr = lr_min + 0.5 (lr_max - lr_min) (1 + cos(π · T_cur / T_i))`; §3 — restart schedule. |
| **What we faithfully reproduce** | `torch.optim.lr_scheduler.CosineAnnealingWarmRestarts`. |

## 4 · Input contract

- **`scheduler = CosineAnnealingWarmRestarts(optimizer, T_0=10,
  T_mult=2, eta_min=0)`**
- **`scheduler.step()`** — call once per epoch.

## 5 · Output contract

- Schedules the optimizer's learning rate in-place.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `cosine_annealing.enabled` | bool | `true` (once torch training loop exists) | Recommended preset policy | No | — | Off = constant LR |
| `cosine_annealing.T_0` | int | `10` | Loshchilov-Hutter §3 — first-cycle length | Yes | `int(5, 50)` | — |
| `cosine_annealing.T_mult` | int | `2` | Paper default — each cycle 2× longer | Yes | `int(1, 4)` | — |
| `cosine_annealing.eta_min` | float | `0.0` | Paper default | Yes | `loguniform(1e-6, 1e-3)` | Floor on LR |

## 7 · Pseudocode

```
import torch.optim.lr_scheduler as lr_sched

scheduler = lr_sched.CosineAnnealingWarmRestarts(
    optimizer, T_0=T_0, T_mult=T_mult, eta_min=eta_min,
)

for epoch in range(epochs):
    train_one_epoch(...)
    scheduler.step()
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| (none yet — awaits torch training loop) | — | — |

## 9 · Scheduled-updates job

None directly — runs inside a training job (e.g. future neural-reranker
training).

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 1 KB | — |
| Disk | 0 | — |
| CPU | < 1 µs per `step()` | — |

## 11 · Tests

- `test_cosine_annealing_lowers_lr_within_cycle`
- `test_warm_restart_resets_lr_at_t_mult`

## 12 · Benchmark inputs

Micro-benchmarks of the schedule itself are trivial; real perf is in
the training loop.

## 13 · Edge cases & failure modes

- **No torch training loop exists** — pick is dormant. If a neural
  reranker is added later, this pick wires in trivially.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| A torch-based trainable model | Required consumer |

| Downstream | Reason |
|---|---|
| #45 SWA | Often paired — cosine schedule + SWA averaging |

## 15 · Governance checklist

- [ ] Pick remains deferred until a torch training loop is built
- [ ] Spec referenced from the training-loop PR when it lands
