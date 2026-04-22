# Pick #24 — PMI collocations (Church & Hanks 1990)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 24 |
| **Canonical name** | Pointwise Mutual Information + NPMI collocation scoring |
| **Settings prefix** | `collocations_pmi` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | `a4771e8` (PR-E, 2026-04-22) |
| **Helper module** | [backend/apps/sources/collocations.py](../../backend/apps/sources/collocations.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `CollocationsPMITests` |
| **Benchmark module** | `backend/benchmarks/test_bench_collocations.py` (pending G6) |

## 2 · Motivation

Two tokens that keep appearing together ("social", "media"; "machine",
"learning") form a **collocation** — the pair carries meaning the
individual tokens don't. PMI measures association: `log( P(A,B) /
(P(A) × P(B)) )`. Large positive PMI = pair co-occurs far more than
chance would predict. The linker uses collocation phrases to improve
BM25 phrase matching and to de-duplicate near-identical "social media
marketing" vs "marketing on social media" suggestions.

Complements the existing Dunning G² in `apps/cooccurrence/services.py`:
G² handles small counts gracefully (rare events), PMI surfaces
genuinely associated pairs regardless of frequency. Operators ship
both scores to the ranker.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Church, K. W. & Hanks, P. (1990). "Word association norms, mutual information, and lexicography." *Computational Linguistics* 16(1): 22-29. Bouma, G. (2009). "Normalized (pointwise) mutual information in collocation extraction." *Proceedings of GSCL*, pp. 31-40. |
| **Open-access link** | Church-Hanks: <https://aclanthology.org/J90-1003/>. Bouma: <https://svn.spraakdata.gu.se/repos/gerlof/pub/www/Docs/npmi-pfd.pdf> |
| **Relevant section(s)** | Church-Hanks §2 — PMI formula; Bouma 2009 §4 — NPMI normalisation bounded to `[-1, 1]`. |
| **What we faithfully reproduce** | Both formulas, base-2 logs (easier intuition). |
| **What we deliberately diverge on** | Nothing — pure arithmetic helper. |

## 4 · Input contract

- **`pmi(*, joint_count: int, count_a: int, count_b: int,
  total: int) -> float`** — base-2 PMI.
- **`normalised_pmi(*, joint_count: int, count_a: int, count_b: int,
  total: int) -> float`** — NPMI in `[-1, 1]`.
- All counts must be non-negative; `joint_count ≤ min(count_a,
  count_b)`; `total > 0`.

## 5 · Output contract

- `float`.
- **Invariants.**
  - PMI is positive for over-associated pairs, negative for under-associated.
  - NPMI is bounded in `[-1, 1]` (monotone transform).
- **Determinism.** Pure arithmetic.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `collocations_pmi.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no PMI signal |
| `collocations_pmi.min_joint_count` | int | `5` | Church-Hanks §3 — pairs below ~5 joint occurrences are noisy | Yes | `int(2, 50)` | Higher = fewer, more confident collocations |
| `collocations_pmi.min_pmi` | float | `2.0` | Church-Hanks §3 — PMI ≥ 2 (8× chance) is the standard "genuine collocation" threshold | Yes | `uniform(0.0, 6.0)` | Higher = stricter filtering |
| `collocations_pmi.rebuild_cadence_days` | int | `7` | Weekly collocation refresh job | Yes | `int(1, 30)` | More frequent adapts to new vocabulary faster |

## 7 · Pseudocode

See `apps/sources/collocations.py`. Core:

```
function pmi(joint, count_a, count_b, total):
    p_ab = max(joint / total, 1e-12)
    p_a  = max(count_a / total, 1e-12)
    p_b  = max(count_b / total, 1e-12)
    return log2(p_ab / (p_a * p_b))

function normalised_pmi(joint, count_a, count_b, total):
    if joint == 0:
        return -1.0
    raw = pmi(joint, count_a, count_b, total)
    # Bouma 2009: NPMI = PMI / -log(P(A,B))
    p_ab = max(joint / total, 1e-12)
    return raw / -log2(p_ab)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/cooccurrence/services.py` | Dunning G² already; will also emit PMI + NPMI | Both scores feed the ranker |
| `apps/pipeline/services/phrase_matching.py` | Known collocations | Longer n-gram matching in retrieval |

## 9 · Scheduled-updates job

- **Key:** `collocations_pmi_rebuild`
- **Cadence:** weekly (Fri 15:30)
- **Priority:** medium
- **Estimate:** 10 min
- **Multicore:** yes
- **RAM:** ≤ 32 MB (stream through pair counts)
- **Disk:** ≤ 10 MB (collocation table)

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 100 KB per call (streaming) | — |
| Disk | < 10 MB per corpus collocation table | — |
| CPU | ~100 ns per pair score | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_over_associated_pair_positive_pmi` | Direction |
| `test_random_pair_near_zero_pmi` | Baseline |
| `test_npmi_bounded_in_minus_one_one` | Bouma property |
| `test_rejects_invalid_counts` | Input validation |
| `test_zero_joint_npmi_is_minus_one` | Edge case |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 000 pair scores | < 10 ms | > 100 ms |
| medium | 10 000 000 pair scores | < 5 s | > 60 s |
| large | 1 000 000 000 pair scores | < 10 min | > 2 h |

## 13 · Edge cases & failure modes

- **`joint_count > min(count_a, count_b)`** — logically impossible;
  `ValueError`.
- **All-zero counts** — rare but valid (fresh corpus). Helper returns
  `-inf`; callers should filter by `min_joint_count`.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #13 NFKC, #15 PySBD, #21 Snowball | Cleaner tokens = denser joint counts |

| Downstream | Reason |
|---|---|
| Phrase-matching ranker | Uses collocation phrases as extra tokens |
| #17 YAKE | YAKE is per-doc; PMI is per-corpus — orthogonal signals |

## 15 · Governance checklist

- [ ] `collocations_pmi.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-E)
- [ ] Benchmark module
- [x] Test module (PR-E)
- [ ] `collocations_pmi_rebuild` scheduled job registered (W1)
- [ ] TPE search space declared
- [ ] Phrase-matching wired (W3)
