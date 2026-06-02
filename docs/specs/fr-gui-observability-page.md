# FR — Observability Stack GUI Page

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

Expose `/observability` as the stack-health page for VictoriaMetrics, vmagent, vmalert, Grafana, Loki, Tempo, Pyroscope, GlitchTip, Faro, SonarQube, OTel Collector, and postgres-exporter.

## Sources Of Truth

- Angular Material documentation, `https://material.angular.io/`.
- Angular routing documentation, `https://angular.dev/guide/routing`.
- Repo deep-linking rule in `DEEP-LINKING-CATALOG.md`.
- Repo plain-English helper rule in `PLAIN-ENGLISH-HELPER-RULE.md`.

## Behavior

Given the user opens `/observability`,  
When the backend returns stack statuses,  
Then the page renders one tile per service, shows status, last sample, open gap count, and opens external dashboards with `noopener,noreferrer`.


[SPEC CITED: feature=fr-gui-observability-page kind=technical_doc id=https://material.angular.io/ verified_at=2026-06-02]
