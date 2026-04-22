# Pick #17 — YAKE! unsupervised keyword extraction

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 17 |
| **Canonical name** | YAKE! (Yet Another Keyword Extractor) |
| **Settings prefix** | `yake` |
| **Pipeline stage** | Parse |
| **Shipped in commit** | **DEFERRED** — needs `yake` pip dep |
| **Helper module** | `backend/apps/parse/keywords/yake_adapter.py` (plan path) |
| **Tests module** | pending |
| **Benchmark module** | pending G6 |

## 2 · Motivation

Keywords summarise a document in 5-15 terms operators can scan at a
glance. They also anchor "related-topic" links — if post A has keywords
`{"pagerank", "graph", "authority"}` and post B shares 2 of those, the
linker can suggest a cross-link. YAKE! is unsupervised (no training
data needed), single-document (no corpus required), runs in < 10 ms
per article, and handles multiple languages. Campos et al.'s 2020
benchmark shows it competitive with RAKE / TextRank / KP-Miner on
SemEval 2010 + Inspec.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Campos, R., Mangaravite, V., Pasquali, A., Jorge, A., Nunes, C. & Jatowt, A. (2020). "YAKE! Keyword extraction from single documents using multiple local features." *Information Sciences* 509: 257-289. |
| **Open-access link** | <https://www.sciencedirect.com/science/article/pii/S0020025519308588> |
| **Relevant section(s)** | §3 feature set (casing, position, frequency, relatedness, different-sentence); §4.2 scoring formula `S(w) = ∏ features / (sentence_frequency × 1 + term_frequency)` |
| **What we faithfully reproduce** | Call `yake.KeywordExtractor(...).extract_keywords(text)`. |
| **What we deliberately diverge on** | Nothing algorithmic. Adapter standardises the returned dict and enforces a min-score cutoff since the lib's low-scoring tail is typically noise. |

## 4 · Input contract

- **`extract_keywords(text: str, *, language: str = "en", top_k: int = 15,
  max_ngram_size: int = 3, deduplication_threshold: float = 0.9) ->
  list[KeywordResult]`**
- Empty text returns `[]`.

## 5 · Output contract

- `KeywordResult(phrase: str, score: float)` frozen dataclass. Lower
  score = better (YAKE's convention).
- Results sorted ascending by score (best first).

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `yake.enabled` | bool | `true` | Recommended preset policy | No | — | Off = no keyword extraction |
| `yake.language` | str | `"en"` | Corpus language | No | — | YAKE stopword list per language |
| `yake.max_ngram_size` | int | `3` | Campos §4.3 — trigrams capture "machine learning" and "search engine optimization" | Yes | `int(1, 5)` | Bigger n-grams = more specific, rarer |
| `yake.top_k` | int | `15` | Empirical — 15 covers typical article topics | Yes | `int(5, 50)` | Trade UI clutter vs coverage |
| `yake.deduplication_threshold` | float | `0.9` | YAKE default | Yes | `uniform(0.5, 0.99)` | How aggressively near-duplicate phrases are collapsed |
| `yake.window_size` | int | `2` | Campos §4.3 default | Yes | `int(1, 5)` | Context window for relatedness feature |

## 7 · Pseudocode

```
from yake import KeywordExtractor

function extract_keywords(text, language, top_k, max_ngram_size, dedup):
    if not text.strip():
        return []
    kw = KeywordExtractor(
        lan=language,
        n=max_ngram_size,
        dedupLim=dedup,
        top=top_k,
    )
    return [KeywordResult(phrase, score) for phrase, score in kw.extract_keywords(text)]
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/pipeline/services/text_cleaner.py` | Cleaned body | Stores keywords on `ContentItem`, used by related-topic link suggestions |
| `apps/sources/collocations.py` (pick #24) | Complement | Collocations are bigrams from corpus stats; YAKE is per-doc — orthogonal signals |

## 9 · Scheduled-updates job

None — inline with parse.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~5 MB per call | library docs |
| Disk | 5 MB pip install | — |
| CPU | ~10 ms per article | paper §5.3 |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_returns_keywords_for_sample_article` | Canonical path |
| `test_sorted_best_first` | Ordering |
| `test_top_k_caps_output` | Cap |
| `test_empty_returns_empty` | Degenerate |
| `test_language_switch` | Multilingual support |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 × 2 KB | < 1 s | > 10 s |
| medium | 10 000 × 5 KB | < 2 min | > 20 min |
| large | 1 000 000 × 5 KB | < 3 h | > 12 h |

## 13 · Edge cases & failure modes

- **Very short text** — YAKE still returns keywords but scores are
  unstable. Min-length threshold can be added downstream.
- **Code-heavy articles** — tokeniser treats code variables as words
  causing noise. Future enhancement: pre-strip code blocks.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #13 NFKC | Normalised input |
| #14 FastText LangID | Selects YAKE's `lan` parameter |

| Downstream | Reason |
|---|---|
| UI related-topic panel | Operator-facing keyword tags |

## 15 · Governance checklist

- [ ] Approve `yake` pip dep (blocker)
- [ ] `yake.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [ ] Helper module written
- [ ] Benchmark module written
- [ ] Test module written
- [ ] TPE search space declared
- [ ] Pipeline wired (W2)
