# Pick #08 — URL Canonicalization (RFC 3986)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 8 |
| **Canonical name** | URL Canonicalization per RFC 3986 §6 |
| **Settings prefix** | `url_canonical` |
| **Pipeline stage** | Crawl |
| **Shipped in commit** | **not yet merged** — existing `canonical_url` in `site_crawler.py` only reads the `<link rel="canonical">` tag, does not normalise arbitrary URLs |
| **Helper module** | `backend/apps/sources/url_canonical.py` (to be created) |
| **Tests module** | `backend/apps/sources/tests.py` — `UrlCanonicalTests` (to be created) |
| **Benchmark module** | `backend/benchmarks/test_bench_url_canonical.py` (pending G6) |

**Status: TO-SHIP.** Implementation needed. Plan lists
`url-normalize` PyPI as reference; we ship a stdlib-only
implementation because the handful of rules we need can be written
in ~100 SLOC without adding a dep.

## 2 · Motivation

The same logical page can appear under hundreds of URL spellings:

- `http://example.com/foo`
- `http://example.com:80/foo`
- `http://Example.COM/foo/`
- `http://example.com/foo/#fragment`
- `http://example.com/foo/?utm_source=twitter&ref=home`
- `http://example.com/foo//bar` (double slash)

Without canonicalization the crawler ingests all of those as separate
pages, wasting bandwidth, GPU embed time, and polluting the graph
with spurious edges. RFC 3986 §6 defines the normalisation rules —
lowercase scheme & host, collapse dot segments, strip default ports,
drop fragments, sort query parameters, and remove tracking params
(the project-specific addition).

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Berners-Lee, T., Fielding, R. & Masinter, L. (January 2005). RFC 3986: "Uniform Resource Identifier (URI): Generic Syntax." IETF. |
| **Open-access link** | <https://datatracker.ietf.org/doc/html/rfc3986> |
| **Relevant section(s)** | §6 "Normalization and Comparison". §6.2.2.1 Case Normalization; §6.2.2.2 Percent-Encoding Normalization; §6.2.2.3 Path Segment Normalization; §6.2.3 Scheme-Based Normalization |
| **What we faithfully reproduce** | All §6.2.2.x rules plus §6.2.3 default-port stripping for http/https/ftp. |
| **What we deliberately diverge on** | §6.2.4 "Protocol-Based Normalization" (e.g. `index.html` collapsing to `/`) is site-specific; we skip it by default and let operators add per-origin rules if needed. We also strip tracking query params — not in RFC 3986 but a project-specific dedup concern. |

## 4 · Input contract

- **`canonicalize(url: str, *, drop_fragment: bool = True,
  strip_tracking_params: bool = True, sort_query_params: bool = True)
  -> str`**
  - Input must parse as a valid URL; raises `ValueError` on
    unparseable input (returning the raw string would hide bugs).
  - Relative URLs are rejected — the caller must resolve them first.
  - IDN hostnames (`münchen.de`) are idna-encoded before being
    lowercased.

## 5 · Output contract

- Returns a `str`. Same type as input, always.
- **Invariants.**
  - Idempotent: `canonicalize(canonicalize(u)) == canonicalize(u)`.
  - Case-insensitive equality: `canonicalize("HTTP://X.COM") ==
    canonicalize("http://x.com")`.
  - Default port stripped: `canonicalize("http://x.com:80/") ==
    canonicalize("http://x.com/")`.
  - Fragment stripped when `drop_fragment=True`.
  - Tracking params stripped when `strip_tracking_params=True` —
    see §6 for the list.
- **Determinism.** Pure function.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `url_canonical.enabled` | bool | `true` | Recommended preset policy | No | — | Master toggle |
| `url_canonical.drop_fragment` | bool | `true` | RFC 3986 §3.5 — fragments are client-side; two URLs differing only in fragment target the same resource | No | — | Correctness (dedup) |
| `url_canonical.strip_tracking_params` | bool | `true` | Project-specific — UTM / ref / fbclid carry no content signal | No | — | Correctness (dedup) |
| `url_canonical.sort_query_params` | bool | `true` | RFC 3986 §6.2.2 encourages consistent ordering; alphabetical is the stable choice | No | — | Correctness |
| `url_canonical.tracking_param_prefixes` | str (comma-sep) | `"utm_,fbclid,gclid,mc_cid,mc_eid,_ga,ref,referrer,source"` | Google Analytics docs, Facebook Pixel docs, Mailchimp docs | No | — | Master list of strippable query keys |
| `url_canonical.path_case_sensitive` | bool | `true` | RFC 3986 §6.2.2.1 — scheme/host are case-insensitive; path **is** case-sensitive (for many origins) | No | — | Lowercasing path would create false duplicates on case-sensitive origins |

All params fixed — correctness/compliance, not optimisation.

## 7 · Pseudocode

```
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote

TRACKING_PREFIXES = settings.tracking_param_prefixes.split(",")

function canonicalize(url, drop_fragment, strip_tracking, sort_qs):
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"URL must be absolute: {url!r}")

    # Scheme + host — §6.2.2.1
    scheme = parts.scheme.lower()
    host = parts.hostname.lower()                                  # idna already applied by stdlib
    port = parts.port
    if port in (default_port_for(scheme),):
        port = None

    # Path — §6.2.2.3 normalise dot-segments, collapse double slashes
    path = normalise_path_segments(parts.path) or "/"
    if not settings.path_case_sensitive:
        path = path.lower()
    path = quote(unquote(path), safe="/:@%+,;=")                   # §6.2.2.2 pct-encoding

    # Query — parse, filter, sort, re-encode
    qs = parse_qsl(parts.query, keep_blank_values=True)
    if strip_tracking:
        qs = [(k, v) for k, v in qs if not any(k.startswith(p) for p in TRACKING_PREFIXES)]
    if sort_qs:
        qs.sort()
    query = urlencode(qs, doseq=True)

    # Fragment — §3.5 drop per flag
    fragment = "" if drop_fragment else parts.fragment

    authority = host + (f":{port}" if port else "")
    return urlunsplit((scheme, authority, path, query, fragment))
```

`normalise_path_segments` implements RFC 3986 §5.2.4 "Remove Dot
Segments" — stdlib has no direct helper so we inline the 15-line
loop.

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/crawler/services/site_crawler.py` | Every discovered URL | Stored canonical form is the DB key |
| `apps/pipeline/tasks_import.py` | Imported URLs from sitemaps / CSV | Same |
| `apps/sync/services/*` | Post permalinks | Stored canonical form |

**Wiring status.** Not yet imported. W2 replaces ad-hoc lowercasing
in the crawler with this helper.

## 9 · Scheduled-updates job

None — inline per URL discovered.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | < 1 KB per call | — |
| Disk | 0 | — |
| CPU | < 30 µs per URL | benchmark small |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_lowercase_scheme_and_host` | §6.2.2.1 |
| `test_strip_default_ports` | §6.2.3 |
| `test_collapse_dot_segments` | §5.2.4 |
| `test_drop_fragment_when_enabled` | Flag semantics |
| `test_preserve_fragment_when_disabled` | Flag semantics |
| `test_sort_query_params` | Determinism |
| `test_strip_utm_and_fbclid` | Tracking dedup |
| `test_percent_encoding_normalised` | §6.2.2.2 |
| `test_idempotent_under_double_call` | Invariant |
| `test_relative_url_rejected` | Input validation |
| `test_idn_host_lowercased_correctly` | §6.2.2.1 + idna |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 1 000 URLs | < 30 ms | > 300 ms |
| medium | 100 000 URLs | < 3 s | > 30 s |
| large | 10 000 000 URLs | < 5 min | > 30 min |

## 13 · Edge cases & failure modes

- **URLs with embedded user:password** — stdlib handles this; we
  lowercase the host but preserve userinfo (per RFC).
- **Mixed-case path on macOS/Windows vs Linux-hosted origin** —
  `path_case_sensitive=true` default means we don't fold case;
  documented risk when operator has case-insensitive file systems
  for their origin.
- **Unicode in path** (`/café/`) — kept pct-encoded after round-trip;
  stable across callers.
- **Query value contains tracking prefix as a value, not a key** —
  only keys are stripped; values preserved.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| — | Standalone |

| Downstream | Reason |
|---|---|
| #4 Bloom Filter | Canonical URL is the dedup key |
| #12 SHA-256 fingerprint | Hash stable only if canonical URL is the dedup key upstream |

## 15 · Governance checklist

- [ ] `url_canonical.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [ ] `FEATURE-REQUESTS.md` entry
- [ ] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [ ] Helper module written
- [ ] Benchmark module written
- [ ] Test module written
- [ ] Crawler + syncer + import wired (W2)
