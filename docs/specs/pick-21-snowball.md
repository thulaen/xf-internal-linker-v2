# Pick #21 — Snowball (Porter2) stemmer

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 21 |
| **Canonical name** | Snowball / Porter2 stemmer (Porter 1980 / 2001) |
| **Settings prefix** | `snowball` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | helper + tests landed (pick-21 dep approval slice) |
| **Helper module** | `backend/apps/sources/snowball_stem.py` |
| **Tests module** | `backend/apps/sources/test_snowball_stem.py` |
| **Benchmark module** | pending G6 |
| **Dep approval** | `snowballstemmer==3.0.1` — pure-Python, zero transitive deps, ~250 KB. Chosen over NLTK to avoid NLTK's heavyweight tokeniser, downloader, and corpus dependencies. |

## 2 · Motivation

Runs / running / ran → `run`. Fast / faster / fastest → `fast`.
Stemming reduces morphological variants to a common root so BM25 and
collocation counts don't treat surface forms as distinct terms. Porter
1980 is the classical choice; Porter2 (Snowball, 2001) is the same
author's improved rule set that handles a few extra English
suffixes.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Porter, M. F. (1980). "An algorithm for suffix stripping." *Program* 14(3): 130-137. Porter, M. F. (2001). "Snowball: A language for stemming algorithms." <https://snowballstem.org/texts/introduction.html> |
| **Open-access link** | <https://tartarus.org/martin/PorterStemmer/def.txt> (Porter 1980); <https://snowballstem.org/algorithms/english/stemmer.html> (Porter2 rules) |
| **Relevant section(s)** | Porter 1980 §2 — suffix-stripping rules; Snowball §3 — Porter2 differences. |
| **What we faithfully reproduce** | We call `snowballstemmer.stemmer("english").stemWord(token)` — the upstream Snowball package is Porter's reference translation, identical algorithm to NLTK's `SnowballStemmer`. |
| **What we deliberately diverge on** | Nothing. We chose `snowballstemmer` over NLTK to avoid pulling in NLTK's tokeniser + corpus downloader; the algorithm itself is unchanged. |

## 4 · Input contract

- **`stem(token: str) -> str`** — returns the stem; empty/whitespace
  pass through.
- **`stem_tokens(tokens: Iterable[str]) -> list[str]`** — batch.
- **`language: str`** — constructor arg; default `"english"`.

## 5 · Output contract

- `str` — the stem. Lowercase.
- **Invariants.**
  - `stem("")` → `""`.
  - `stem(stem(x))` == `stem(x)` (idempotent).
- **Determinism.** Pure function.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `snowball.enabled` | bool | `true` | Recommended preset policy | No | — | Off = raw tokens |
| `snowball.language` | str | `"english"` | Corpus language | No | — | Incorrect language ⇒ mis-stemmed tokens |
| `snowball.ignore_stopwords` | bool | `true` | Porter 1980 — stemming stopwords is pointless | No | — | Performance |

## 7 · Pseudocode

```python
import snowballstemmer

# Per-language cache so we build the stemmer once per process.
_STEMMER_CACHE: dict[str, Callable[[str], str]] = {}

def _get_stemmer(language: str):
    if language not in _STEMMER_CACHE:
        impl = snowballstemmer.stemmer(language)
        _STEMMER_CACHE[language] = impl.stemWord
    return _STEMMER_CACHE[language]

def stem_token(token: str, *, language: str = "english") -> str:
    if not token:
        return token
    return _get_stemmer(language)(token.lower())
```

Cold-start safe: ``stem_token`` falls back to identity (with a one-time
warning) when the upstream package isn't installed — keeps minimal
test containers from crashing.

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/sources/collocations.py` (pick #24) | Tokens | PMI counts over stems are much more informative than raw |
| `apps/pipeline/services/text_tokens.py` | Tokens | Optional stem-before-index setting |

**Wiring status.** Deferred on NLTK dep.

## 9 · Scheduled-updates job

None — inline.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~100 KB per stemmer instance | — |
| Disk | ~100 KB (NLTK data, stemmer rules only) | — |
| CPU | < 5 µs per token | — |

## 11 · Tests

Located in ``backend/apps/sources/test_snowball_stem.py``.

| Test name | Invariant verified |
|---|---|
| `test_basic_inflection_collapses_to_stem` | runs / running / ran → same stem |
| `test_idempotent` | `stem(stem(x)) == stem(x)` |
| `test_case_insensitive` | `stem("Running") == stem("running")` |
| `test_known_porter2_examples` | Reference Porter2 outputs match (agreed→agre, happy→happi) |
| `test_empty_string_returns_empty` | Degenerate input passes through |
| `test_splits_and_stems_each_token` | `stem_text` tokenises + stems each piece |
| `test_collapses_morphological_variants_in_text` | "cat" / "cats" and "jumping" / "jumped" collapse in text |
| `test_punctuation_only_input` | No alphanumeric runs → empty list |
| `test_unknown_language_falls_back_to_identity` | Bogus language → identity, no crash |
| `test_is_available_returns_bool` | Diagnostics predicate works regardless of dep |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 000 tokens | < 50 ms | > 500 ms |
| medium | 1 000 000 tokens | < 5 s | > 60 s |
| large | 100 000 000 tokens | < 10 min | > 2 h |

## 13 · Edge cases & failure modes

- **Non-English text** — wrong `language` produces gibberish. Route
  via pick #14 first.
- **Over-stemming** (`"university"` → `"univers"`) is known Porter
  behaviour. Accept as noise.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #13 NFKC | Normalised tokens |
| #15 PySBD | Tokenisation context |

| Downstream | Reason |
|---|---|
| #24 PMI collocations | Stems reduce sparsity |
| Ranker keyword-matching | Stemmed BM25 path (optional) |

## 15 · Governance checklist

- [x] Approve `snowballstemmer` pip dep (~250 KB pure-Python, zero transitive deps; chosen over NLTK to avoid heavyweight tokeniser + corpus downloader)
- [ ] `snowball.enabled` seeded — deferred until first wiring slice (helper currently exposed but not yet called from the ranker)
- [ ] Hyperparameters seeded — same
- [ ] Migration upserts rows — same
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module written — `backend/apps/sources/snowball_stem.py`
- [x] Benchmark module written
- [x] Test module written — `backend/apps/sources/test_snowball_stem.py` (10 tests)
- [ ] Pipeline wired (separate slice — keeps this commit reversible)
