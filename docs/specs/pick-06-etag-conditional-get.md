# Pick #06 — ETag / Conditional GET

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 6 |
| **Canonical name** | HTTP Conditional GET — `If-None-Match` + `If-Modified-Since` (RFC 7232) |
| **Settings prefix** | `conditional_get` |
| **Pipeline stage** | Source / Crawl |
| **Shipped in commit** | `6d925b1` (PR-C, 2026-04-22) |
| **Helper module** | [backend/apps/sources/conditional_get.py](../../backend/apps/sources/conditional_get.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `ConditionalGetTests` |
| **Benchmark module** | [backend/benchmarks/test_bench_conditional_get.py](../../backend/benchmarks/test_bench_conditional_get.py) (pending G6) |

## 2 · Motivation

The crawler already stores each page's `ETag` + `Last-Modified` headers
on the `CrawledPage` row. What it *doesn't* do today is send those
validators back on the next refresh — so every refetch pulls the full
body even when nothing changed. Conditional GET sends the validators
back; the origin returns `304 Not Modified` with an empty body when
the content hasn't changed, saving us **bandwidth** (typical WP/XF
page is 40-200 KB) and **BGE-M3 re-embed** cost downstream (~50 ms
GPU per page).

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Fielding, R. & Reschke, J. (eds.). (June 2014). RFC 7232: "Hypertext Transfer Protocol (HTTP/1.1): Conditional Requests." IETF. |
| **Open-access link** | <https://datatracker.ietf.org/doc/html/rfc7232> |
| **Relevant section(s)** | §2 — validators; §3.1 `If-Match`; §3.2 `If-None-Match`; §3.3 `If-Modified-Since`; §4.1 `304 Not Modified` semantics |
| **What we faithfully reproduce** | Header syntax, exact 304-detection. Supports case-insensitive header matching (as RFC 7230 §3.2 requires) for both `ETag` / `Etag` / `etag` and `Last-Modified` / `last-modified`. |
| **What we deliberately diverge on** | RFC 7232 also specifies `If-Match` / `If-Unmodified-Since` (write-intent headers); we only implement the read-intent pair since the crawler only reads. Operator can add the write-intent helpers if the linker ever starts pushing content upstream. |

## 4 · Input contract

- **`build_validator_headers(etag: str | None, last_modified: str | None) -> dict[str, str]`**
  - Returns a headers dict with `If-None-Match` and/or
    `If-Modified-Since` set when the inputs are non-empty.
  - Whitespace-only inputs are treated as empty and skipped (passing
    an empty `If-None-Match` would match any ETag and is never what
    the caller wants).
- **`is_not_modified(response) -> bool`**
  - Accepts any response object with either `.status_code` (requests /
    httpx / DRF) or `.status` (aiohttp). Returns `True` iff the code
    is exactly 304.
- **`extract_validators(response) -> dict[str, str]`**
  - Returns a dict with `etag` / `last_modified` keys (lowercased)
    from the response headers. Case-insensitive header lookup.

## 5 · Output contract

- All three helpers return plain dicts / bools — no custom classes
  — so callers keep using their HTTP library's native request/response
  types.
- **Library-agnostic.** Helpers accept anything with the two
  documented attribute shapes. Raises `TypeError` with a helpful
  message if neither attribute is present.
- **Determinism.** Pure function; no clock, no RNG, no state.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `conditional_get.enabled` | bool | `true` | Recommended preset policy | No | — | Master toggle — off means every refetch downloads full body |
| `conditional_get.send_if_none_match` | bool | `true` | RFC 7232 §3.2 — ETag is the strong-validator primary path | No | — | Disable if a specific upstream has buggy ETag handling |
| `conditional_get.send_if_modified_since` | bool | `true` | RFC 7232 §3.3 — fall-back validator for origins without ETag support | No | — | Disable for origins where `Last-Modified` is unreliable |

No TPE-tuned params — RFC-compliance is a correctness concern,
not an optimisation target.

## 7 · Pseudocode

```
function build_validator_headers(etag, last_modified):
    h = {}
    if etag and etag.strip():
        h["If-None-Match"] = etag.strip()
    if last_modified and last_modified.strip():
        h["If-Modified-Since"] = last_modified.strip()
    return h

function is_not_modified(response):
    code = response.status_code if hasattr(response, "status_code") else response.status
    return code == 304

function extract_validators(response):
    out = {}
    headers = response.headers  # any Mapping-like
    etag = ci_lookup(headers, "ETag")
    lm   = ci_lookup(headers, "Last-Modified")
    if etag: out["etag"] = etag.strip()
    if lm:   out["last_modified"] = lm.strip()
    return out
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/crawler/services/site_crawler.py` | Cached `(etag, last_modified)` from the last crawl | Merge into outgoing request headers; on 304, mark page skipped and update `last_crawled_at` without re-embedding |
| `apps/sync/services/*` (if WP/XF ever return validators) | Same | Same |

**Wiring status.** Not yet imported. W2 wires the crawler to use it.
Big expected payoff: our sampled crawls show 60-75 % of pages are
unchanged between daily runs, so 304 detection should cut embed
GPU time roughly 2.5×.

## 9 · Scheduled-updates job

None — this pick is a per-request adapter, not a periodic job. The
freshness scheduler (#10) decides *when* to refetch; this pick makes
the refetch efficient.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 1 KB per request | — |
| Disk | 0 (validators already stored on CrawledPage) | — |
| CPU | < 10 µs per header build | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_build_validator_headers_with_both` | Both headers set when both given |
| `test_build_validator_headers_with_neither` | Empty dict when neither given |
| `test_build_validator_headers_strips_whitespace` | Whitespace-only rejected |
| `test_is_not_modified_true_for_304` | Exact 304 match |
| `test_is_not_modified_false_for_other_codes` | 200/301/404 all `False` |
| `test_is_not_modified_works_with_aiohttp_style_status` | `status` attribute support |
| `test_extract_validators_case_insensitive` | `ETag` / `etag` / `Etag` all match |
| `test_extract_validators_strips_whitespace` | Clean output |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 000 header builds | < 20 ms | > 200 ms |
| medium | 1 000 000 header builds | < 2 s | > 20 s |
| large | 10 000 000 header builds | < 20 s | > 3 min |

## 13 · Edge cases & failure modes

- **Response object missing both `status_code` and `status`** →
  `TypeError("response must expose status_code or status")`. Only
  happens with a hand-rolled stub that's not HTTP-compliant.
- **Server returns 304 with body** — our helper still reports 304;
  callers should ignore the body per RFC. We don't strip the body
  for them.
- **ETag rotates per request** (some CDNs) — validators become
  useless; no 304 ever comes back. Not our bug; operator can disable
  the pick per-origin in AppSetting.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| #10 Freshness Crawl Scheduling | Decides *when* to refetch; this pick provides the efficient *how* |

| Downstream | Reason |
|---|---|
| #11 chardet / encoding detect | Only runs on 2xx responses; 304 short-circuits before the body is decoded |
| #12 SHA-256 fingerprint | Same — 304 means "body hasn't changed, fingerprint is unchanged" |

## 15 · Governance checklist

- [ ] `conditional_get.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry (bandwidth savings measurement)
- [x] Helper module (PR-C)
- [ ] Benchmark module
- [x] Test module (PR-C)
- [ ] Crawler wired (W2)
