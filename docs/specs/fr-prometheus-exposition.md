# FR — Backend Prometheus Exposition Endpoint

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

Expose backend metrics at `/metrics/` in Prometheus text format, gated by `X-Metrics-Token`, so vmagent can scrape durable application metrics into VictoriaMetrics.

## Sources Of Truth

- Prometheus exposition format documentation, `https://prometheus.io/docs/instrumenting/exposition_formats/`.
- Python Prometheus client documentation, `https://github.com/prometheus/client_python`.
- OpenMetrics specification, `https://openmetrics.io/`.

## Behavior

### Scenario: authorized scrape

Given the backend is running,  
When a request includes the correct `X-Metrics-Token`,  
Then `/metrics/` returns text format with `HELP` and `TYPE` lines.

### Scenario: unauthorized scrape

Given the backend is running,  
When a request omits the token,  
Then the backend returns HTTP 403.

### Scenario: shared registry

Given code registers a metric through `apps.observability.api.register_metric`,  
When `/metrics/` is scraped,  
Then the metric is present in the same registry output.


[SPEC CITED: feature=fr-prometheus-exposition kind=technical_doc id=https://prometheus.io/docs/instrumenting/exposition_formats/ verified_at=2026-06-02]
