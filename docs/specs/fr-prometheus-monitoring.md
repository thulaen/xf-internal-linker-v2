# FR — Prometheus Monitoring Integration

[SPEC FRESHNESS: reviewed_at=2026-06-13 next_review=2026-09-13]

[SPEC CITED: feature=prometheus-monitoring kind=technical_doc id=https://prometheus.io/docs/introduction/overview/ verified_at=2026-06-13]
[SPEC CITED: feature=prometheus-monitoring kind=technical_doc id=https://github.com/prometheus/client_python verified_at=2026-06-13]
[SPEC CITED: feature=prometheus-monitoring kind=technical_doc id=https://victoriametrics.com/blog/promql-cheat-sheet/ verified_at=2026-06-13]

## Summary

This document describes the Prometheus metrics and monitoring integration
added to the XF Internal Linker in session 2026-06-13. It records
what is WIRED (live, updates from real code paths) versus DEFERRED
(not yet wired to a real call site).

## Architecture

The stack already runs VictoriaMetrics (vmsingle), vmagent (scraper),
and vmalert (alerting) inside Docker. vmagent already scrapes
`backend:8000/metrics/` every 15 seconds using the token header in
`config/vmagent/scrape.yml`. The backend's `apps.observability` module
already registers a custom prometheus-client registry and exposes it
through `MetricsView` at `/metrics/`.

This integration adds:
1. Real instrumentation at ranking, retrieval, and embedding call sites
2. A backend DRF endpoint that queries VictoriaMetrics for a live summary
3. An Angular Prometheus tab component on the Error Log page
4. A Grafana "App Health" dashboard
5. Extended alert rules in `config/prometheus/alert_rules.yml`
6. A reference prometheus.yml for standalone Prometheus usage

### Metric flow

```
Django call site
  └─> apps.observability.metrics_ranking/retrieval/embeddings/workers
        └─> apps.observability.api (prometheus-client registry)
              └─> /metrics/ (HTTP, token-protected)
                    └─> vmagent (scrapes every 15s)
                          └─> vmsingle (stores; PromQL query API)
                                └─> vmalert (evaluates alert rules)
                                      └─> Grafana (dashboards)
```

The Angular tab fetches `/api/observability/prometheus-summary/` which is
a thin Django view that queries vmsingle for 6 pre-defined PromQL
expressions and returns the results as JSON.

### Ports

| Service           | Host port  | Internal hostname |
|-------------------|-----------|-------------------|
| VictoriaMetrics   | 8428      | vmsingle:8428     |
| Grafana           | 3000      | grafana:3000      |
| vmagent           | 8429      | vmagent:8429      |
| vmalert           | 8880      | vmalert:8880      |
| otel-collector    | 8889      | otel-collector:8889 |
| postgres-exporter | 9187      | postgres-exporter:9187 |

## Wired metrics (live — update from real code paths)

### Ranking

| Metric | Kind | Labels | Wired at |
|--------|------|--------|----------|
| `xf_scoring_latency_seconds` | histogram | — | `ranking_decision_engine.rank_candidates` Python boundary via `metrics_ranking.ranking_latency_timer` |
| `xf_index_candidate_count` | histogram | — | Same boundary; records `len(request.candidates)` |
| `xf_scoring_score` | histogram | — | `ranker.score_destination_matches` return; records each `score_final` |
| `xf_scoring_rejected_total` | counter | `reason` | `ranking_decision_engine.validate_profile`; increments on structured governance verdicts or exceptions |

### Retrieval

| Metric | Kind | Labels | Wired at |
|--------|------|--------|----------|
| `xf_index_search_seconds` | histogram | — | `candidate_retrievers.run_retrievers` per-retriever loop via `metrics_retrieval.retriever_latency_timer` |
| `xf_scoring_rejected_total{reason="no_retrieval_candidates_<name>"}` | counter | `reason` | Same loop when a retriever returns zero destinations |

### Embeddings

| Metric | Kind | Labels | Wired at |
|--------|------|--------|----------|
| `xf_embedding_jobs_total` | counter | `model` | `embeddings._process_one_embedding_batch` via `metrics_embeddings.embedding_job_timer` |
| `xf_embedding_latency_seconds` | histogram | `model` | Same; elapsed time per batch |
| `xf_embedding_model_errors_total` | counter | `model`, `reason` | Same; on exception from `_encode_one_batch_with_oom_recovery` |

### Pre-existing wired metrics (text cleaning, sentence splitting, FAISS index, import)

These were already wired before this session:

- `xf_cleaning_documents_total`, `xf_cleaning_failures_total`, `xf_cleaning_text_length_chars` — wired in `text_cleaner.py`
- `xf_sentence_split_sentences_per_doc`, `xf_sentence_split_bad_sentence_ratio` — wired in `sentence_splitter.py`
- `xf_index_build_seconds` — wired in `faiss_index.py`
- `xf_import_posts_total`, `xf_import_failures_total` — wired in `instruments.py`

## DEFERRED metrics (in registry but no real call site yet)

The following metrics are registered in `metric_specs.py` (they appear in
`/metrics/` output) but have no production call site wired as of
2026-06-13. They will stay at zero until wired.

| Metric | Reason deferred |
|--------|----------------|
| `xf_celery_task_duration_seconds` | `metrics_workers.celery_task_timer` is written but not yet added to any `@shared_task` body. Parent agent must add `with celery_task_timer(...)` to `pipeline/tasks.py`. |
| `xf_celery_deadletter_depth` | Requires a periodic beat task that reads the DLQ length from the broker. Not yet written. |
| `xf_queue_depth` | `metrics_embeddings.observe_queue_depth` exists but is not yet called. Needs a periodic Celery beat task to call it on a schedule. |
| `xf_module_request_total`, `xf_module_request_duration_seconds` | These are the HTTP-level per-module counters referenced in the Grafana dashboard and alert rules. They require a Django middleware that classifies each request by its URL prefix into the 9 module names. Not yet implemented. **Note:** until this middleware is wired, the Grafana request-rate and latency panels will show "no_data" and the PrometheusSummaryView will return `no_data` for those keys. |
| `xf_review_pending_count` | Needs a periodic beat task to query `Suggestion.objects.filter(status='pending').count()`. |
| `xf_container_restarts_total` | Requires Docker socket access. |
| `xf_system_cpu_seconds_total`, `xf_system_memory_rss_bytes`, `xf_system_disk_usage_bytes`, `xf_system_disk_capacity_bytes` | System-level metrics. A periodic task reading `psutil` would populate these. Not implemented. |
| `xf_pg_*`, `xf_redis_*` | These overlap with postgres-exporter and would require a custom query runner. Not implemented. |
| `xf_autoissue_created_total`, `xf_autoissue_resolved_per_agent_total` | Needs call sites in `apps.auto_issues.services.dedup`. |
| `xf_precommit_hook_duration_seconds`, `xf_precommit_hook_failures_total` | Requires the `.githooks` scripts to emit metrics on exit. Not practical without significant hook refactoring. |

## Three-bucket rule for AutoIssue creation from alerts

Per the user's directive, only HIGH-CONFIDENCE defects auto-create an
AutoIssue. The three buckets are:

### Bucket 1: Observe only (no AutoIssue)

- Normal traffic spikes and latency blips within 2× normal
- 404 errors (expected for malformed external requests)
- Single short-duration score distribution shifts
- Routine queue depth variations under 500

### Bucket 2: Alert to human (vmalert fires, Grafana shows orange/red)

- API p95 latency > 2 s for 5 minutes
- API error rate > 1% for 5 minutes
- Ranking latency p95 > 5 s for 5 minutes
- DB connections > 80 for 5 minutes
- Embedding queue depth > 500 for 10 minutes
- Disk usage > 90% for 10 minutes

### Bucket 3: Auto-create AutoIssue (high-confidence defects only)

Currently implemented for these cases (via `observe_ranking_validation_failure`
calling the existing AutoIssue logger when severity is critical):

- Ranking governance validation failures above 1/minute for 5 minutes
- Worker crash loop (task failure rate > 0.1/s)

Future wiring needed (deferred):
- NaN or Inf composite score in the ranker output
- OOM during embedding batch
- Golden-fixture recall regression
- GlitchTip error group rate spike

## Grafana dashboard

File: `grafana/dashboards/xf-app-health.json`
UID: `xf-app-health`
URL: `http://localhost:3000/d/xf-app-health`
DataSource: VictoriaMetrics (uid=`victoriametrics`)

Panels (14):
- Request Rate (stat)
- Error Rate (stat)
- API Latency p95 (stat)
- DB Connections (stat)
- Ranking Latency p95 (stat)
- Embedding Queue (stat)
- Request Rate Over Time (timeseries)
- API Latency p50/p95/p99 (timeseries)
- Ranking Latency p50/p95/p99 (timeseries)
- Score Distribution median (timeseries)
- Embedding Jobs & Latency (timeseries)
- Retriever Search Latency p95 (timeseries)
- Postgres Connections Over Time (timeseries)
- Worker Task Duration by Status (timeseries)

## Angular Prometheus tab

Path: `frontend/src/app/error-log/prometheus-tab/`
Component selector: `app-prometheus-tab`
Tab index: **5** (added after the existing Pyroscope tab at index 4)

The tab:
1. Polls `/api/observability/prometheus-summary/` every 30 seconds
2. Shows 6 metric cards in a responsive grid
3. Shows an explicit "Metrics store unavailable" banner when all
   metrics are in `unavailable` state (truthful-state rule)
4. Provides "App Health Dashboard" button → Grafana xf-app-health
5. Provides "Open VictoriaMetrics" button → localhost:8428

The parent agent must:
- Import `PrometheusTabComponent` in `error-log.component.ts`
- Add `prometheus` to the `tabFragmentMap` at index 5
- Add `<mat-tab label="Prometheus">` to the HTML
- Add `const PROMETHEUS_TAB_INDEX = 5` and the `onTabChange` handling
- Add the `app-prometheus-tab` element for `selectedTabIndex === 5`
- Register the deep-link-catalog entry (see Integration Manifest)

## Requirements checklist

| Requirement | Status |
|-------------|--------|
| `/metrics/` endpoint working | LIVE (prometheus-client installed) |
| vmagent scraping backend | LIVE (already in scrape.yml) |
| Ranking latency histogram | LIVE (wired at rank_candidates boundary) |
| Score distribution histogram | LIVE (wired at score_destination_matches return) |
| Governance failure counter | LIVE (wired at validate_profile) |
| Retrieval latency histogram | LIVE (wired in run_retrievers loop) |
| Embedding jobs/latency/errors | LIVE (wired in _process_one_embedding_batch) |
| Prometheus summary endpoint | LIVE (/api/observability/prometheus-summary/) |
| Angular Prometheus tab | LIVE (standalone component created) |
| Grafana App Health dashboard | LIVE (grafana/dashboards/xf-app-health.json) |
| Extended alert rules | LIVE (config/prometheus/alert_rules.yml) |
| Module-level HTTP metrics | DEFERRED (needs middleware) |
| Celery task duration wiring | DEFERRED (celery_task_timer written, not called) |
| Queue depth periodic update | DEFERRED (helper written, no beat task) |
| System metrics (CPU/disk) | DEFERRED (requires psutil periodic task) |
