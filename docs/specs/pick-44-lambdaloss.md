# Pick #44 — LambdaLoss listwise LTR (Wang et al. 2018)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 44 |
| **Canonical name** | LambdaLoss — NDCG-optimising listwise loss |
| **Settings prefix** | `lambda_loss` |
| **Pipeline stage** | Training |
| **Shipped in commit** | **DEFERRED** — needs torch training loop |
| **Helper module** | `backend/apps/training/loss/lambda_loss.py` (Phase 6 — sanctioned `apps.training` Django app, see Completion Plan §Architecture Principles rule 1) |
| **Tests module** | pending |
| **Benchmark module** | pending G6 |

## 2 · Motivation

Training a ranker with pointwise regression (MSE) or pairwise
(BPR-like) loss doesn't directly optimise the ranking metric
(typically NDCG). LambdaLoss unifies LambdaMART / LambdaRank under
a listwise framework that *does* optimise NDCG. Wang et al. show
2-3 NDCG@10 points improvement over pairwise on LETOR benchmarks.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Wang, X., Li, C., Golbandi, N., Bendersky, M. & Najork, M. (2018). "The LambdaLoss framework for ranking metric optimization." *CIKM*, pp. 1313-1322. |
| **Open-access link** | <https://storage.googleapis.com/pub-tools-public-publication-data/pdf/1e34e05e5e4bf2d12f41eb9ff29ac3da9fdb4de3.pdf> |
| **Relevant section(s)** | §3 — LambdaLoss formulation `L = Σ log2(1 + exp(-σ(s_i - s_j))) |ΔNDCG_ij|`. |

## 4 · Input contract

- **`lambda_loss(scores: torch.Tensor, labels: torch.Tensor) ->
  torch.Tensor`** — computes the scalar loss.

## 5 · Output contract

- Scalar loss tensor suitable for `.backward()`.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `lambda_loss.enabled` | bool | `true` (once torch training loop exists) | Recommended preset policy | No | — | Off = fall back to pairwise |
| `lambda_loss.sigma` | float | `1.0` | Wang et al. §4 empirical | Yes | `uniform(0.1, 5.0)` | Sharpness of pairwise preference |

## 7 · Pseudocode

See the paper §3; concise Python impl is hand-rollable once a training
loop exists.

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| (none yet — awaits torch training loop) | — | — |

## 9 · Scheduled-updates job

None — runs inside training.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~4 × batch size² (pairwise matrix) | — |
| Disk | 0 | — |
| CPU | Dominated by torch autograd | — |

## 11 · Tests

Deferred.

## 12 · Benchmark inputs

Deferred.

## 13 · Edge cases & failure modes

- **All labels zero** — loss is zero (no positive pairs).
- **Batch size 1** — no pairs; loss is zero.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| Torch training loop | Required consumer |

## 15 · Governance checklist

- [ ] Pick remains deferred until training loop is built
