# FR — Agent-Aware Correlation

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

Link related symptoms across logs, traces, profiles, metrics, code scans, AutoIssues, and Paper Trail rows so agents see one likely cause group instead of isolated noise.

## Sources Of Truth

- "Dapper, a Large-Scale Distributed Systems Tracing Infrastructure", Google, 2010, `https://research.google/pubs/dapper-a-large-scale-distributed-systems-tracing-infrastructure/`.
- "Graph-based root cause analysis for service-oriented and microservice architectures", Journal of Systems and Software 2020, DOI `10.1016/j.jss.2019.110432`.
- Patent US10581891B1, graph models for datacenter anomaly detection, `https://patents.google.com/patent/US10581891B1`.
- Patent US11237897B2, ensemble anomaly detection, `https://patents.google.com/patent/US11237897B2`.

## Capabilities

1. Cause-and-effect graph.
2. Contradiction detector.
3. Dynamic source trust score.
4. Evidence freshness score.
5. Contextual remediation suggestions.
6. Self-querying historical fixes.

## Behavior

### Scenario: related observability symptoms

Given Loki, GlitchTip, and Pyroscope report related symptoms,  
When correlation runs,  
Then one cause group is shown with the shared files, sources, confidence, and next action.

### Scenario: contradictory evidence

Given one source says a service is healthy and another reports fresh failures,  
When the work queue projection runs,  
Then the contradiction is visible and the lower-confidence source is not allowed to hide the problem.

### Scenario: stale evidence

Given a Paper Trail row points at changed files,  
When its evidence is stale,  
Then `/work-queue` marks it stale and asks for refresh.

## Ranking

Cause groups rank by severity, source count, recency, source confidence, and whether an issue blocks agent work.


[SPEC CITED: feature=fr-agent-aware-correlation kind=technical_doc id=https://research.google/pubs/dapper-a-large-scale-distributed-systems-tracing-infrastructure/ verified_at=2026-06-02]
