# FR — Reserved vmalert Rules

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

Define the first reserved alert rules that turn durable metrics into AutoIssues through vmalert.

## Sources Of Truth

- VictoriaMetrics vmalert documentation, `https://docs.victoriametrics.com/vmalert/`.
- VictoriaMetrics MetricsQL documentation, `https://docs.victoriametrics.com/metricsql/`.
- Prometheus alerting practices, `https://prometheus.io/docs/practices/alerting/`.

## Rules

Rules must include `summary`, `description`, `trap`, and `fix_shape` annotations so resolved AutoIssues carry the required two-part lesson.

## Behavior

Given a rule condition crosses the documented threshold,  
When vmalert evaluates the group,  
Then the matching alert fires with a severity label and the required annotations.


[SPEC CITED: feature=fr-reserved-alerts kind=technical_doc id=https://docs.victoriametrics.com/vmalert/ verified_at=2026-06-02]
