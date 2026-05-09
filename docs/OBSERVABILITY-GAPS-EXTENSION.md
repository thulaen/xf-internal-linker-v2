# Observability — Gaps Beyond GlitchTip + Pyroscope

GlitchTip catches **errors** (Python exceptions, JS exceptions, transactions). Pyroscope catches **CPU flamegraphs** (which Python is hot). Together they cover the most common "the app crashed" / "the app is slow" cases. This document lists the categories they DON'T cover and how to fill each gap, with an honest "wired today / not wired" label per item.

The four `auto_issues` pickers (GlitchTip, Pyroscope, internal-errors, slow-queries) plus the weekly pip-audit task already cover 5 of the 11 gaps below. The remaining 6 are catalogued for follow-up sessions.

## Gap matrix

| # | Gap | Symptom | Status | Wired by |
|---|---|---|---|---|
| 1 | **DB slow queries** | A query slowly degrades from 50 ms to 5 s. No exception, no CPU spike (the query is slow because of bad plan or missing index, not Python). | **WIRED** | `pg_stat_statements` extension + `pick_daily_slow_queries` Celery task → AutoIssue rows with `mean_exec_ms` ranking |
| 2 | **Browser performance / Web Vitals** | Page feels sluggish but no JS error fires. LCP, INP, CLS, FID, TTFB are not captured by exception tracking alone. | **WIRED** | `Sentry.browserTracingIntegration()` in `frontend/src/main.ts` — captures all 5 Web Vitals as measurements on the page-load transaction in GlitchTip's Performance tab |
| 3 | **Dependency CVEs** | `requests==2.31.0` ships a known CVE; pip-audit reports it; no test fails; nothing in the app crashes; CVE sits unpatched. | **WIRED** | `pip-audit==2.7.3` in requirements + `pick_weekly_pip_audit_findings` Celery task (Mondays 11:35 UTC) → AutoIssue rows with stable `(package, cve_id)` canonical fingerprint |
| 4 | **Memory leaks** | Backend RAM grows from 1 GB to 6 GB over a week. No exception, no CPU spike, no slow query. Eventually OOMs, restart_always recovers, cycle repeats. | NOT YET — see "Memory profiling (memray)" below |
| 5 | **Disk pressure** | `media_files` volume fills, future image writes silently fail or get partial. | PARTIAL — `apps.pipeline.services.disk_pressure.require_free_disk()` exists; needs a Celery beat probe that emits AutoIssue when free space crosses thresholds |
| 6 | **External API health** | GA4 / GSC / Matomo APIs throttle to 1 req/min. Every call eventually returns 429 or 503; sync tasks retry but data lags 4 hours. | NOT YET — see "Synthetic SLO probes" below |
| 7 | **Cron job missed runs** | Celery beat dispatches a task; worker is at concurrency cap; task expires unread; nobody knows. | PARTIAL — schedule_tracker exists; doesn't surface missed runs as AutoIssue |
| 8 | **Data quality regressions** | Ranking output suddenly has 10× more zero-scored rows than yesterday. No exception, no slow query — just bad output. | NOT YET — see "Output-quality probes" below |
| 9 | **Security misconfigurations at runtime** | `DEBUG=True` left on in prod; `ALLOWED_HOSTS=*`; CSRF cookie not Secure. | PARTIAL — Django's deploy-checks catch most; not surfaced as AutoIssue |
| 10 | **Test coverage erosion** | A commit drops `apps.audit` coverage from 85 % → 60 %; no test fails, just less safety. | NOT YET — needs coverage gate in pre-push |
| 11 | **Frontend bundle size regression** | A new dependency adds 800 KB to the prod bundle; LCP creeps up but no error fires. | NOT YET — needs `bundle-size-limit` script in CI |

## Five new gap-fillers wired this session (concrete code, not deferred)

### 1. pg_stat_statements → slow-query picker (gap #1)

- **Files**: [`postgres/postgresql.conf`](../postgres/postgresql.conf) preloads the extension, [`backend/apps/auto_issues/services/slow_query_picker.py`](../backend/apps/auto_issues/services/slow_query_picker.py) reads `pg_stat_statements` and surfaces queries with `mean_exec_time > 100 ms` ranked by `total_exec_time`. Daily 11:25 UTC via Celery beat.
- **Cross-source dedup**: same `queryid` → stable canonical fingerprint, so a slow query that's ALSO captured by Sentry-SDK as "slow transaction" merges onto one AutoIssue row.
- **Cost**: `pg_stat_statements` adds ~1-3 % overhead per query and 3 MB shared memory. Acceptable for dev/local stack.

### 2. Sentry browser-tracing integration (gap #2)

- **File**: [`frontend/src/main.ts`](../frontend/src/main.ts) — added `Sentry.browserTracingIntegration()` to the SDK init.
- **Captures**: LCP (Largest Contentful Paint), INP (Interaction to Next Paint), FID (First Input Delay), CLS (Cumulative Layout Shift), TTFB (Time to First Byte) as measurements on page-load transactions.
- **Where to see**: GlitchTip → Performance tab → page-load transactions show vital scores per route.
- **Cost**: ~10 KB extra in the lazy-loaded SDK chunk. No new services.

### 3. pip-audit weekly CVE scan (gap #3)

- **Files**: [`backend/requirements.txt`](../backend/requirements.txt) (`pip-audit==2.7.3`), [`backend/apps/auto_issues/services/pip_audit_picker.py`](../backend/apps/auto_issues/services/pip_audit_picker.py) runs `pip-audit --format json` and surfaces each CVE.
- **Schedule**: Weekly Monday 11:35 UTC.
- **Cross-source dedup**: same `(package, cve_id)` → stable canonical fingerprint so the same CVE re-scanned every week updates the existing row.
- **Cost**: ~30-180 s per run (network call to PyPI advisory DB). Once a week is fine.

## Recommended next gap-fillers (NOT YET wired)

### 4. Memory leak detection (gap #4) — recommend `memray` or `tracemalloc`

`memray` is the modern Python memory profiler. It records every allocation and produces a flamegraph showing where memory is held. Two options:
- **Pull mode** (run on demand via management command when RAM is high) — cheap, ad-hoc.
- **Continuous** (memray-rust agent shipping to a flamegraph server, similar to Pyroscope's CPU flamegraphs but for memory) — heavier; only worthwhile if memory bugs are recurring.

Cost: ~5 % CPU + 10-20 % memory in continuous mode. **Recommendation: don't wire continuous yet; add a `manage.py memray_report` command for ad-hoc.**

### 5. Disk pressure → AutoIssue (gap #5) — extend existing `disk_pressure` helper

The codebase already has `apps.pipeline.services.disk_pressure.require_free_disk()`. A new Celery beat task `pick_daily_disk_pressure` would call `current_state()` every hour and emit an AutoIssue when free space crosses the existing watermarks. ~30 lines of code, fits the same dedup pattern as the other pickers.

### 6. Synthetic SLO probes (gap #6) — recommend `prober` task pattern

Define a list of `(name, url, expected_status, max_latency_ms)` tuples. A Celery beat task fires every 15 min, hits each URL, records latency. When latency p95 over the last 24 h exceeds threshold, emit an AutoIssue. Targets:
- `https://analyticsdata.googleapis.com/v1beta/properties/.../runReport` (GA4 health)
- `https://www.googleapis.com/oauth2/v3/tokeninfo` (Google auth health)
- `https://${matomo_url}/index.php?module=API&method=...` (Matomo health)

Cost: ~one HEAD request per URL per 15 min — trivial. Adds 1 new Celery task.

### 7. Schedule-tracker missed-run surfacer (gap #7)

The existing `apps.scheduled_updates.schedule_tracker` already logs missed runs. Wire a `pick_daily_missed_runs` task that reads its findings into AutoIssue. ~50 lines of code.

### 8. Output-quality probes (gap #8) — domain-specific, deferred

Define quality metrics per pipeline stage (e.g. "fraction of suggestions with score=0", "fraction of pages where embeddings are missing"). When the metric crosses a threshold, emit AutoIssue. Needs domain knowledge of what counts as a regression for THIS codebase. Not a generic plug-in.

### 9. Security check at runtime (gap #9)

Django's `manage.py check --deploy` already emits a list of misconfigurations. A Celery beat task running it weekly + parsing output → AutoIssue would close the gap. ~30 lines.

### 10. Coverage erosion gate (gap #10) — pre-push hook

Add a `.githooks/pre-push` step that runs `coverage run + coverage json` and refuses the push if `coverage.totals.percent_covered` drops more than 2 percentage points from `git show main:coverage.json`. Needs a baseline-coverage file checked into the repo.

### 11. Frontend bundle size regression (gap #11) — CI gate

Use `bundlewatch` or `size-limit` against `frontend/dist/main-*.js`. Refuse the build if it grows >10 % vs the last successful build's recorded size. Adds ~30 s per CI run.

## Recommended priority order

1. **Disk pressure picker** (gap #5) — trivial, the helper already exists.
2. **Synthetic SLO probes** (gap #6) — high signal for external-API users; one Celery task.
3. **Schedule-tracker missed-run surfacer** (gap #7) — closes a real silent failure mode.
4. **memray ad-hoc** (gap #4) — manage.py command, no continuous service.
5. **Django deploy-check picker** (gap #9) — one Celery task; weekly.
6. The rest (output-quality, coverage, bundle-size) when needed.

## What's deliberately NOT in scope

- **Distributed tracing UI beyond GlitchTip's Performance tab.** OpenTelemetry already feeds traces into GlitchTip via the `sentry` exporter. Adding Tempo/Jaeger as a parallel store duplicates work. Add only if GT's UI proves insufficient.
- **Loki / log aggregation.** Logs go to `docker compose logs <service>` and OTel collector's stdout. Adding Loki + Grafana adds 2-3 services for marginal gain at our scale.
- **APM SaaS** (DataDog, NewRelic). Self-hosted GlitchTip + Pyroscope cover the same ground. Only justified at scale > 100k events/day.
