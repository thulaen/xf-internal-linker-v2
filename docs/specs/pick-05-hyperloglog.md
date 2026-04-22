# Pick #05 — HyperLogLog cardinality estimator

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 5 |
| **Canonical name** | HyperLogLog (Flajolet, Fusy, Gandouet, Meunier 2007) |
| **Settings prefix** | `hyperloglog` |
| **Pipeline stage** | Source |
| **Shipped in commit** | `6d925b1` (PR-C, 2026-04-22) |
| **Helper module** | [backend/apps/sources/hyperloglog.py](../../backend/apps/sources/hyperloglog.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `HyperLogLogTests` |
| **Benchmark module** | [backend/benchmarks/test_bench_hyperloglog.py](../../backend/benchmarks/test_bench_hyperloglog.py) (pending G6) |

## 2 · Motivation

"How many unique posts did we ingest this week?" is the canonical
cardinality question — and doing it exactly requires storing every
ID ever seen. HyperLogLog answers the same question with ~12 KB of
state per stream and a relative error of about `1.04 / sqrt(m)` —
i.e. ~0.8 % error at precision 14 (`m = 16 384`). The operator-facing
dashboard uses it to show fresh vs duplicate crawl counts without a
GROUP BY over 10 M rows.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Flajolet, P., Fusy, É., Gandouet, O. & Meunier, F. (2007). "HyperLogLog: the analysis of a near-optimal cardinality estimation algorithm." *Proceedings of the Conference on Analysis of Algorithms (AofA)*, DMTCS Proc. AH. pp. 137-156. |
| **Open-access link** | <https://algo.inria.fr/flajolet/Publications/FlFuGaMe07.pdf> |
| **Relevant section(s)** | §4 — estimator formula with `α_m` correction constants; §6 — small-range (linear-counting) correction below `5m/2`. |
| **What we faithfully reproduce** | Register layout (`m = 2^p` buckets, each a 6-bit leading-zero count), harmonic-mean estimator with the paper's `α_m` constants, small-range linear-counting correction. |
| **What we deliberately diverge on** | Use `hashlib.blake2b` → 64-bit digest (the paper uses a 32-bit hash family) — avoids the 2^32-limit bias without the empirical bias-correction table HLL++ needs. Simpler than HLL++ (Heule 2013) and within the paper's error bound at the cardinalities the linker operates in (≤ 10 M). |

## 4 · Input contract

- **`precision: int`** — register count bits. Domain `[4, 16]`.
  `m = 2^precision`. Default 14 → 16 384 buckets → ~12 KB state.
- **`add(item: bytes | str)`** — O(1) hash + max.
- **`merge(other: HyperLogLog)`** — mutates `self` into the union of
  the two streams. Requires matching precision.
- **`count() -> float`** — current cardinality estimate.

## 5 · Output contract

- **`count()`** → `float` (fractional because of bias correction).
- **`relative_error()`** → `float` — the paper's theoretical bound
  `1.04 / sqrt(m)`, independent of current cardinality.
- **Invariants.**
  - `count()` is monotonic non-decreasing under `add`.
  - `count()` is unchanged under `add` of an already-seen item, in
    expectation (actual register bits may fluctuate but estimate
    doesn't grow without a new hash hitting a higher leading-zero
    count).
  - After `A.merge(B)`, `A.count() ≈ |items(A) ∪ items(B)|`.
- **Determinism.** Given the same seed, the register state is
  deterministic.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `hyperloglog.enabled` | bool | `true` | Recommended preset policy | No | — | Master toggle |
| `hyperloglog.precision` | int | `14` | Flajolet 2007 §4.3 — precision 14 balances 12 KB state vs 0.8 % error | No | — | **Correctness param.** Lower precision = less RAM, larger error; higher = more RAM, smaller error. Tuning risks inconsistent estimates across runs. |
| `hyperloglog.seed` | int | `0` | Flajolet 2007 — unseeded in the paper; added for A/B stream experiments | No | — | Changes blake2b personalization; incompatible across seeds |

All HLL params are correctness-flavoured. TPE has nothing to
optimise here — NDCG is not a function of the cardinality-counter
precision.

## 7 · Pseudocode

```
# m = 2^p buckets, registers = [0] * m.
# For each item:
function add(item):
    h = blake2b(item, digest_size=8, person=f"hll-{seed}".encode())
    bits = int.from_bytes(h, "big")  # 64-bit
    bucket_index = bits & (m - 1)
    w = bits >> p                    # remaining 64-p bits
    leading_zeros = (64 - p) - w.bit_length() + 1
    registers[bucket_index] = max(registers[bucket_index], leading_zeros)

# Estimator (Flajolet 2007 §4):
function count():
    harmonic_mean = m / sum(2 ** -r for r in registers)
    raw = alpha_m * m * harmonic_mean
    zeros = sum(1 for r in registers if r == 0)
    if raw <= 2.5 * m and zeros != 0:
        # small-range linear counting (§6)
        return m * ln(m / zeros)
    return raw
```

`alpha_m` comes from Flajolet 2007 Table 3 — precomputed for m ∈
{16, 32, 64, …, 65536}.

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/crawler/services/site_crawler.py` | URLs seen this crawl | Dashboard metric: unique pages crawled |
| `apps/sync/services/*` | Post IDs | "Unique posts synced today" card |
| `apps/analytics/*` | Query strings | Unique queries per day |

**Wiring status.** Not yet imported. W2.

## 9 · Scheduled-updates job

None — HLL runs inline with ingestion. A daily "reset" might be added
if operators want per-day cardinality rather than running-total.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~12 KB @ precision 14 | 6 bits × 16 384 buckets |
| Disk | optional 12 KB persistence snapshot | — |
| CPU `add` | < 2 µs | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_empty_returns_zero` | Degenerate case |
| `test_single_add_returns_near_one` | Within ~20 % for small n (bias tolerated at low cardinality) |
| `test_one_million_adds_within_error_bound` | 10^6 adds → |estimate − 10^6| < 10^6 × 2.08 % (2 σ bound at p=14) |
| `test_merge_equals_union_cardinality` | Union semantics |
| `test_merge_mismatched_precision_rejected` | Input validation |
| `test_different_seeds_produce_different_registers` | Seed matters |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 000 adds | < 3 ms | > 30 ms |
| medium | 1 000 000 adds | < 3 s | > 30 s |
| large | 10 000 000 adds | < 30 s | > 5 min |

## 13 · Edge cases & failure modes

- **Precision out of `[4, 16]`** — `ValueError`.
- **Merge across incompatible precisions** — `ValueError`.
- **Blake2b determinism across Python versions** — ships stdlib-only
  since Python 3.6, stable. Persisted registers from 3.12 decode
  fine on 3.13.
- **Bias at very low n** (n < 50) — small-range linear correction
  kicks in; still 5-10 % error at n=10 due to the estimator's
  asymptotic nature. Dashboard annotations acknowledge this.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| — | Standalone |

| Downstream | Reason |
|---|---|
| #4 Bloom Filter | Paired dedup stack: Bloom for "seen?" (membership), HLL for "how many unique?" (cardinality) |

## 15 · Governance checklist

- [ ] `hyperloglog.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry (12 KB RAM budget)
- [x] Helper module (PR-C)
- [ ] Benchmark module
- [x] Test module (PR-C)
- [ ] Crawler / syncer / analytics wired (W2)
- [ ] Dashboard card rendering `count()` (W4 / dashboard extension)
