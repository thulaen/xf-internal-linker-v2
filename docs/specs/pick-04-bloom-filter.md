# Pick #04 — Bloom Filter for ID Dedup

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 4 |
| **Canonical name** | Bloom Filter (Bloom 1970) |
| **Settings prefix** | `bloom_filter` |
| **Pipeline stage** | Source |
| **Shipped in commit** | `6d925b1` (PR-C, 2026-04-22) |
| **Helper module** | [backend/apps/sources/bloom_filter.py](../../backend/apps/sources/bloom_filter.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `BloomFilterTests` |
| **Benchmark module** | [backend/benchmarks/test_bench_bloom_filter.py](../../backend/benchmarks/test_bench_bloom_filter.py) (pending G6) |

## 2 · Motivation

When importing posts from XenForo and WordPress we re-fetch the same
post IDs across retries, pagination, catch-up runs, and webhook
replays. Without dedup the pipeline rebuilds embeddings for IDs it
has already seen — wasted GPU cycles at ~50 ms per post. A Bloom
filter answers "have I seen this ID?" in O(1) and 12 MB of RAM per
10 M IDs with a controllable false-positive rate (~1 %). False
positives are fine for this use case: we re-query the database to
confirm before rebuilding, so a false "seen" ends up as a single
cheap DB lookup instead of a GPU re-embed.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Bloom, B. H. (1970). "Space/time trade-offs in hash coding with allowable errors." *Communications of the ACM* 13(7): 422-426. |
| **Open-access link** | <https://dl.acm.org/doi/10.1145/362686.362692> |
| **Relevant section(s)** | §2 — formula `m = -n ln(p) / (ln 2)^2` for optimal bit count; §3 — `k = (m/n) ln 2` for optimal hash count |
| **What we faithfully reproduce** | Bloom's optimal sizing formulas. Kirsch-Mitzenmacher double-hashing (2008) for generating `k` hashes from two base hashes — standard technique, cited in §6 of Broder-Mitzenmacher 2004. |
| **What we deliberately diverge on** | Uses `hashlib.blake2b` instead of MurmurHash3 for the two base hashes — blake2b ships with Python 3, is collision-resistant, and benchmarks fast enough for this use case. |

## 4 · Input contract

- **`expected_elements: int`** — anticipated total IDs. Domain
  `[1, ∞)`.
- **`false_positive_rate: float`** — target `p`. Domain `(0, 1)`.
  Typical: `0.01`.
- **`add(item: bytes | str)`** — mutates the filter. No return value.
- **`contains(item: bytes | str)`** → `bool`. `False` is authoritative
  ("definitely not seen"); `True` is probabilistic ("probably seen,
  verify with DB").

**Empty-input.** A freshly-constructed filter returns `False` for
every `contains` until something is added.

## 5 · Output contract

- **`add`** — no return value, O(k).
- **`contains`** — `bool`, O(k).
- **`count_bits_set`** — `int`, returns how many bits are 1. Exposed
  for diagnostics; an unexpectedly high count means the filter is
  saturated and should be rebuilt.
- **`estimated_cardinality`** — `float`. Uses Swamidass-Baldi 2007
  formula: `n_est = -m/k * ln(1 - bits_set/m)`. Accurate to ~1 % when
  `bits_set < 0.5m`.

**Invariants.**

- `contains(x) == True` after `add(x)` — no false negatives ever.
- `count_bits_set ≤ capacity_bits`.
- `add` is idempotent — adding an already-added item doesn't
  increase `bits_set` on an already-all-ones-for-that-item state.

**Determinism.** Bitmap state is deterministic given the same hash
inputs. The `seed` parameter controls blake2b's per-hash personalization
so two filters with different seeds produce different bitmaps — useful
for A/B dedup experiments.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `bloom_filter.enabled` | bool | `true` | Recommended preset policy | No | — | Master toggle for ID-dedup Bloom usage |
| `bloom_filter.expected_elements` | int | `10_000_000` | Plan §Source layer: "12 MB per 10 M IDs" is the documented memory ceiling | No | — | **Correctness/sizing param — do not tune.** Rebuild the filter with a larger `expected_elements` if the real corpus outgrows this; TPE would only inflate memory. |
| `bloom_filter.false_positive_rate` | float | `0.01` | Bloom 1970 §2 — 1 % FPR is the standard configuration; yields `m ≈ 9.6n` bits | No | — | **Correctness param — do not tune.** Lower FPR costs linear extra memory; higher FPR floods downstream DB with verify-lookups. |
| `bloom_filter.seed` | int | `0` | Bloom 1970 — not parameterised in the paper; added here for A/B dedup experiments | No | — | Changes the hash personalization; mutually-incompatible filters under different seeds |

**No hyperparameters here are TPE-tuned.** This is a correctness
primitive — the plan's 12 MB / 10 M / 1 % FPR triple is the operating
point. An auto-tuner would chase false-positive-rate "improvements"
that only shift memory around without improving NDCG.

## 7 · Pseudocode

```
function optimal_params(n, p):
    m = ceil(-n * ln(p) / (ln 2) ** 2)        # bits
    k = round((m / n) * ln 2)                  # hashes
    return m, k

# Kirsch-Mitzenmacher double-hashing with blake2b:
function indices(item, m, k, seed):
    h = blake2b(item, digest_size=16, person=f"bloom-{seed}".encode())
    a = int.from_bytes(h[:8],  "big")
    b = int.from_bytes(h[8:], "big")
    return [(a + i * b) % m for i in 0..k-1]

function add(item):
    for idx in indices(item, m, k, seed):
        bitmap[idx] = 1

function contains(item):
    for idx in indices(item, m, k, seed):
        if bitmap[idx] == 0:
            return False
    return True
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/sync/services/xenforo_api.py` | Post ID strings | Skip re-fetch on `True`; DB verify if uncertain |
| `apps/sync/services/wordpress_api.py` | WP post GUIDs | Same |
| `apps/crawler/services/site_crawler.py` | Canonical URLs | Skip re-crawl |

**Wiring status.** Not yet imported. W2 wires the syncers + crawler
to use the Bloom helper.

## 9 · Scheduled-updates job

- **Key:** `bloom_filter_ids_rebuild`
- **Cadence:** weekly (Mon 13:10)
- **Priority:** critical
- **Estimate:** 5 min
- **Multicore:** yes (hash computation)
- **Why rebuild:** the filter monotonically accumulates bits; after
  weeks the count approaches `expected_elements` and FPR grows past
  `false_positive_rate`. A weekly rebuild seeds a fresh filter from
  the authoritative DB IDs.
- **RAM budget:** 12 MB (matching plan's 10 M-ID budget).
- **Disk budget:** 12 MB (bitmap snapshot for persistence).

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | 12 MB @ 10 M elements / 1 % FPR | formula in §6 |
| Disk | 12 MB bitmap snapshot | — |
| CPU `add`/`contains` | < 2 µs | benchmark small |
| CPU rebuild from DB | ~5 min for 10 M IDs | weekly job |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_no_false_negatives` | Added items always contain |
| `test_false_positive_rate_within_target` | 10 000 adds + 10 000 queries, FPR ≤ 2 % |
| `test_optimal_params_match_paper` | Formula agreement with Bloom 1970 §2 |
| `test_empty_filter_returns_false` | Initial state |
| `test_bitmap_idempotent_under_duplicate_adds` | No regression on repeats |
| `test_estimated_cardinality_tracks_truth` | Swamidass-Baldi formula |
| `test_different_seeds_produce_different_bitmaps` | Seed matters |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 000 adds + 1 000 contains | < 5 ms | > 50 ms |
| medium | 100 000 adds + 100 000 contains | < 300 ms | > 3 s |
| large | 10 000 000 adds + 10 000 000 contains | < 40 s | > 5 min |

## 13 · Edge cases & failure modes

- **Filter saturation.** `bits_set / capacity_bits > 0.5` → FPR is
  already worse than target. The scheduled rebuild addresses this;
  operators also get an alert via `diagnostics/health.py` (wiring
  TBD).
- **Filter corruption.** On startup the filter is rehydrated from
  disk; a CRC mismatch triggers a re-seed from the DB (same code
  path as the weekly rebuild).
- **Hash input type mismatch.** `add("x")` and `add(b"x")` hash the
  same bytes only because the helper internally encodes to UTF-8
  bytes. Changing the encoding would invalidate every persisted
  filter.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| — | Standalone |

| Downstream | Reason |
|---|---|
| #5 HyperLogLog | HLL estimates **distinct** IDs, Bloom tests **membership** — different questions over the same ID stream; shared ingestion path |
| #12 SHA-256 Page Fingerprint | Content-level dedup; complements ID-level dedup |

## 15 · Governance checklist

- [ ] `bloom_filter.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry (12 MB RAM budget)
- [x] Helper module (PR-C)
- [ ] Benchmark module
- [x] Test module (PR-C)
- [ ] `bloom_filter_ids_rebuild` scheduled job registered (W1)
- [ ] Syncers + crawler wired (W2)
