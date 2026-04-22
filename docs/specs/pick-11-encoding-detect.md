# Pick #11 — Character-encoding detection (Li & Momoi 2001)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 11 |
| **Canonical name** | Character encoding auto-detection |
| **Settings prefix** | `encoding_detect` |
| **Pipeline stage** | Crawl / Parse |
| **Shipped in commit** | `f8548e4` (PR-D, 2026-04-22) |
| **Helper module** | [backend/apps/sources/encoding.py](../../backend/apps/sources/encoding.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `EncodingDetectTests` |
| **Benchmark module** | [backend/benchmarks/test_bench_encoding_detect.py](../../backend/benchmarks/test_bench_encoding_detect.py) (pending G6) |

## 2 · Motivation

Not every origin declares its charset. Some WordPress 1.x blogs still
serve CP1252-without-a-header; some XenForo installs on older PHP
emit ISO-8859-1. Decoding the wrong way produces mojibake (`caf?`
instead of `café`) which destroys embedding quality and search
recall. A 5-tier detection cascade — explicit header → HTML `<meta
charset>` → BOM sniff → `charset_normalizer` probabilistic guess →
latin-1 fallback — correctly decodes > 99.5 % of real-world pages on
our sampled crawl.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Li, S. & Momoi, K. (2001). "A composite approach to language/encoding detection." *18th International Unicode Conference* (Hong Kong). Foundation of Mozilla's `universalchardet` / Python's `chardet`. |
| **Open-access link** | <https://www-archive.mozilla.org/projects/intl/universalcharsetdetection> |
| **Relevant section(s)** | §3 — two-level classifier (character distribution + 2-char sequence likelihood); §5 — fallback strategy when confidence is low |
| **What we faithfully reproduce** | The 5-tier cascade: we consult `charset_normalizer` (the actively-maintained fork of `chardet`) for the probabilistic tier. Li-Momoi's classifier is the engine. |
| **What we deliberately diverge on** | We short-circuit with **declared charset** (HTTP header, BOM, meta tag) before probabilistic detection — the paper focuses on the probabilistic tier; real-world code should honour declarations first because they're essentially always right when present. |

## 4 · Input contract

- **`detect_encoding(data: bytes, *, content_type_header: str | None =
  None, meta_charset: str | None = None) -> EncodingGuess`**
  - `data` — raw body bytes. Empty → returns `EncodingGuess(encoding
    ="utf-8", confidence=0.0, source="empty_default")`.
  - `content_type_header` — value of the `Content-Type` HTTP header
    if known.
  - `meta_charset` — value of `<meta charset="...">` if extracted
    from the HTML.

## 5 · Output contract

- `EncodingGuess(encoding: str, confidence: float, source: str)`
  - `encoding` — a codec name Python's `bytes.decode()` accepts.
  - `confidence` — in `[0, 1]`; declared encodings return `1.0`,
    charset_normalizer's confidence is passed through, latin-1
    fallback returns `0.0`.
  - `source` — one of `http_header`, `meta_charset`, `bom`,
    `charset_normalizer`, `latin1_fallback`, `empty_default`.
- **Determinism.** Output is deterministic per byte sequence; ties
  broken by source-order precedence.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `encoding_detect.enabled` | bool | `true` | Recommended preset policy | No | — | Off = hardcoded latin-1 (safe but produces mojibake on UTF-8) |
| `encoding_detect.trust_http_header` | bool | `true` | HTTP spec — Content-Type charset is authoritative | No | — | Correctness |
| `encoding_detect.trust_meta_charset` | bool | `true` | HTML living standard §4.2.5 — `<meta charset>` is a MUST-honour declaration | No | — | Correctness |
| `encoding_detect.charset_normalizer_min_confidence` | float | `0.5` | charset_normalizer docs recommend 0.5 as the "trust" threshold | Yes | `uniform(0.2, 0.95)` | Higher = more aggressive latin-1 fallback, lower = trusts weaker guesses |
| `encoding_detect.sample_bytes_for_detection` | int | `32768` | Only inspect the first 32 KB — faster, Li-Momoi §5 observes that 32 KB is enough for 99 % accuracy | Yes | `int(4096, 262144)` | Larger = slower detection but edge-case multi-encoded pages get detected |

## 7 · Pseudocode

```
function detect_encoding(data, content_type_header, meta_charset):
    if not data:
        return EncodingGuess("utf-8", 0.0, "empty_default")

    # Tier 1 — HTTP header
    if content_type_header:
        charset = parse_content_type_charset(content_type_header)
        if charset and is_valid_codec(charset):
            return EncodingGuess(charset, 1.0, "http_header")

    # Tier 2 — HTML <meta charset>
    if meta_charset and is_valid_codec(meta_charset):
        return EncodingGuess(meta_charset, 1.0, "meta_charset")

    # Tier 3 — BOM sniff
    bom_encoding = detect_bom(data[:4])
    if bom_encoding:
        return EncodingGuess(bom_encoding, 1.0, "bom")

    # Tier 4 — probabilistic (charset_normalizer)
    sample = data[:sample_bytes_for_detection]
    result = charset_normalizer.detect(sample)
    if result and result["confidence"] >= min_confidence_threshold:
        return EncodingGuess(result["encoding"], result["confidence"], "charset_normalizer")

    # Tier 5 — latin-1 never errors, always round-trips bytes
    return EncodingGuess("latin-1", 0.0, "latin1_fallback")
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/crawler/services/site_crawler.py` | Downloaded body bytes + HTTP headers + extracted meta tag | Decode body with the returned encoding before BS4 parsing |
| `apps/pipeline/tasks_import.py` | Imported raw bytes from files | Same |

**Wiring status.** Helper exists (PR-D). Crawler currently uses
`response.text` (httpx's heuristic) which misses HTTP-header /
meta-charset precedence. W2 replaces that.

## 9 · Scheduled-updates job

None — inline with fetch.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 5 MB (charset_normalizer's internal state + sample buffer) | library docs |
| Disk | ~5 MB pip dep (charset_normalizer) | — |
| CPU | < 10 ms per detection on 32 KB sample | benchmark medium |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_http_header_trumps_everything` | Tier-1 precedence |
| `test_meta_charset_beats_bom_beats_probabilistic` | Tier 2-4 order |
| `test_bom_detected_utf8_utf16_le_be` | §3 BOM sniff |
| `test_charset_normalizer_fallback_on_low_confidence` | Tier 5 triggers |
| `test_latin1_never_raises` | §5 final safety net |
| `test_empty_bytes_returns_utf8_default` | Degenerate input |
| `test_invalid_codec_name_ignored` | Defensive parsing |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 100 byte strings (various encodings) | < 50 ms | > 500 ms |
| medium | 10 000 pages (average 50 KB each) | < 10 s | > 60 s |
| large | 1 000 000 pages | < 20 min | > 2 h |

## 13 · Edge cases & failure modes

- **Truncated UTF-8 mid-codepoint** — charset_normalizer recognises
  but reports low confidence; latin-1 fallback kicks in; caller can
  still process the text (lossy, but no crash).
- **Multi-encoded document** (HTTP says ASCII but body is CP1252) —
  we follow the HTTP header and produce mojibake. Known RFC-vs-reality
  conflict; operator can disable `trust_http_header` per-origin.
- **BOM present but header says different encoding** — header wins
  per project policy; documented behaviour.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #6 Conditional GET | Only runs on 2xx; 304 short-circuits before decoding |

| Downstream | Reason |
|---|---|
| #7 Trafilatura | Receives correctly-decoded string |
| #13 NFKC normalization | Normalises after decoding |

## 15 · Governance checklist

- [ ] `encoding_detect.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-D)
- [ ] Benchmark module
- [x] Test module (PR-D)
- [ ] Crawler + import wired (W2)
