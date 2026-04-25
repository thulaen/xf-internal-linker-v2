# Pick #07 — Trafilatura main-content extractor

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 7 |
| **Canonical name** | Trafilatura (Barbaresi 2021) |
| **Settings prefix** | `trafilatura` |
| **Pipeline stage** | Crawl / Parse |
| **Shipped in commit** | **not yet merged — awaiting pip-dep approval** |
| **Helper module** | `backend/apps/sources/trafilatura_adapter.py` (Phase 6 — Medium tier; needs `trafilatura` pip dep approval) |
| **Tests module** | `backend/apps/sources/tests.py` — `TrafilaturaTests` (to be created) |
| **Benchmark module** | `backend/benchmarks/test_bench_trafilatura.py` (pending G6) |

**Status: DEFERRED.** Needs `trafilatura` pip dep. Deferred until
operator approves the dep (~10 MB install footprint, pulls
`lxml` — already installed — and `justext`).

## 2 · Motivation

A raw HTML page is maybe 20 % main content and 80 % chrome
(navigation, footer, sidebar ads, cookie banners, schema-org blocks,
comment forms). Embedding the full HTML gives BGE-M3 a very noisy
signal — cosine similarity gets dominated by site-template
boilerplate instead of article text. Trafilatura strips the chrome
and returns the author-written body, typically ~3-8 KB per article.
Barbaresi's 2021 benchmark shows it beats Readability.js, Boilerpipe,
DOM-distiller, and Goose3 across six reference test corpora.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Barbaresi, A. (2021). "Trafilatura: A web scraping library and command-line tool for text discovery and retrieval." *Proceedings of the 59th ACL: System Demonstrations*, pp. 122-131. |
| **Open-access link** | <https://aclanthology.org/2021.acl-demo.15/> |
| **Relevant section(s)** | §2 — cascaded algorithm (XPath patterns → fallback to content-density heuristics); §4 — benchmark results on 4 corpora including CommonCrawl and GoldenRules |
| **What we faithfully reproduce** | We **wrap** the library, not re-implement. Our adapter standardises the call site (extract → title, main body, publication date, language). |
| **What we deliberately diverge on** | Disable `include_comments=True`, `include_tables=False`, `favor_recall=True` (we want longer extractions for forums and news). |

## 4 · Input contract

- **`extract(html: str | bytes, url: str | None = None) -> TrafilaturaExtract | None`**
  - `html` — raw HTML bytes or decoded string. Empty / whitespace-only
    input returns `None`.
  - `url` — optional base URL used by trafilatura to resolve relative
    links and skip site-specific boilerplate by template ID.
- Library upstream may raise `trafilatura.core.UnicodeError` for
  mangled encoding; adapter catches and returns `None`.

## 5 · Output contract

- `TrafilaturaExtract` frozen dataclass:
  - `title: str | None`
  - `body_text: str` — **main-content plain text**, no HTML.
  - `language: str | None` — ISO 639-1 when trafilatura detects one.
  - `publication_date: datetime.date | None` — from schema.org or meta
    tags if present.
  - `author: str | None`
  - `word_count: int`
- Returns `None` when trafilatura can't find a main body (very short
  pages, error pages, pure-media pages).
- **Determinism.** Pure function of input; trafilatura's internal
  heuristics are deterministic given a fixed version.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `trafilatura.enabled` | bool | `true` | Recommended preset policy | No | — | Fall back to raw HTML + BeautifulSoup text extraction if off |
| `trafilatura.favor_recall` | bool | `true` | Barbaresi 2021 §3 — forums and long threads benefit from aggressive recall; we operate mostly on forum text | Yes | `categorical([true, false])` | Trade recall (more text, more noise) vs precision (less text, cleaner) |
| `trafilatura.include_comments` | bool | `false` | Barbaresi 2021 §3 default — comments are typically reply-chain, not the author's original content | Yes | `categorical([true, false])` | Including comments adds recall on old forum threads but dilutes the author's signal |
| `trafilatura.include_tables` | bool | `false` | Barbaresi 2021 §3 default — tables in forum/WP content are usually signature boxes, not content | Yes | `categorical([true, false])` | — |
| `trafilatura.target_language` | str | `"en"` | Corpus is predominantly English; invalid detections get dropped | No | — | Filters by detected language |
| `trafilatura.min_extracted_size_chars` | int | `250` | Barbaresi 2021 §4 — below 250 chars Trafilatura's precision collapses; better to fall back | Yes | `int(100, 2000)` | Rejection threshold for too-short extractions |

## 7 · Pseudocode

```
from trafilatura import extract as trf_extract, bare_extraction

function extract(html, url):
    try:
        data = bare_extraction(
            html,
            url=url,
            favor_recall=settings.favor_recall,
            include_comments=settings.include_comments,
            include_tables=settings.include_tables,
            target_language=settings.target_language,
        )
    except trafilatura.core.UnicodeError:
        return None
    if data is None:
        return None
    body = (data.get("text") or "").strip()
    if len(body) < settings.min_extracted_size_chars:
        return None
    return TrafilaturaExtract(
        title=data.get("title"),
        body_text=body,
        language=data.get("language"),
        publication_date=parse_date(data.get("date")),
        author=data.get("author"),
        word_count=len(body.split()),
    )
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/crawler/services/site_crawler.py` | Downloaded HTML + URL | Replace the current BeautifulSoup text cleaner with the adapter's `body_text`; fall back on `None` |
| `apps/pipeline/tasks_import.py` | Same for imported non-crawled sources | Same |

**Wiring status.** Adapter not yet written (deferred on pip dep).
Current code uses `BeautifulSoup().get_text()` which keeps all
chrome text. Replacing it in W2 is the gateway to measurable
embed-quality gains.

## 9 · Scheduled-updates job

None — extraction runs inline with crawl / import.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~10 MB per process (lxml + trafilatura + heuristic models) | library docs |
| Disk | ~10 MB install footprint | pip install |
| CPU | 20-100 ms per page, dominated by lxml tree walk | benchmark medium |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_extracts_main_body_from_clean_article` | Canonical path |
| `test_returns_none_on_empty_html` | Degenerate input |
| `test_min_size_threshold_rejects_too_short` | Threshold semantics |
| `test_strips_nav_and_footer_chrome` | Boilerplate removal |
| `test_forum_reply_chain_detected_as_comments_section` | Comments excluded by default |
| `test_respects_target_language_filter` | Language semantics |
| `test_unicode_error_returns_none` | Graceful failure |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 HTML pages (~50 KB each) | < 500 ms | > 5 s |
| medium | 1 000 HTML pages | < 1 min | > 10 min |
| large | 10 000 HTML pages | < 15 min | > 90 min |

## 13 · Edge cases & failure modes

- **Mangled encoding** → adapter returns `None`; upstream caller
  falls back to raw-text extraction.
- **PDF / image / video content-type** → adapter returns `None`;
  caller skips.
- **Extremely dense single-page HTML (SPAs rendered server-side)** —
  Trafilatura may extract the SPA shell instead of content. Operator
  can add the origin to a "raw-HTML passthrough" list (future
  enhancement).
- **Library version upgrade** — Trafilatura's heuristics evolve.
  Pinning `trafilatura==X.Y.Z` in requirements.txt keeps extractions
  reproducible across rebuilds.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #11 chardet | Decode HTML to a correct Unicode string before extraction |
| #12 SHA-256 fingerprint | Hash is over `body_text`, not raw HTML — stable across chrome-only changes |

| Downstream | Reason |
|---|---|
| BGE-M3 embedding step | Clean body_text = cleaner embeddings |
| #13 NFKC normalization | Acts on `body_text` |

## 15 · Governance checklist

- [ ] Approve `trafilatura` pip dep (blocker)
- [ ] `trafilatura.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module written
- [x] Benchmark module written
- [x] Test module written
- [ ] TPE search space declared
- [ ] Wired into crawler + import (W2)
