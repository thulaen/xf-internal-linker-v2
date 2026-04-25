# Pick #52 — Adaptive Conformal Inference (Gibbs & Candès 2021)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 52 |
| **Canonical name** | ACI — online α adjustment under distribution shift |
| **Settings prefix** | `adaptive_conformal_inference` |
| **Pipeline stage** | Reviewable |
| **Shipped in commit** | **PR-P — to ship** |
| **Helper module** | [backend/apps/pipeline/services/adaptive_conformal_inference.py](../../backend/apps/pipeline/services/adaptive_conformal_inference.py) |
| **Tests module** | `backend/apps/pipeline/test_reviewable.py` |
| **Benchmark module** | `backend/benchmarks/test_bench_aci.py` (pending G6) |

## 2 · Motivation

Plain Conformal Prediction (pick #50) assumes **exchangeability** —
the data distribution doesn't shift. Reality shifts: new content types,
new operator behaviours, seasonal trends. ACI watches observed coverage
online and nudges `α` up when coverage drops below target or down when
coverage exceeds target — long-run coverage stays calibrated even under
arbitrary drift. Gibbs & Candès prove this retains the guarantee with
zero distributional assumptions.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Gibbs, I. & Candès, E. J. (2021). "Adaptive Conformal Inference Under Distribution Shift." *NeurIPS*. |
| **Open-access link** | <https://arxiv.org/abs/2106.00170> |
| **Relevant section(s)** | Algorithm 1 — `α_{t+1} = α_t + γ (target_α - observed_miscoverage_t)`. |
| **What we faithfully reproduce** | Algorithm 1 exactly. |
| **What we deliberately diverge on** | Clip α to `[clip_min, clip_max]` as a safety rail — paper's algorithm can drift arbitrarily; our clamp prevents runaway in adversarial scenarios. |

## 4 · Input contract

- **`AdaptiveConformalInference(target_alpha=0.1, learning_rate_gamma=0.005,
  window_size=500, clip_alpha_min=0.01, clip_alpha_max=0.50)`** —
  constructor.
- **`.update(was_covered: bool) -> float`** — feed one observation,
  return updated α.
- **`.current_alpha`** — current α.

## 5 · Output contract

- `float` in `[clip_alpha_min, clip_alpha_max]`.
- **Long-run coverage guarantee.** Under arbitrary shift, running
  mean of `was_covered` converges to `1 - target_alpha` as n → ∞.
- **Determinism.** Pure state machine.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `adaptive_conformal_inference.enabled` | bool | `true` | Recommended preset policy | No | — | Off = plain Conformal Prediction |
| `adaptive_conformal_inference.method` | str (enum) | `"gibbs_candes_2021"` | Plan-spec fixed to the paper's algorithm | No | — | Identity |
| `adaptive_conformal_inference.target_miscoverage_alpha` | float | `0.10` | Matches #50 default (90 % coverage) | No | — | User-chosen coverage target |
| `adaptive_conformal_inference.learning_rate_gamma` | float | `0.005` | Gibbs-Candès recommended 0.005–0.05 | Yes | `loguniform(1e-4, 0.1)` | Higher = faster adaptation, more oscillation |
| `adaptive_conformal_inference.window_size` | int | `500` | Plan — rolling coverage window | Yes | `int(100, 2000)` | Trade responsiveness vs noise |
| `adaptive_conformal_inference.clip_alpha_min` | float | `0.01` | Safety — never go below 1 % miscoverage | No | — | Safety floor |
| `adaptive_conformal_inference.clip_alpha_max` | float | `0.50` | Safety — never go above 50 % | No | — | Safety ceiling |
| `adaptive_conformal_inference.coverage_log_retention_days` | int | `90` | Plan — audit trail | Yes | `int(30, 365)` | Disk budget for audit log |

## 7 · Pseudocode

```
class AdaptiveConformalInference:
    def __init__(self, target_alpha, gamma, window_size, clip_min, clip_max):
        self.alpha = target_alpha
        self.target = target_alpha
        self.gamma = gamma
        self.window = deque(maxlen=window_size)
        self.clip_min, self.clip_max = clip_min, clip_max

    def update(self, was_covered):
        self.window.append(1.0 if was_covered else 0.0)
        if len(self.window) < self.window.maxlen // 2:
            return self.alpha   # warmup — don't adjust yet
        observed_miscoverage = 1.0 - sum(self.window) / len(self.window)
        self.alpha += self.gamma * (observed_miscoverage - self.target)
        self.alpha = max(self.clip_min, min(self.clip_max, self.alpha))
        return self.alpha
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| Review-queue feedback loop | "Was the true outcome inside #50's predicted interval?" | Updated α → next CP intervals tighter/looser |

## 9 · Scheduled-updates job

None directly — ACI updates online on every feedback event. A daily
audit log rotation is handled by the generic `jobalert_dedup_cleanup`
or a dedicated pruning task.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 1 MB (window of 500 booleans) | — |
| Disk | < 1 MB (90-day audit log of α values) | — |
| CPU | < 1 µs per update | benchmark small |

## 11 · Tests

- `test_warmup_keeps_initial_alpha`
- `test_under_coverage_pushes_alpha_up`
- `test_over_coverage_pushes_alpha_down`
- `test_clip_prevents_runaway`
- `test_long_run_coverage_tracks_target` (Monte Carlo)

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 updates | < 1 ms | > 10 ms |
| medium | 100 000 updates | < 50 ms | > 500 ms |
| large | 100 000 000 updates | < 30 s | > 5 min |

## 13 · Edge cases & failure modes

- **Coverage oracle wrong** (feedback labels mislabelled) — ACI still
  tracks the labelled coverage, which may diverge from true coverage.
  Only mitigable by label-quality audits.
- **Extreme γ** — wild α oscillation. Clip + TPE search space keep
  γ reasonable.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #50 Conformal Prediction | Produces the intervals ACI adapts |

| Downstream | Reason |
|---|---|
| Review-queue UI | Always shows coverage-calibrated intervals |

## 15 · Governance checklist

- [ ] `adaptive_conformal_inference.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows + coverage-log table
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry (< 1 MB RAM / < 1 MB disk)
- [x] Helper module (PR-P)
- [ ] Benchmark module
- [x] Test module (PR-P)
- [ ] TPE search space declared
- [ ] Feedback loop wired (W4)
- [ ] Coverage log dashboard card (W4)
