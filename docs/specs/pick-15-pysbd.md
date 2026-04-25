# Pick #15 — PySBD sentence boundary disambiguation

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 15 |
| **Canonical name** | PySBD (Python Sentence Boundary Disambiguation) |
| **Settings prefix** | `pysbd` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | **NOT YET — spec was incorrect**: existing `sentence_splitter.py` uses spaCy + regex, NOT PySBD. Phase 6 will add PySBD as an opt-in alternative when robustness on edge cases (abbreviations, ellipses, scientific text) matters. |
| **Helper module** | `backend/apps/sources/pysbd_segmenter.py` (Phase 6 — `apps.parse.*` namespace from original plan is forbidden by anti-spaghetti rule §1) |
| **Tests module** | `backend/apps/sources/test_pysbd_segmenter.py` (Phase 6) |
| **Benchmark module** | `backend/benchmarks/test_bench_pysbd.py` (pending G6) |

## 2 · Motivation

Splitting text into sentences is harder than splitting on `. `. Think
of "Dr. Smith went to Washington." or "See U.S.A. for details." or
any text with ellipses, abbreviations, numbered lists, or decimal
numbers. A good splitter uses dozens of language-specific rules
together — PySBD is a Python port of the Golden-Rule-Set sentence
splitter and consistently beats naive regex + `nltk.sent_tokenize`
on Barbaresi-2021-style benchmarks.

The linker uses sentences as the unit of work for passage-level
scoring, collocations, entity-salience sentence coverage, KenLM
perplexity, and readability metrics. Good sentence boundaries matter
downstream of every parse-stage pick.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Sadvilkar, N. & Neumann, M. (2020). "PySBD: Pragmatic sentence boundary disambiguation." *ACL Workshop on NLP-OSS*. |
| **Open-access link** | <https://aclanthology.org/2020.nlposs-1.15/> |
| **Relevant section(s)** | §2 — design goals vs NLTK / spaCy splitter; §4 — scoring on GoldenRules, achieves 97.9 % F1 vs spaCy's 87.3 % |
| **What we faithfully reproduce** | PySBD's rule set and defaults. We wrap the `Segmenter` class. |
| **What we deliberately diverge on** | Nothing algorithmic. Wrapper adds caching — one `Segmenter` instance per language code to amortise the rules-compilation cost. |

## 4 · Input contract

- **`split_sentences(text: str, language: str = "en") -> list[str]`**
- Empty / whitespace → `[]`.
- Language must be one of PySBD's supported ISO codes; unsupported
  codes fall back to `"en"` with a warning.

## 5 · Output contract

- `list[str]` — each element is a single sentence with leading/
  trailing whitespace stripped.
- **Invariants.**
  - `"".join(split_sentences(t)) ≈ t` (modulo whitespace).
  - No empty strings in the output.
- **Determinism.** Fully deterministic per PySBD version.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `pysbd.enabled` | bool | `true` | Recommended preset policy | No | — | Off = regex fallback (fast, worse) |
| `pysbd.default_language` | str | `"en"` | Corpus is predominantly English | No | — | Falls back to `en` for unsupported codes |
| `pysbd.char_span` | bool | `false` | PySBD option — returns character offsets when `true`. We don't use them, and enabling adds overhead | No | — | Correctness: keep disabled unless callers need offsets |

## 7 · Pseudocode

```
import pysbd
from functools import lru_cache

@lru_cache(maxsize=8)
def _segmenter(language):
    return pysbd.Segmenter(language=language, clean=False, char_span=False)

function split_sentences(text, language):
    if not text.strip(): return []
    try:
        seg = _segmenter(language)
    except ValueError:
        seg = _segmenter("en")
    return [s.strip() for s in seg.segment(text) if s.strip()]
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/text_cleaner.py` | NFKC-normalised body | Sentence list used for everything downstream |
| `apps/sources/passages.py` (pick #25) | Sentences | `segment_from_sentences()` builds passage windows |
| `apps/sources/entity_salience.py` (pick #26) | Sentences | Sentence-coverage feature needs sent boundaries |

**Wiring status.** Already wired for the current pipeline. No
re-wiring needed under W2.

## 9 · Scheduled-updates job

None — inline with parse.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~5 MB per language segmenter | library docs |
| Disk | 5 MB pip install | — |
| CPU | ~200 µs per 1 KB of text | benchmark medium |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_splits_simple_sentences` | Canonical path |
| `test_handles_abbreviations` | `Dr. Smith.` is not split |
| `test_handles_ellipses_and_numbered_lists` | Edge cases |
| `test_empty_returns_empty_list` | Degenerate |
| `test_fallback_for_unsupported_language` | Language router |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 articles × 1 KB | < 200 ms | > 2 s |
| medium | 10 000 articles × 5 KB | < 60 s | > 10 min |
| large | 100 000 articles × 5 KB | < 15 min | > 2 h |

## 13 · Edge cases & failure modes

- **Code blocks / quoted text** — split as regular sentences; not
  perfect. Future enhancement could detect code fences.
- **Languages not in PySBD's rule list** — fallback to `en` rules;
  quality degrades for scripts without spaces (Chinese, Japanese).
  For CJK we could add a Jieba-based splitter in a later slice.
- **Very long single sentence** — passed through as-is; passage
  windowing handles length.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #13 NFKC | Normalised input |
| #14 FastText LangID | Selects `language` arg |

| Downstream | Reason |
|---|---|
| #16 spaCy | Tagger/parser per sentence |
| #19 Readability | Counts sentences |
| #23 KenLM | Perplexity per sentence |
| #24 PMI collocations | Tokens within sentence |
| #25 Passage segmentation | Sentence-aware windows |
| #26 Entity salience | Sentence coverage feature |

## 15 · Governance checklist

- [ ] `pysbd.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (already reused)
- [ ] Benchmark module
- [x] Test module (existing)
- [ ] Nothing to rewire (W2 unchanged)
