# Observability Options On Top Of GlitchTip

GlitchTip catches **errors** — every Python exception and every JavaScript error becomes a row in the dashboard. This document lists what else you could add to also catch:

- **Performance issues** — endpoints that are slow but don't crash
- **Resource issues** — high CPU, high RAM, queue backlog, slow database queries
- **Availability issues** — services down, dashboards 502'ing
- **User-facing slowness** — page load times, layout shifts, slow interactions

Each option below includes: what it catches, the cost (RAM / disk / time to set up), and a recommendation on whether to add it.

## Already-paid-for: enable what GlitchTip and the Sentry SDK already ship

These cost zero new services — just config changes. **Do these first** before adding new tools.

### 1. Bump `traces_sample_rate` to capture transaction performance

The Sentry SDK already initialised in [`backend/config/settings/base.py:538-571`](../backend/config/settings/base.py) has `traces_sample_rate=0.1` — meaning 10 % of every Django view + Celery task is recorded as a "transaction" with timings. GlitchTip's UI shows these under **Performance** → **Transactions**. You can already see slow endpoints, slow database queries, slow cache reads.

Currently usable as-is. To get more data: bump the rate to `0.5` or `1.0` in dev, leave `0.1` in prod. Each transaction is a small JSON blob; storage cost is GlitchTip's existing 90-day retention partition rotation.

**Cost:** zero new services. **Add when:** you want to know "which endpoint is slow" without instrumenting code.

### 2. Add `@sentry_sdk.trace` decorators on hot paths

For specific functions where the auto-instrumentation isn't granular enough (e.g. a single Celery task that does 5 different things), wrap them with `@sentry_sdk.trace` to record fine-grained spans. The hot paths to consider: ranking pipeline, BGE-M3 embedding calls, cooccurrence scoring.

**Cost:** ~5 lines per function. **Add when:** Performance tab shows a slow transaction but you can't tell which inner call is the culprit.

### 3. Turn on GlitchTip's built-in Uptime Monitoring

GlitchTip ships an uptime feature — periodic HTTP probes that page you when an endpoint goes down. Visit http://localhost:1337/{org}/uptime-monitors/, add a monitor pointing at `http://nginx/api/system/health/` (or your public URL once deployed), pick a check interval (5 min is reasonable). The migration tables `uptime_monitorcheck` and `uptime_uptimecheckhourlystatistic` already exist; they were created by `glitchtip-migrate`.

**Cost:** zero new services, ~30 s of UI clicking. **Add when:** you want to know "is the dashboard / API actually reachable right now?" without manually visiting.

### 4. Enable browser session replay

The frontend Sentry SDK at [`frontend/src/main.ts`](../frontend/src/main.ts) supports session replay — short video-like recordings of the user's session leading up to an error. You see exactly what they clicked / typed / scrolled before the crash. Add `Sentry.replayIntegration()` to the SDK init and bump `replaysSessionSampleRate: 0.1, replaysOnErrorSampleRate: 1.0`.

**Cost:** zero new services, ~5 lines in `main.ts`, ~50 KB of bundle size for the replay SDK. **Add when:** UI bugs are reported but you can't reproduce them.

## Add new services: only when you've outgrown the GlitchTip-only stack

These are real new Docker services. Each adds RAM/disk and one more thing to maintain. Pick **one** at a time.

### 5. Pyroscope — continuous profiling (which Python code is slow)

Pyroscope shows you flamegraphs of where Python time is being spent across the entire stack — like having `cProfile` running 24/7. Plug a small Python agent into the backend and Celery workers via `pyroscope-io`, and a Pyroscope server captures and renders flamegraphs. Best when GlitchTip's transaction view says "this endpoint is slow" but you want the function-level breakdown.

**Cost:** ~256 MB RAM for the Pyroscope server, ~2-3 % CPU overhead per profiled process, ~5 lines of agent init in `wsgi.py` and the Celery worker startup. One new compose service. **Add when:** GlitchTip transactions point at slow paths but you need flamegraphs to find the actual hot lines.

**Recommended.** Highest signal-per-RAM-MB of all options here.

### 6. Prometheus + Grafana — system + queue + database metrics

Prometheus scrapes time-series metrics from instrumented endpoints (per-endpoint request rate / latency, Celery queue depth, Postgres connection pool usage, Redis memory, GPU utilisation). Grafana renders them as dashboards. Use this when you want **trends over time** that GlitchTip's per-transaction view can't show — "p99 latency over the last 24 h" or "queue depth grew 10× during the GA4 sync."

**Cost:** ~512 MB RAM for both services combined, persistent volume for ~30 days of metrics, ~30 min to set up the Django + Celery exporters. Two new compose services. The `django-prometheus` and `celery-exporter` Python packages do most of the work.

**Add when:** you want to compare today vs. last week, set alerts on metric thresholds, or correlate spikes across services.

### 7. Loki — centralised log aggregation

Replaces `docker logs` as the place you go to read what went wrong. Loki indexes logs by labels (service, level, etc.) and you query them from Grafana with a SQL-like syntax. Pairs well with Prometheus + Grafana — same UI for metrics and logs.

**Cost:** ~256 MB RAM, persistent volume that grows with log volume (compresses well — ~10 MB/day for this stack), one new compose service plus a log forwarder (`promtail`).

**Add when:** you've already got Grafana running and you're tired of `docker compose logs <service>` to find a recent error.

### 8. OpenTelemetry — vendor-neutral tracing layer

Standard for distributed traces. The Sentry/GlitchTip SDK already produces OpenTelemetry-compatible spans. The point of OpenTelemetry is to send those spans to **multiple** backends simultaneously — GlitchTip for error-to-trace correlation, plus Tempo or Jaeger for deep distributed-trace UIs. Worth adding **only** if you outgrow GlitchTip's tracing UI.

**Cost:** OTel collector ~256 MB, plus Tempo/Jaeger ~1 GB if you choose to run a tracing backend, ~1 hour of plumbing.

**Skip unless** you've genuinely outgrown GlitchTip's Performance tab — which for a single-host stack like this one is unlikely.

## Cheat sheet — what should you add first

| You want to know... | Use this | Already runs? |
|---|---|---|
| "Did anything crash?" | GlitchTip Issues | ✅ Yes |
| "Which endpoint is slow?" | GlitchTip Performance + raise `traces_sample_rate` | ✅ Yes — just config |
| "Is the dashboard up right now?" | GlitchTip Uptime | ✅ Yes — just enable in UI |
| "What did the user click before the crash?" | Sentry Session Replay | Add 5 lines to `main.ts` |
| "Which line of Python is hot?" | Pyroscope | Add 1 service |
| "Is queue depth spiking?" | Prometheus + Grafana | Add 2 services |
| "Where's the error in the log stream?" | Loki + Grafana | Add 2 services |

## My recommendation (vibe-coder-friendly)

In order:

1. **Enable session replay** in the frontend SDK (5 lines, zero new services). Highest UX signal.
2. **Bump `traces_sample_rate` to 0.3** in dev so GlitchTip Performance has more data to render.
3. **Click "Add Uptime Monitor"** in the GlitchTip UI for the `/api/system/health/` endpoint.
4. **Add Pyroscope** (one Docker service) once you find a slow endpoint and want to see the inner hot path.

Stop there unless you find concrete unmet observability needs — adding more tools you don't actively use is just maintenance debt. Each new tool adds a bit of RAM, a bit of disk, and a place to forget about until it bit-rots.
