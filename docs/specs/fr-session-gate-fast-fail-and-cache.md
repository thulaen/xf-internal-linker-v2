# Session-Gate Fast-Fail Connect Timeout + Startupd TTL Cache

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]
[SPEC CITED: feature=session-gate-fast-fail kind=technical_doc id=https://grpc.io/docs/guides/wait-for-ready/ verified_at=2026-06-02]
[SPEC CITED: feature=session-gate-fast-fail kind=technical_doc id=https://grpc.github.io/grpc/core/md_doc_connectivity-semantics-and-api.html verified_at=2026-06-02]
[SPEC CITED: feature=session-gate-ttl-cache kind=technical_doc id=https://www.rfc-editor.org/rfc/rfc9111 verified_at=2026-06-02]
[SPEC CITED: feature=session-gate-hmac-token kind=technical_doc id=https://www.rfc-editor.org/rfc/rfc2104 verified_at=2026-06-02]

## Goal

Make the session-start gate ritual finish fast in the two cases that dominate
its wall-clock time:

1. **snapshotd is OFF.** The snapshot health probe used to wait the full default
   connect timeout of 5.0 seconds before giving up. That single wait was the
   slowest step of the whole ritual.
2. **The same ritual runs twice.** Each run made a fresh trip to the Django
   backend for the six database-backed markers, even when the answer was
   seconds old and unchanged.

Both fixes are pure speed changes. They do not change what the gate returns when
everything is healthy, and they do not weaken the security token that proves the
marker block came from startupd.

## Plain-English summary

- "Connect timeout" means how long a client waits to open a network connection
  before it declares the other side unreachable.
- "Health probe" means a quick are-you-alive check, not a real data request.
- "TTL cache" means a small in-memory store of recent answers, where each answer
  is thrown away after a fixed number of seconds (TTL = time to live).
- "HMAC token" means a short signature that proves a message was produced by
  something that knows a shared secret, so a hook can trust the marker block.

## Measured before and after

| Scenario | Before | After |
|---|---|---|
| Session-start ritual, snapshotd OFF | ~5.7 s (dominated by the 5.0 s connect wait) | ~0.65 s |
| Repeat ritual, same session type + areas, within the cache window | full Django round-trip every time | ~0.18 s on a cache hit |

The numbers above are measured wall-clock times for the ritual, not micro-bench
loops. The 5.0 s figure is the shared default connect timeout
(`DEFAULT_CONNECT_TIMEOUT` in `backend/apps/_sidecars_shared/channel.py`, sourced
from `XF_SIDECARS_CONNECT_TIMEOUT`, default `"5.0"`).

## Sources of truth

| Area | Source | Design decision |
|---|---|---|
| Fast-fail connect behaviour | gRPC "Wait-for-Ready" guide (grpc.io) | A call that is not wait-for-ready fails as soon as the channel cannot connect within the deadline, instead of queuing until the channel is ready. A liveness probe wants this fast-fail behaviour, so the health probe opens its channel with a short connect timeout. |
| Channel connectivity states | gRPC connectivity semantics and API (grpc.github.io) | A channel moves through IDLE → CONNECTING → READY / TRANSIENT_FAILURE. When snapshotd is down the channel sits in CONNECTING / TRANSIENT_FAILURE until the connect timeout elapses; shortening that timeout for the probe bounds the worst-case wait to ~0.3 s. |
| Response caching with a freshness lifetime | RFC 9111 (HTTP Caching) §4.2 (freshness) | A cached response may be reused while it is still fresh; a bounded freshness lifetime (here a 45 s TTL) is the standard way to reuse a recent answer without serving a stale one indefinitely. The startupd cache reuses the Django markers within the window and re-fetches once the entry expires. |
| Token signing | RFC 2104 (HMAC: Keyed-Hashing for Message Authentication) | The gate token is HMAC-SHA256 over `sessionType\|unixMinute\|totalOpenCount`, truncated to 16 hex chars. RFC 2104 defines the keyed-hash construction; the token is re-signed on every request from the current minute, so a cache hit never reuses a stale token. |

## Fix 1 — fast-fail snapshot health probe

### What changed

`SnapshotdClient.health()` in
`backend/apps/auto_issues/_sidecars/snapshotd_client.py` opens its gRPC channel
with an explicit short connect timeout:

```python
HEALTH_CONNECT_TIMEOUT_SECONDS = 0.3
...
def health(self) -> str:
    pb, grpc_mod = load_service_stubs(SERVICE_NAME)
    with sidecars_channel(connect_timeout=HEALTH_CONNECT_TIMEOUT_SECONDS) as channel:
        stub = grpc_mod.SnapshotdStub(channel)
        response = stub.Health(pb.Empty(), timeout=self._deadline)
    return pb.HealthStatus.Name(response.status)
```

The shared `sidecars_channel()` already accepts a `connect_timeout` override
(`backend/apps/_sidecars_shared/channel.py`); when it is `None` the call falls
back to the 5.0 s default. Only the health probe passes the short value.

### Why only the health probe

- A health probe is the first thing the session-start ritual does, and it is the
  one call that runs while snapshotd might still be OFF. Failing fast there is
  what reclaims the ~5 s.
- The data RPCs (`create_snapshot`, `get_snapshot`, `list_by_issue`, `pin`,
  `unpin`) keep the normal connect timeout, because by the time they run
  snapshotd is already reachable. Shortening their connect timeout would only add
  flakiness on a cold start with no speed benefit.

### Scaling and limits

- The probe runs once per ritual. There is no loop and no unbounded growth.
- Worst case when snapshotd is OFF: ~0.3 s connect wait, then a clear
  NOT_SERVING / unreachable result.
- The 0.3 s value is deliberately above local socket round-trip time (sub-
  millisecond on the same host) so a momentarily-busy-but-alive snapshotd is not
  misreported as down.

## Fix 2 — startupd TTL cache of the Django session-gate response

### What changed

The gate handler in `services/startupd/internal/gate/handler.go` keeps a small
in-memory TTL cache of the Django session-gate response, keyed by session type
plus the requested areas:

```go
const djangoCacheTTL = 45 * time.Second
...
key := cacheKey(sessionType, areas)
dr, hit := cache.get(key, now)
if !hit {
    fetched, err := proxyDjango(cfg.HTTPClient, cfg.DjangoURL, sessionType, areas)
    ...
    dr = fetched
    cache.put(key, dr, now)
}
tsMins := now.Unix() / 60
token := computeToken(cfg.Secret, sessionType, tsMins, dr.TotalOpenCount)
```

- **Key.** `cacheKey(sessionType, areas)` sorts the areas first, so `[a,b]` and
  `[b,a]` share one entry. Session type and areas are the only inputs that change
  the Django markers, so they are the whole key.
- **TTL.** Entries expire after 45 s. A repeat ritual inside that window reuses
  the cached markers and skips the Django round-trip entirely. After the window,
  the next request re-fetches and stores a new entry.
- **Token is always fresh.** The HMAC token is re-signed on every request from
  the current minute (`now.Unix() / 60`) and the cached `TotalOpenCount`. A cache
  hit never returns a stale token, so hooks that verify the token keep working.
- **Concurrency.** The cache is guarded by a `sync.Mutex`, so concurrent gate
  requests are safe.

### Why 45 seconds

- The session-gate counts (open AutoIssues, paper-trail entries) change on the
  order of minutes during a session, not sub-second. A 45 s freshness window is
  short enough that a reused answer is still accurate and long enough to absorb
  the repeated rituals an agent fires back-to-back at session start.
- This follows the RFC 9111 freshness model: reuse a stored response only while
  it is fresh, then revalidate by re-fetching.

### Scaling and limits

- The cache holds at most one entry per `(session type, sorted areas)`
  combination. The session-type set is fixed (`docs`, `infrastructure`,
  `reconciliation`, `feature`) and the area set is bounded by the repo path list,
  so the map cannot grow without bound during a session.
- Expired entries are simply ignored on read and overwritten on the next miss; no
  background sweeper is needed at this scale. If the map ever needs eviction at a
  much larger scale, the next change adds a size cap with LRU eviction — the
  insertion point is `djangoCache.put`.

## Behaviour (BDD)

Given snapshotd is OFF,
When the session-start gate runs the snapshot health probe,
Then it fails within about 0.3 s instead of waiting the 5.0 s default connect
timeout, and the ritual finishes in about 0.65 s instead of about 5.7 s.

Given the same session type and areas were requested within the last 45 s,
When the startupd gate handler receives a repeat request,
Then it returns the cached Django markers without a new round-trip, re-signs a
fresh HMAC token from the current minute, and responds in about 0.18 s.

Given a cached entry has expired (older than 45 s),
When the next gate request arrives,
Then the handler re-fetches the markers from Django and stores a new cache entry.

Given snapshotd is healthy,
When the health probe runs,
Then it returns SERVING exactly as before — the short connect timeout does not
change the healthy-path result.

## Test plan (TDD, before or alongside)

- **Python:** `backend/apps/auto_issues/_sidecars/tests_snapshotd_client.py`
  asserts `health()` opens its channel with `connect_timeout=0.3` while the data
  RPCs do not pass a short connect timeout. Run with
  `manage.py test apps.auto_issues._sidecars.tests_snapshotd_client`.
- **Go:** `services/startupd/internal/gate/handler_test.go` asserts a cache hit
  inside the TTL skips the Django call, that an expired entry triggers a
  re-fetch, that the area key is order-insensitive, and that the token is
  re-signed on every request. Run with `go test ./internal/gate/`.

## Regression risks

- A health probe that fails fast must still report a real NOT_SERVING result
  rather than a false "down" when snapshotd is merely slow to accept the socket.
  The 0.3 s value is well above same-host socket latency, so this risk is bounded.
- A cache hit must never serve a stale token. The handler re-signs the token on
  every request from `now`, so the cached value is only the Django marker payload,
  never the token.
- The cache must stay correct under concurrent gate requests. The `sync.Mutex`
  around `get` / `put` guarantees this.

## Out of scope

- No change to the Django session-gate endpoint itself.
- No change to the HMAC secret, the token format, or the hook that verifies it.
- No change to the data RPCs' connect timeout.
