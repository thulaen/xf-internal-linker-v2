# Pick #13 — NFKC Unicode Normalization

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 13 |
| **Canonical name** | NFKC Unicode normalization (UAX #15) |
| **Settings prefix** | `nfkc` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | `a4771e8` (PR-E, 2026-04-22) |
| **Helper module** | [backend/apps/sources/normalize.py](../../backend/apps/sources/normalize.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `NfkcNormaliseTests` |
| **Benchmark module** | `backend/benchmarks/test_bench_nfkc.py` (pending G6) |

## 2 · Motivation

Two glyphs that look identical to a human can have different byte
sequences: `"café"` with precomposed `U+00E9`, versus `"café"` as
`e` + combining acute `U+0301`. Fullwidth digit `１` vs ASCII `1`.
Greek final-sigma ``ς`` vs interior-sigma `σ`. Every downstream step
— hashing, BM25, BGE-M3 embedding, phrase matching — treats them as
distinct unless the text is normalised first. NFKC does the
aggressive compatibility decomposition + canonical composition that
folds these into their canonical forms.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Unicode Consortium. (2023). *Unicode Standard Annex #15 — Unicode Normalization Forms.* |
| **Open-access link** | <https://unicode.org/reports/tr15/> |
| **Relevant section(s)** | §1.2 table of forms; §5 "Compatibility Composition" (NFKC algorithm); §12 "Implementation" — the stdlib `unicodedata.normalize("NFKC", s)` is a faithful implementation. |
| **What we faithfully reproduce** | Calls `unicodedata.normalize("NFKC", s)` directly. |
| **What we deliberately diverge on** | Nothing — we're a thin wrapper. The wrapper's value is centralising the choice of form: changing NFKC to NFC in the future is a one-line edit here instead of a repo-wide grep. |

## 4 · Input contract

- **`nfkc(text: str) -> str`** — returns the NFKC-normalised form.
  `None` or the empty string pass through unchanged.
- **`nfkc_all(texts: Iterable[str]) -> list[str]`** — vectorised
  version. Empty strings pass through.
- **`is_normalised(text: str) -> bool`** — no-op detector; useful
  before re-running the pipeline to skip already-normalised docs.

## 5 · Output contract

- `str` — always the same length or shorter (compatibility
  decomposition can reduce width, e.g. fullwidth → ASCII).
- **Invariants.**
  - Idempotent: `nfkc(nfkc(s)) == nfkc(s)`.
  - Equivalence preserved: `nfkc(a) == nfkc(b)` whenever `a` and `b`
    are canonically equivalent per UAX #15.
- **Determinism.** Fully deterministic, stdlib.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `nfkc.enabled` | bool | `true` | Recommended preset policy | No | — | Off = raw text passes through |
| `nfkc.form` | str (enum) | `"NFKC"` | Plan-spec pick #13 — NFKC is the most aggressive form, correct for retrieval | No | — | Alternatives: `NFC`, `NFD`, `NFKD`. NFKC chosen for IR. |

## 7 · Pseudocode

```
import unicodedata

function nfkc(text):
    if not text: return text
    return unicodedata.normalize("NFKC", text)
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/text_cleaner.py` | Raw extracted text | Normalised text flows to tokenisation + embedding |
| `apps/pipeline/services/sentence_splitter.py` | Same | Sentence boundaries are more consistent after NFKC |
| `apps/sources/sha256_fingerprint.py` (future) | Clean text before hashing | Stable hashes across canonically-equivalent inputs |

**Wiring status.** Helper exists (PR-E). Pipeline does NOT yet
normalise — W2 inserts a call in `text_cleaner.py` before BS4
cleanup.

## 9 · Scheduled-updates job

None — runs inline with parse.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 2× input string | stdlib |
| Disk | 0 | — |
| CPU | ~1 µs per 100 chars | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_precomposed_equals_decomposed_after_nfkc` | Canonical equivalence |
| `test_fullwidth_digits_folded_to_ascii` | Compatibility fold |
| `test_idempotent` | §5 invariant |
| `test_empty_string_passthrough` | Degenerate input |
| `test_none_input_returns_none` | Safety net |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 000 short strings | < 5 ms | > 50 ms |
| medium | 1 000 articles (~10 KB each) | < 200 ms | > 2 s |
| large | 1 000 000 articles | < 3 min | > 30 min |

## 13 · Edge cases & failure modes

- **Surrogate-pair handling** — stdlib is correct.
- **Non-UTF-8 input** — `unicodedata.normalize` requires `str`; caller
  must decode first (see pick #11).
- **Historical combining marks** — preserved; NFKC doesn't strip
  diacritics (that would be locale-specific).

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #11 chardet | Decodes bytes to `str` before normalisation |

| Downstream | Reason |
|---|---|
| #12 SHA-256 | Hashes post-NFKC text for stable dedup |
| #21 Snowball stemmer | Works on NFKC-normalised input |

## 15 · Governance checklist

- [ ] `nfkc.enabled` seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-E)
- [x] Benchmark module
- [x] Test module (PR-E)
- [ ] Pipeline wired (W2)
