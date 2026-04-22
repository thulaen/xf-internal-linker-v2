# Pick #48 — Reservoir Sampling (Vitter 1985 Algorithm R)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 48 |
| **Canonical name** | Vitter Algorithm R — uniform random sample from a stream |
| **Settings prefix** | `reservoir_sampling` |
| **Pipeline stage** | Eval |
| **Shipped in commit** | `f25104a` (PR-O, 2026-04-22) |
| **Helper module** | [backend/apps/pipeline/services/reservoir_sampling.py](../../backend/apps/pipeline/services/reservoir_sampling.py) |
| **Tests module** | [backend/apps/pipeline/test_explain_and_eval.py](../../backend/apps/pipeline/test_explain_and_eval.py) — `ReservoirSampleTests` + `ReservoirDataclassTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_reservoir.py` (pending G6) |

## 2 · Motivation

Offline NDCG evaluation, eval-set rotation, and TPE's objective
function all need a uniformly random sample of size `k` from a
possibly huge stream of suggestions. Storing every row in memory
and shuffling doesn't scale. Reservoir Sampling draws a uniformly
random size-`k` sample in one streaming pass with O(k) memory.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Vitter, J. S. (1985). "Random sampling with a reservoir." *ACM Transactions on Mathematical Software* 11(1): 37-57. |
| **Open-access link** | <https://www.cs.umd.edu/~samir/498/vitter.pdf> |
| **Relevant section(s)** | §3 — Algorithm R definition + correctness proof; §4 — faster variants (Algorithm Z) for large streams. |
| **What we faithfully reproduce** | Algorithm R. Algorithm Z would speed up very large streams but Algorithm R is fast enough (~ns per observation) for the linker's scale. |

## 4 · Input contract

- **`Reservoir(k: int, items=[], _rng=Random())`** — streaming class.
- **`.add(item)`** — `O(1)`.
- **`.extend(stream)`** / **`sample(stream, *, k, rng=None)`** —
  one-shot helpers.
- **`deterministic_rng(seed: int) -> random.Random`** — scheduler job
  uses this for reproducible sampling.

## 5 · Output contract

- `list` of size `min(stream_length, k)`.
- **Uniformly distributed.** Every item in a stream of length N has
  exactly `k/N` probability of appearing in the final sample.
- **Determinism.** Deterministic per seeded RNG.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `reservoir_sampling.enabled` | bool | `true` | Recommended preset policy | No | — | Off = use whole stream (often intractable) |
| `reservoir_sampling.eval_sample_size` | int | `1000` | Plan §On-demand eval — 1 000 is the standard offline-NDCG sample size | Yes | `int(100, 10000)` | Larger = lower variance, slower HPO trials |
| `reservoir_sampling.seed` | int | `42` | Reproducibility | No | — | Same seed → same sample (tests + HPO reproducibility) |
| `reservoir_sampling.rotation_cadence_days` | int | `1` | Plan — daily rotation keeps the eval set fresh | Yes | `int(1, 30)` | Longer = more stable eval but staler corpus coverage |

## 7 · Pseudocode

See `apps/pipeline/services/reservoir_sampling.py`. Core:

```
function add(self, item):
    self._seen += 1
    if len(self.items) < self.k:
        self.items.append(item)
    else:
        j = self._rng.randrange(self._seen)
        if j < self.k:
            self.items[j] = item
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/meta_hpo_eval.py` (future W1) | Stream of suggestions from past week | Eval set for TPE objective |
| `apps/diagnostics/*` (future) | Suggestion stream | Random spot-check feature |

## 9 · Scheduled-updates job

- **Key:** `reservoir_sampling_rotate`
- **Cadence:** daily 19:00
- **Priority:** low
- **Estimate:** < 1 min
- **Multicore:** no
- **RAM:** ≤ 16 MB

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | O(k) — ~1 MB at k=1000 | — |
| Disk | Persisted eval set: `k × row size` | — |
| CPU | < 2 µs per add | benchmark small |

## 11 · Tests

All 8 `ReservoirSampleTests` + `ReservoirDataclassTests` +
`FairShuffleTests` + `SHAPUnavailableTests` pass, including a
2000-trial Monte Carlo uniformity check.

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 000-item stream, k=100 | < 5 ms | > 50 ms |
| medium | 10 000 000-item stream, k=1000 | < 5 s | > 60 s |
| large | 1 000 000 000-item stream, k=1000 | < 8 min | > 1 h |

## 13 · Edge cases & failure modes

- **Stream shorter than `k`** — returns everything.
- **Empty stream** — returns `[]`.
- **`k ≤ 0`** → `ValueError`.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| Suggestion / click stream | Source |

| Downstream | Reason |
|---|---|
| #42 TPE | Objective function consumes the eval set |
| Dashboard random-audit | Uses the daily rotated sample |

## 15 · Governance checklist

- [ ] `reservoir_sampling.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-O)
- [ ] Benchmark module
- [x] Test module (PR-O)
- [ ] `reservoir_sampling_rotate` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Eval set consumer (meta-HPO) wired (W1)
