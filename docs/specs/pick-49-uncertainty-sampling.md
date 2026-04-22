# Pick #49 — Uncertainty Sampling for review ordering (Lewis & Gale 1994)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 49 |
| **Canonical name** | Uncertainty Sampling — show least-confident cases first |
| **Settings prefix** | `uncertainty_sampling` |
| **Pipeline stage** | Reviewable |
| **Shipped in commit** | **PR-P — to ship** |
| **Helper module** | `backend/apps/pipeline/services/uncertainty_sampling.py` (to be created) |
| **Tests module** | `backend/apps/pipeline/test_reviewable.py` (to be created) |
| **Benchmark module** | `backend/benchmarks/test_bench_uncertainty.py` (pending G6) |

## 2 · Motivation

Operators can review, say, 50 suggestions per day. If we order them
by confidence (highest first) they see cases the model already gets
right — their attention is wasted. Uncertainty sampling flips it:
show the model's **least-confident** cases first, which is where
human judgement adds the most value. Foundational active-learning
result from Lewis & Gale 1994.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Lewis, D. D. & Gale, W. A. (1994). "A sequential algorithm for training text classifiers." *SIGIR*, pp. 3-12. |
| **Open-access link** | <https://arxiv.org/abs/cmp-lg/9407020> |
| **Relevant section(s)** | §3 — least-confidence strategy; §5 — convergence bounds for active learning. |
| **What we faithfully reproduce** | Least-confidence ordering: `uncertainty = 1 - max(P(class=c | x))`. |
| **What we deliberately diverge on** | Plan-spec has binary {accept, reject} outcomes; we add a "margin sampling" variant for multi-class settings. |

## 4 · Input contract

- **`rank_by_uncertainty(probabilities: Iterable[float], *,
  strategy="least_confidence") -> list[int]`** — returns indices in
  review order (most uncertain first).
- Strategies: `"least_confidence"`, `"margin"`, `"entropy"`.

## 5 · Output contract

- `list[int]` of the original indices, reordered.
- **Determinism.** Pure function.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `uncertainty_sampling.enabled` | bool | `true` | Recommended preset policy | No | — | Off = review ordering by raw score |
| `uncertainty_sampling.strategy` | str (enum) | `"least_confidence"` | Lewis-Gale §3 default | Yes | `categorical(["least_confidence","margin","entropy"])` | Different uncertainty flavours |

## 7 · Pseudocode

```
function rank_by_uncertainty(probabilities, strategy):
    if strategy == "least_confidence":
        uncertainty = 1 - max(p) per row
    elif strategy == "margin":
        uncertainty = p_top1 - p_top2 (lower = more uncertain)
    elif strategy == "entropy":
        uncertainty = -sum(p * log(p)) per row
    return argsort(-uncertainty)  # most uncertain first
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/suggestions/views.py` (Review Queue endpoint) | Daily suggestions with calibrated probabilities | Reordered review list |

## 9 · Scheduled-updates job

None — per-request API.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | O(N) for the ordering | — |
| Disk | 0 | — |
| CPU | O(N) | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_least_confidence_orders_correctly` | 0.5 confidence before 0.9 |
| `test_margin_orders_correctly` | Small margin before large |
| `test_entropy_orders_correctly` | High entropy before low |
| `test_empty_input_returns_empty` | Degenerate |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 suggestions | < 1 ms | > 10 ms |
| medium | 100 000 suggestions | < 50 ms | > 500 ms |
| large | 10 000 000 suggestions | < 5 s | > 60 s |

## 13 · Edge cases & failure modes

- **All probabilities identical** — any ordering is correct; we
  preserve input order as a stable tie-break.
- **Probabilities don't sum to 1** — helper doesn't enforce; caller
  ensures.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #32 Platt Calibration | Provides calibrated probabilities |

| Downstream | Reason |
|---|---|
| Review queue UI | Ordered review list |
| #50 Conformal Prediction | Alt uncertainty indicator (intervals instead of scalar) |

## 15 · Governance checklist

- [ ] `uncertainty_sampling.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [ ] Helper module (PR-P)
- [ ] Benchmark module
- [ ] Test module (PR-P)
- [ ] TPE search space declared
- [ ] Review-queue endpoint wired (W4)
