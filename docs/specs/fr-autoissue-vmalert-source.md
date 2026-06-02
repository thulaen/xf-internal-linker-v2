# FR — vmalert AutoIssue Source

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

Add `vmalert` as an AutoIssue source so metric alerts and observability gaps enter the same repair queue as logs, traces, profiles, browser telemetry, code scans, and agent findings.

## Sources Of Truth

- VictoriaMetrics vmalert HTTP API, `https://docs.victoriametrics.com/vmalert/#api`.
- Existing GitHub Actions picker pattern in `backend/apps/auto_issues/services/ci_failed_runs.py`.
- Repo AutoIssue opening ritual in `AGENTS.md`.

## Behavior

### Scenario: firing alert

Given vmalert returns one firing alert,  
When the picker runs,  
Then exactly one AutoIssue is created or merged with `source="vmalert"`.

### Scenario: resolved alert

Given an existing vmalert AutoIssue is open,  
When vmalert returns that alert as resolved,  
Then the AutoIssue is marked resolved with `Trap:` and `Fix shape:` lessons from alert annotations.

### Scenario: duplicate alert

Given the same alert fires again,  
When the picker runs,  
Then occurrence count increases and no duplicate row is created.


[SPEC CITED: feature=fr-autoissue-vmalert-source kind=technical_doc id=https://docs.victoriametrics.com/vmalert/ verified_at=2026-06-02]
