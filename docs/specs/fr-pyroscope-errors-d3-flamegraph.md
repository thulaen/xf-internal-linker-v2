# Pyroscope Errors Tab D3 Flamegraph

[SPEC CITED: feature=pyroscope-errors-d3-flamegraph kind=technical_doc id=https://grafana.com/docs/pyroscope/latest/reference-server-api/ verified_at=2026-05-20]
[SPEC CITED: feature=pyroscope-errors-d3-flamegraph kind=technical_doc id=https://d3js.org/d3-hierarchy/partition verified_at=2026-05-20]
[SPEC CITED: feature=pyroscope-errors-d3-flamegraph kind=academic_paper id=https://vis.stanford.edu/files/2011-D3-InfoVis.pdf verified_at=2026-05-20]
[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Goal

Show operators a D3-rendered flamegraph preview directly on the Errors page
when they click the Pyroscope tab. D3 means the existing JavaScript charting
library used to draw data-driven shapes in the browser. A flamegraph means a
stack-shaped profiling view where wider blocks represent more time spent in
that function or task.

## Sources Of Truth

| Source | Type | Design decision |
|---|---|---|
| Grafana Pyroscope server API | technical_doc | Pyroscope exposes profile data as flamegraph-shaped JSON through `/pyroscope/render`, and large graphs should be capped with `maxNodes`. |
| D3 partition layout documentation | technical_doc | Use `d3.hierarchy(...).sum(...)` and `d3.partition()` to assign rectangle coordinates for hierarchy nodes. |
| Bostock, Ogievetsky, and Heer, "D3: Data-Driven Documents" | academic_paper | Use D3 because it binds data directly to browser elements and supports custom visual encodings without a chart wrapper. |

## Behavior

Given the operator opens the Errors page,
When they click the Pyroscope tab,
Then the tab shows a non-empty D3 flamegraph preview plus a Visit Pyroscope link.

Given Pyroscope AutoIssues exist,
When the Pyroscope tab renders,
Then the graph uses those open Pyroscope rows and dedupes repeated root causes
by canonical fingerprint or external id.

Given Pyroscope AutoIssues are not loaded yet,
When the Pyroscope tab renders,
Then the graph shows a small local preview so the tab is not a blank launcher.

## Implementation Notes

- Use the existing `d3` dependency already in `frontend/package.json`.
- Do not add Three.js.
- Keep the preview bounded to the top 12 open Pyroscope AutoIssues.
- Keep the Pyroscope dashboard as the source of truth for full flamegraph drilldown.
- Load AutoIssues when the Pyroscope tab opens, the same way the AutoIssues and
  SonarQube tabs do.

## Tests

- `frontend/src/app/error-log/error-log.component.spec.ts` checks that the
  Pyroscope tab loads AutoIssues.
- `frontend/src/app/error-log/error-log.component.spec.ts` checks that the
  Pyroscope tab renders D3 flamegraph rectangles.
- Existing SonarQube task tests continue to prove scanner/import automation is
  wired through Docker Compose plus Celery beat.
