# Pick #35 — Elo rating (Elo 1978)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 35 |
| **Canonical name** | Elo rating — pairwise dynamic rating |
| **Settings prefix** | `elo_rating` |
| **Pipeline stage** | Score (dynamic quality rating) |
| **Shipped in commit** | `879ecc5` (PR-N, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/elo_rating.py](../../backend/apps/pipeline/services/elo_rating.py) |
| **Tests module** | [backend/apps/pipeline/test_feedback_signals.py](../../backend/apps/pipeline/test_feedback_signals.py) — `EloRatingTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_elo.py` (pending G6) |

## 2 · Motivation

Operators accept/reject suggestions one by one — the data is *pairwise*
feedback, not scalar scores. "Operator accepted A over B" is one bit
of signal. Over many such comparisons, Elo produces a single rating
per suggestion that reflects relative quality. Beats simple
win-rate because it accounts for opponent strength — a 90 %
win-rate against weak opponents is weaker than 60 % against strong
ones.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Elo, A. E. (1978). *The Rating of Chessplayers, Past and Present.* Arco Publishing. ISBN 0-668-04721-6. |
| **Open-access link** | <https://www.amazon.com/dp/0668047216> (book); algorithm summary: <https://en.wikipedia.org/wiki/Elo_rating_system#Mathematical_details> |
| **Relevant section(s)** | Chapter 1 §1.2 — logistic expected-score formula; §2.1 — K-factor |
| **What we faithfully reproduce** | Expected-score sigmoid and K-factor update. |
| **What we deliberately diverge on** | Provide a mutable `EloState` with match counts so operators can drop K-factor over time (Elo's Chess recommendation). |

## 4 · Input contract

- **`PairwiseOutcome(item_a, item_b, score_a)`** — `score_a ∈ [0, 1]`
  (1 = A won, 0.5 = draw, 0 = B won).
- **`expected_score(*, rating_a, rating_b, scale=400.0) -> float`**
- **`update(state: EloState, outcome, *, k_factor=32, scale=400,
  initial_rating=1500) -> tuple[float, float]`**
- **`run_batch(outcomes, *, initial_state=None, ...) -> EloState`**

## 5 · Output contract

- `EloState(ratings, match_counts)` — mutable dict-based state.
- Rating values grow unbounded in principle; in practice drift
  into `[500, 2500]`.
- **Determinism.** Deterministic given order of outcomes.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `elo_rating.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no dynamic rating |
| `elo_rating.k_factor` | float | `32.0` | Elo 1978 — chess convention | Yes | `uniform(8.0, 64.0)` | Higher = faster reaction, more volatility |
| `elo_rating.scale` | float | `400.0` | Elo 1978 §1.2 — 400-point gap ≈ 75 % expected win rate | No | — | Correctness (scale of rating) |
| `elo_rating.initial_rating` | float | `1500.0` | USCF convention | No | — | Neutral starting point |

## 7 · Pseudocode

See `apps/pipeline/services/elo_rating.py`. Core:

```
function expected_score(ra, rb, scale):
    return 1 / (1 + 10 ** ((rb - ra) / scale))

function update(state, outcome, k, scale, initial):
    ra, rb = state.get(outcome.item_a, initial), state.get(outcome.item_b, initial)
    ea = expected_score(ra, rb, scale)
    sa = outcome.score_a
    state.ratings[outcome.item_a] = ra + k * (sa - ea)
    state.ratings[outcome.item_b] = rb + k * ((1-sa) - (1-ea))
    # match_counts bookkeeping
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/feedback_rerank.py` | Operator accept/reject pairs | Elo rating as feature |
| `apps/analytics/impact_engine.py` | Suggestion Elo ratings | Dashboard ranking list |

## 9 · Scheduled-updates job

None — stateful, updated on each feedback event. Batch-recompute job
could be added if operators want "rollback to last Monday's rating".

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~16 bytes per rated item (float + match count) | — |
| Disk | Same, persisted to DB | — |
| CPU | < 1 µs per update | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_equal_ratings_give_expected_half` | Baseline |
| `test_higher_rating_expected_above_half` | Direction |
| `test_win_raises_and_loss_lowers` | Update |
| `test_draw_is_noop_between_equal_ratings` | Edge |
| `test_bad_score_rejected` | Validation |
| `test_run_batch_multiple_wins_grow_rating` | Cumulative |
| `test_run_batch_continues_from_initial_state` | State persistence |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 outcomes | < 1 ms | > 10 ms |
| medium | 100 000 outcomes | < 50 ms | > 500 ms |
| large | 10 000 000 outcomes | < 3 s | > 30 s |

## 13 · Edge cases & failure modes

- **Unrated items** — default to `initial_rating`.
- **Never-seen item after seeing it once** — rating persists on the
  state; caller can reset via `state.ratings.pop(...)`.
- **Score outside [0,1]** → `ValueError`.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| Operator feedback events | Outcome source |
| #34 Cascade Click | Click vs skip generates pairwise outcomes |

| Downstream | Reason |
|---|---|
| Feedback reranker | Uses rating as feature |
| UI "top-rated" leaderboard | Visual ranking |

## 15 · Governance checklist

- [ ] `elo_rating.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-N)
- [ ] Benchmark module
- [x] Test module (PR-N)
- [ ] TPE search space declared
- [ ] Feedback reranker wired (W3)
