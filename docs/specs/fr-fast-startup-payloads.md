# Fast Startup Payloads

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Intent

Agent session startup must read one cached payload instead of running several slow live commands. A payload is a single JSON-lines record containing the required startup markers and a plain-English status body.

## Behavior

Given an agent session starts, When it asks for startup markers, Then `python scripts/session_start_payload.py` reads the cached payload through the Go helper and returns within 5 seconds without starting Django.

Given the cached payload is stale but still readable, When `python scripts/session_start_payload.py` runs during normal chat startup with auto-refresh enabled, Then it prints the cached payload immediately, keeps `[HANDOFF READ: ...]` as the first line, inserts `[STARTUP PAYLOAD STALE: ...]` as the second line, starts a background refresh, and does not run the slow live checks.

Given the cached payload is stale but still readable, When `python scripts/session_start_payload.py --no-auto-refresh` runs, Then it exits non-zero and does not print stale markers because the caller withheld consent to serve stale data.

Given the cached payload is missing or unreadable, When `python scripts/session_start_payload.py` runs during normal chat startup, Then it prints a clear error within 5 seconds and stops instead of running the slow live checks.

Given the slow live checks need to refresh the cache, When `manage.py refresh_session_start_payload` runs outside the chat path, Then Python gathers the live marker outputs and writes one current JSON-lines payload for the Go helper to serve.

## Design

Python remains the source of truth for database reads. It owns payload creation because Django already owns AutoIssues, Paper Trail, sticky reads, and test-first preflight commands.

Go owns the fast read path. The `startupd` helper serves the latest payload from a backend-written JSON-lines file over HTTP and exposes Go `pprof` profiling endpoints under `/debug/pprof/`.

The proactive refresh layer remains in the Python backend schedule, not in Go. The scheduled task `auto_issues.refresh_session_start_payload` runs every 120 seconds, which is strictly before the 5-minute payload expiry. This keeps normal operation fresh while preserving the boundary that Go never owns database tables and never runs Django logic.

The cache file is overwrite-in-place with one JSON record, so it does not grow without bound. The payload includes `version`, `generated_at`, `expires_at`, `markers`, and `body`.

The command deadline is 5 seconds by default. A caller may lower the timeout for tests, but production startup must not wait longer than the default. The Django management command remains as a compatibility path, but the 5-second chat path is the non-Django wrapper because Django startup can exceed the budget before command logic runs.

## Tests

- Python unit tests prove marker extraction, stale payload rejection, and atomic cache writes.
- Python command tests prove `session_start_payload` prints cached markers and fails clearly when the helper is unavailable.
- Plain Python wrapper tests prove the chat startup path works without Django imports.
- Plain Python wrapper tests prove stale cached payloads exit zero with auto-refresh enabled, keep `[HANDOFF READ: ...]` first, print a stale marker second, and still exit non-zero when `--no-auto-refresh` is used.
- Go unit tests prove latest-payload loading, missing-file behavior, HTTP payload serving, health serving, and `pprof` route registration.
- Go benchmark proves cached payload reads stay well below the 5-second command budget.

## Citations

- Go standard library documentation, `net/http/pprof`, 2026. Source for built-in HTTP runtime profiling endpoints. https://pkg.go.dev/net/http/pprof
- Python standard library documentation, `subprocess`, 2026. Source for bounded process timeouts and timeout failure behavior. https://docs.python.org/3/library/subprocess.html
- Django Software Foundation, Django cache framework documentation, 2026. Source for cache-staleness framing and explicit timeout behavior. https://docs.djangoproject.com/en/5.2/topics/cache/

[SPEC CITED: feature=fr-fast-startup-payloads kind=technical_doc id=https://pkg.go.dev/net/http/pprof verified_at=2026-06-02]
