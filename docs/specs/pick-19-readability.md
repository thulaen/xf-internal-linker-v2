# Pick #19 — Flesch-Kincaid + Gunning Fog readability

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 19 |
| **Canonical name** | Flesch-Kincaid Grade + Gunning Fog |
| **Settings prefix** | `readability` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | `a4771e8` (PR-E, 2026-04-22) |
| **Helper module** | [backend/apps/sources/readability.py](../../backend/apps/sources/readability.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `ReadabilityTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_readability.py` (pending G6) |

## 2 · Motivation

A single "reading grade level" per document lets operators ban
jargon-heavy matches when the context is an ELI5 post, or ban
beginner-level matches when the context is a deep technical thread.
Flesch-Kincaid gives a US-school-grade number; Gunning Fog gives a
similar number using a different complex-word definition. Shipping
both lets operators see where the two formulas agree (a high-
confidence reading-level signal).

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Flesch, R. (1948). "A new readability yardstick." *Journal of Applied Psychology* 32(3): 221-233. Kincaid, J. P., Fishburne, R. P., Rogers, R. L. & Chissom, B. S. (1975). "Derivation of new readability formulas." Naval Technical Training Command Report 8-75. Gunning, R. (1952). *The Technique of Clear Writing.* McGraw-Hill. |
| **Open-access link** | Flesch: <https://doi.org/10.1037/h0057532>; Kincaid (Navy report): <https://apps.dtic.mil/sti/citations/ADA006655>; Gunning: out-of-print book. |
| **Relevant section(s)** | Kincaid 1975 eq. 1: `FKGL = 0.39(W/S) + 11.8(Syl/W) - 15.59`. Gunning §3: `Fog = 0.4((W/S) + 100(C/W))` with `C` = complex-word count (≥ 3 syllables, excluding proper/compound/inflected). |
| **What we faithfully reproduce** | Both formulas. Syllable counting by vowel-cluster heuristic; complex-word ≥ 3 syllables (simplified from Gunning's hand-tuned exclusions — tracks the stricter version within ~0.5 grades on English prose). |
| **What we deliberately diverge on** | We skip the proper-noun / compound / inflected-suffix filters from Gunning. Plan §Parse notes the divergence is ~0.5 grade levels on English prose. |

## 4 · Input contract

- **`score(text: str) -> ReadabilityScores`** — returns both metrics.
- Empty text → `ReadabilityScores(words=0, sentences=0, syllables=0,
  complex_words=0, flesch_kincaid_grade=0.0, gunning_fog=0.0)`.

## 5 · Output contract

- `ReadabilityScores` frozen dataclass: `words`, `sentences`,
  `syllables`, `complex_words`, `flesch_kincaid_grade: float`,
  `gunning_fog: float`.
- **Invariants.**
  - `complex_words <= words`.
  - Grade values ≥ 0.
- **Determinism.** Fully deterministic (stdlib only).

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `readability.enabled` | bool | `true` | Recommended preset policy | No | — | Master toggle |
| `readability.complex_syllable_threshold` | int | `3` | Gunning 1952 §3 | No | — | Changing would break comparability with Gunning's scale |
| `readability.min_text_words` | int | `30` | Empirical — texts under ~30 words give unstable grade estimates | Yes | `int(10, 200)` | Below threshold, metrics not computed |

## 7 · Pseudocode

See `apps/sources/readability.py` — helper is stdlib-only. Core flow:

```
function score(text):
    sentences = pysbd_split(text)       # pick #15
    words = whitespace_tokens(text)
    if len(words) < min_text_words:
        return empty_scores()
    syllables = sum(count_syllables(w) for w in words)
    complex_words = sum(1 for w in words if count_syllables(w) >= complex_syllable_threshold)

    fkgl = 0.39 * (len(words)/len(sentences)) + 11.8 * (syllables/len(words)) - 15.59
    fog  = 0.4 * ((len(words)/len(sentences)) + 100 * (complex_words/len(words)))
    return ReadabilityScores(words=len(words), sentences=len(sentences),
                             syllables=syllables, complex_words=complex_words,
                             flesch_kincaid_grade=fkgl, gunning_fog=fog)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/text_cleaner.py` | Cleaned body | Stores grades on `ContentItem`; pick #51 uses them to reject seed candidates above `readability_grade_max` |
| `apps/pipeline/services/ranker.py` | Two docs' grades | Proximity-in-grade signal (bias toward similarly-leveled content) |

## 9 · Scheduled-updates job

None — inline with parse.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 100 KB per call | — |
| Disk | 0 | — |
| CPU | ~50 µs per 1 KB text | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_simple_text_low_grade` | "See Spot run." ≈ 1st grade |
| `test_dense_text_high_grade` | Academic paragraph ≥ 12 |
| `test_empty_returns_zeros` | Degenerate |
| `test_syllable_counter_handles_silent_e` | `"make"` = 1 |
| `test_syllable_counter_handles_trailing_le` | `"little"` = 2 |
| `test_complex_words_counted_correctly` | Threshold sanity |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 000 × 500 char articles | < 50 ms | > 500 ms |
| medium | 100 000 × 5 KB articles | < 30 s | > 5 min |
| large | 10 000 000 × 5 KB articles | < 1 h | > 8 h |

## 13 · Edge cases & failure modes

- **All-caps titles** — tokeniser treats them fine; syllable counter
  handles them.
- **Numbers + code** — counted as words with variable syllable
  counts; minor noise.
- **Non-English text** — metrics meaningless; operator filters by
  pick #14 first.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #13 NFKC | Normalised input |
| #15 PySBD | Sentence counter |

| Downstream | Reason |
|---|---|
| #51 Auto-seeder | Uses `readability_grade_max=16` to reject seeds |

## 15 · Governance checklist

- [ ] `readability.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-E)
- [ ] Benchmark module
- [x] Test module (PR-E)
- [ ] Pipeline wired (W2)
