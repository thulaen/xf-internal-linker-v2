# FR — Agent Work Queue Control Center

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

Build `/work-queue` as the agent-aware control center for AutoIssues, Paper Trail rows, self-healing decisions, repair claims, conflicts, and next actions. `/diagnostics` stays the compact health overview. `/mcp` stays the agent connection page. Both link into `/work-queue`.

## Sources Of Truth

- Parnas, "On the Criteria To Be Used in Decomposing Systems into Modules", CACM 1972, DOI `10.1145/361598.361623`.
- ISO/IEC/IEEE 29119-3:2021 for behavior-focused test documentation.
- Model Context Protocol specification, `https://modelcontextprotocol.io/specification/2025-06-18/basic/index`.
- Django official documentation for class-based views and application layout, `https://docs.djangoproject.com/`.
- Angular official documentation for standalone routes and components, `https://angular.dev/`.

## Scope

The `backend/apps/work_queue/` app owns decision support, not raw observability storage.

Responsibilities:

- read AutoIssues and Paper Trail rows;
- build live queue projections for the GUI;
- track agent claims and repair attempts;
- block unsafe parallel repair when two agents touch the same resource;
- expose gated MCP tools;
- surface current blockers, stale evidence, likely cause groups, and next actions.

It does not store metrics. Metrics stay in `backend/apps/observability/` and VictoriaMetrics.

## Layout Contract

```text
backend/apps/work_queue/
├── api.py
├── models.py
├── services/
│   ├── agent_attempts.py
│   ├── correlation.py
│   ├── gui_projection.py
│   ├── remediation.py
│   └── self_healing.py
├── tasks.py
├── urls.py
└── views.py
```

`api.py` is the only public Python surface. Views and MCP tools call `api.py`, not private service files.

## Behavior

### Scenario: live issue change feed

Given an AutoIssue changes,  
When the work queue feed refreshes,  
Then the GUI shows the update without a full page reload by polling and listening for the `work_queue` real-time topic.

### Scenario: failed-attempt loop stop

Given an agent repeats the same failed fix three times,  
When it reports the same repair fingerprint again,  
Then the system marks the next attempt blocked and returns a final-report instruction instead of allowing another unsafe loop.

### Scenario: file conflict

Given two agents claim tasks touching the same file,  
When the second claim is created,  
Then the second claim is marked `conflicted` and the GUI blocks unsafe parallel repair.

### Scenario: MCP repair task

Given an MCP-connected agent claims a task,  
When it runs checks,  
Then the task records the command result, blocker, and next action.

### Scenario: user preference learning

Given user choices repeatedly prefer one issue type,  
When ranking refreshes,  
Then that issue type rises in the work queue through source confidence and attention rules.

## API Contract

- `GET /api/work-queue/overview/`
- `GET /api/work-queue/feed/`
- `GET /api/work-queue/cause-groups/`
- `POST /api/work-queue/tasks/<item_key>/claim/`
- `POST /api/work-queue/tasks/<item_key>/release/`
- `POST /api/work-queue/tasks/<item_key>/rehearse/`
- `GET /api/work-queue/self-healing/`
- `POST /api/work-queue/self-healing/<id>/approve/`

`item_key` uses `autoissue-<id>` or `papertrail-<id>` so the API can stay stable while both stores remain separate.

## Bounded History

Agent attempts are indexed by `(item_kind, item_id, agent, attempt_fingerprint)` and only the count needed for loop detection is queried. Source confidence rows dedupe by `source`. Claims are active until released or completed.

## Out Of Scope

- direct code editing through MCP;
- bypassing repo test, commit, and paper-trail gates;
- full observability metric storage.


[SPEC CITED: feature=fr-work-queue-agent-control kind=technical_doc id=https://modelcontextprotocol.io/specification/2025-06-18/basic/index verified_at=2026-06-02]
