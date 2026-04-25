# Pick #09 — Robots.txt Parser (RFC 9309)

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | 9 |
| **Canonical name** | Robots Exclusion Protocol per RFC 9309 |
| **Settings prefix** | `robots_txt` |
| **Pipeline stage** | Crawl |
| **Shipped in commit** | `f8548e4` (PR-D, 2026-04-22) |
| **Helper module** | [backend/apps/sources/robots.py](../../backend/apps/sources/robots.py) |
| **Tests module** | [backend/apps/sources/tests.py](../../backend/apps/sources/tests.py) — `RobotsCheckerTests` |
| **Benchmark module** | [backend/benchmarks/test_bench_robots_txt.py](../../backend/benchmarks/test_bench_robots_txt.py) (pending G6) |

## 2 · Motivation

Every crawl we run must respect the target origin's `robots.txt`.
Fetching paths marked `Disallow:` for our user agent risks (a) legal
consequences in some jurisdictions, (b) being banned by the origin,
(c) reputational harm. RFC 9309 (September 2022) formalised what had
been a 1994-era de-facto standard and specified how to deal with
the ambiguous legacy bits (case-insensitive user-agent matching,
longest-match precedence, the `crawl-delay` directive).

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Koster, M., Illyes, G., Zeller, H. & Sassman, L. (eds.). (September 2022). RFC 9309: "Robots Exclusion Protocol." IETF. |
| **Open-access link** | <https://datatracker.ietf.org/doc/html/rfc9309> |
| **Relevant section(s)** | §2.2 user-agent matching; §2.2.3 longest-match rule; §2.5 `crawl-delay`; §2.6 sitemap hints; §2.7 size limit (500 KiB); §3 caching (24 h default TTL) |
| **What we faithfully reproduce** | Python stdlib's `urllib.robotparser.RobotFileParser` handles §2.1–§2.4 correctly. Wrapper adds: per-origin caching with §3 TTL, fail-open on 404/5xx (consistent with §3.1), and a clear user-agent string. |
| **What we deliberately diverge on** | We fall **open** on unreachable robots.txt (404, timeout, 5xx), matching §3.1's "if the robots.txt is unreachable the server MAY assume no restrictions." Operators who want fail-closed can flip a setting. |

## 4 · Input contract

- **`RobotsChecker(user_agent: str, timeout_seconds: float = 5.0)`**
  — constructor.
- **`is_allowed(url: str) -> bool`** — looks up the URL's origin,
  fetches + caches robots.txt if not already cached, returns the
  allow/deny verdict for `user_agent`.
- **`crawl_delay(origin: str) -> float | None`** — returns the
  crawl-delay directive value (seconds) if present.
- **`sitemap_urls(origin: str) -> list[str]`** — returns the
  `Sitemap:` declarations from robots.txt.

## 5 · Output contract

- `is_allowed` → `bool`. `True` allows the fetch; `False` blocks it.
- Per-origin robots.txt cached in-process for `cache_ttl_seconds`
  (default 24 h per RFC 9309 §3). Re-fetched after TTL expiry.
- **Empty-input.** `is_allowed("")` → `ValueError`.
- **Determinism.** Deterministic per cached robots.txt content;
  refreshes over time.

## 6 · Hyperparameters

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `robots_txt.enabled` | bool | `true` | Recommended preset policy; disabling violates RFC 9309 | No | — | Master toggle; turning off skips robots.txt entirely |
| `robots_txt.user_agent` | str | `"XFInternalLinker/2.0 (+https://github.com/thulaen/xf-internal-linker-v2)"` | RFC 9309 §2.2.1 — include an identifying token and a contact URL | No | — | Identifies the crawler to origins; must remain stable |
| `robots_txt.fetch_timeout_seconds` | float | `5.0` | Google's crawler documentation recommends 5–10 s; short enough to avoid blocking the crawl on slow hosts | Yes | `uniform(2.0, 30.0)` | Trades latency vs patience for slow origins |
| `robots_txt.cache_ttl_seconds` | int | `86400` | RFC 9309 §3 — "24 hours is the default" | No | — | Correctness — lowering re-fetches unnecessarily, raising risks stale policy |
| `robots_txt.fail_open` | bool | `true` | RFC 9309 §3.1 — "the server MAY assume no restrictions" when robots.txt is unreachable | No | — | Flipping to false blocks crawl on any transient 5xx from robots.txt |

## 7 · Pseudocode

```
from urllib.robotparser import RobotFileParser

cache: dict[origin, (RobotFileParser, fetched_at)]

function is_allowed(url):
    origin = urlsplit(url).scheme + "://" + urlsplit(url).netloc
    parser, fetched_at = cache.get(origin, (None, None))
    if parser is None or (now() - fetched_at) > cache_ttl_seconds:
        parser = fetch_and_parse(origin)
        cache[origin] = (parser, now())
    if parser is fail_open_sentinel:
        return True
    return parser.can_fetch(user_agent, url)

function fetch_and_parse(origin):
    try:
        resp = httpx.get(origin + "/robots.txt", timeout=fetch_timeout)
        if 200 <= resp.status_code < 300:
            parser = RobotFileParser()
            parser.parse(resp.text.splitlines())
            return parser
        if resp.status_code in {404, 410}:
            return fail_open_sentinel          # RFC 9309 §3.1
    except (TimeoutError, NetworkError):
        return fail_open_sentinel if settings.fail_open else fail_closed_sentinel
    return fail_open_sentinel                   # 5xx with fail_open
```

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `apps/crawler/services/site_crawler.py` | Candidate URL before fetch | Skip the URL on `False`; honour `crawl_delay` as an additional sleep |
| `apps/pipeline/tasks_import.py` | Seed URLs from sitemaps | Enumerate `sitemap_urls()` to populate the frontier |

**Wiring status.** Helper exists (PR-D). Not yet called from the
crawler. W2.

## 9 · Scheduled-updates job

None — robots.txt checks are per-request. The in-process cache
self-refreshes on TTL expiry.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM | ~10 KB per cached origin (parser + rules) | — |
| Disk | 0 | in-memory cache |
| CPU | < 100 µs per `is_allowed` cache hit | benchmark small |
| Network | 1 GET + one parse per origin per 24 h | — |

## 11 · Tests

| Test name | Invariant verified |
|---|---|
| `test_allow_default_when_robots_missing` | §3.1 fail-open |
| `test_deny_when_disallow_matches` | Core allow/deny |
| `test_longest_match_wins` | §2.2.3 precedence |
| `test_user_agent_case_insensitive` | §2.2 |
| `test_crawl_delay_extracted` | §2.5 |
| `test_sitemap_urls_extracted` | §2.6 |
| `test_cache_reused_within_ttl` | Cache hit |
| `test_cache_refreshed_after_ttl` | Cache expiry |
| `test_timeout_respects_fail_open_setting` | Fail-open flag |

## 12 · Benchmark inputs

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | 10 URLs × 3 cached origins | < 5 ms | > 50 ms |
| medium | 10 000 URLs × 50 cached origins | < 200 ms | > 2 s |
| large | 1 000 000 URLs × 500 cached origins | < 30 s | > 5 min |

## 13 · Edge cases & failure modes

- **Malformed robots.txt** — stdlib `RobotFileParser.parse` is
  lenient; parse errors typically result in an empty ruleset (=
  allow everything).
- **Redirect loops on robots.txt fetch** — httpx default 30 redirect
  limit + timeout; treated as unreachable.
- **Origin serves HTML robots.txt (misconfig)** — RFC 9309 §3 says
  "MUST be text/plain"; lenient parser still often tolerates it.
  Operator can flip `fail_open=false` for known-problematic origins.
- **Very large robots.txt** — RFC 9309 §2.7 caps at 500 KiB; we
  accept up to 1 MiB before bailing to fail-open.

## 14 · Paired picks

| Upstream | Reason |
|---|---|
| — | Standalone |

| Downstream | Reason |
|---|---|
| #10 Freshness scheduler | Honour `crawl_delay` by widening scheduled interval |
| #2 Exponential Backoff | 5xx on robots.txt fetch retried with backoff before falling open |

## 15 · Governance checklist

- [ ] `robots_txt.enabled` seeded
- [ ] Hyperparameters seeded
- [ ] Migration upserts rows
- [x] `FEATURE-REQUESTS.md` entry
- [x] `AI-CONTEXT.md` ledger
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row
- [ ] `docs/PERFORMANCE.md` entry
- [x] Helper module (PR-D)
- [ ] Benchmark module
- [x] Test module (PR-D)
- [ ] Crawler wired (W2)
