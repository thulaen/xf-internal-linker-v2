# startupd HTTP API

## GET /health

Returns `200 OK` with `ok` when the helper process is alive.

## GET /payload

Returns the latest backend-written session startup payload as JSON.

Failure cases:

- `404 Not Found` when the payload file is missing.
- `503 Service Unavailable` when the payload file exists but has no valid JSON-lines record.

## GET /gate

Lean session-start gate. Proxies to Django's `/api/session-gate/` to
retrieve the six DB-backed markers, signs the response with an HMAC-SHA256
token, writes `audit/session_gate_state.json`, and returns the assembled
marker block.

Query params:
- `type` — session type: `docs`, `infrastructure`, `reconciliation`, `feature`.
  Returns `400 Bad Request` for unknown values.
- `area` — repeatable repo-relative path for scoped lesson lookup.
  Example: `?type=reconciliation&area=backend/apps/core&area=backend/apps/auto_issues`

Success response (`200 OK`):
```json
{
  "marker_block": "[STICKY 1 READ: ...]\n[REGISTRY READ: ...]\n...",
  "state": {
    "session_type": "reconciliation",
    "layer2_autoissues": 10,
    "layer2_paper_trail": 3,
    "token": "<16 hex chars>",
    "ts": 28478880,
    "total_open_count": 142,
    "generated_at": "2026-05-28T12:00:00Z"
  }
}
```

Failure cases:
- `400 Bad Request` — unknown session type.
- `502 Bad Gateway` — Django backend unreachable.
- `500 Internal Server Error` — could not write `session_gate_state.json`.

Token algorithm: `HMAC-SHA256(SESSION_GATE_SECRET, "session_type|unix_minute|total_open_count")`,
first 16 hex chars.  The Python hook at `.githooks/check-registry-read.py`
re-derives the token at commit time to prove the gate ran during this session.

## GET /debug/pprof/

Serves Go runtime profiling data through the standard Go `net/http/pprof` handlers.
