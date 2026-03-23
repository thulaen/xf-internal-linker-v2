# PROMPTS.md

<!--
Paste-ready prompt pack for Codex, Claude Code, and Google Antigravity.

Usage rules:
- assume the AI tool is already opened inside the correct repository/workspace
- do not include filesystem paths unless the tool needs them
- every new thread should read `AI-CONTEXT.md` first
- prefer one narrow slice per session
- prefer safe automatic commit/push when possible
- use the Decision-First prompt unless the user explicitly says to proceed
-->

## Global Rules

```text
Assume you are already in the correct repository/workspace.

Before doing any work:
1. Read `AI-CONTEXT.md` first.
2. Read `PROMPTS.md`.
3. Read the master plan (`docs/v2-master-plan.md`) when needed for the current task.
4. Inspect the current repo state.

Project rules:
- GUI-first after setup
- Django + DRF backend, Angular frontend
- PostgreSQL + pgvector for all data
- Redis for cache, Celery broker, WebSocket channel layer
- Celery for all background tasks
- WebSockets for real-time (no HTTP polling)
- Docker Compose for deployment
- read-only access to XenForo and WordPress APIs
- destination = title + distilled body text
- host = sentence-level body text within first 600 words
- max 3 links per host thread
- one small slice per session unless I explicitly widen scope
- update `AI-CONTEXT.md` before stopping

Git rules:
- if Git is safe, pull latest at start when appropriate
- at session end, stage only intended files
- commit with a descriptive message
- push automatically when the session is clean and safe
- if Git is unsafe, explain why instead of pushing blindly
```

## Which AI To Use When

- **Codex:** backend wiring, Django models, serializers, views, Celery tasks, pipeline services, tests, bug fixes.
- **Claude Code:** architecture review, risk validation, performance skepticism, refactor judgment, strict review before/after risky changes.
- **Google Antigravity:** Angular components, Material UI, layout, visual behavior, empty/loading/error states, theme customizer, D3 visualizations.
- Stay in Codex by default.
- Do not switch to Google Antigravity when the backend contract (API shape, serializers) is still unsettled.
- Use Claude Code as a review gate before broad refactors, risky migrations, or phase-complete claims.

## Decision-First Prompt

```text
Read `AI-CONTEXT.md` and inspect the current repo before coding.

Then report:
1. the current phase
2. whether the repo is on-plan, behind, ahead, or drifting
3. the best AI/tool for the next task
4. 2 to 4 sensible next-task options
5. one recommended option
6. a short implementation suggestion for that option

Do not start coding until I confirm, unless I explicitly say to proceed.
```

## Codex New Thread Prompt

```text
Read `AI-CONTEXT.md` first, then inspect the repo and continue the XF Internal Linker V2 project.

Before writing code:
1. summarize the current phase
2. summarize what appears complete
3. identify the next smallest high-value slice
4. list the exact files you expect to touch
5. note blockers or architecture conflicts

Then implement exactly one narrow slice.

Rules:
- preserve the architecture and guardrails in `AI-CONTEXT.md`
- keep scope narrow
- do not refactor unrelated areas
- heavy work belongs in Celery tasks, not request handlers
- update `AI-CONTEXT.md` before stopping
- if Git is safe, stage intended files, commit, and push automatically
```

## Claude Code New Thread Prompt

```text
Read `AI-CONTEXT.md` first, then inspect the current repo state.

Act primarily as an architecture/risk/review tool for the XF Internal Linker V2 project.

Report:
1. current phase and whether the repo is on-plan, behind, ahead, or drifting
2. the highest-risk assumptions in the current slice
3. bugs, architecture conflicts, regression risks, missing tests, and weak contracts
4. the most defensible next step

If asked to review code, prioritize findings first and keep summaries short.
Do not widen scope into speculative redesign unless the current plan is actually unsound.
```

## Google Antigravity New Thread Prompt

```text
Read `AI-CONTEXT.md` first, then inspect the current repo state.

Work on the XF Internal Linker V2 project only within established API contracts.

Focus on:
- Angular components and Material UI
- Dashboard, settings, review workflow UX
- Theme customizer and appearance
- D3.js visualizations (link graph, heatmaps)
- Strong empty/loading/error states
- Focus Mode and keyboard shortcuts

Rules:
- use the existing Django REST API contracts
- do not invent backend endpoints without calling them out clearly
- keep the UI GUI-first, practical, and review-oriented
- do not switch into backend refactors unless explicitly asked
```

## Error Checking Prompt

```text
Read `AI-CONTEXT.md` first, then inspect the current repo state.

Check for:
1. Python errors: run `python manage.py check --deploy`
2. Migration issues: run `python manage.py showmigrations`
3. TypeScript errors: run `ng build --configuration=production`
4. Test failures: run `pytest` and `ng test --no-watch`
5. Dependency conflicts: check requirements.txt and package.json
6. Docker health: verify all services are running

Report all errors with file references and suggested fixes.
Do not fix anything until I confirm.
```

## Update/Upgrade Prompt

```text
Read `AI-CONTEXT.md` first, then inspect the current repo state.

Check for:
1. Outdated Python packages: pip list --outdated
2. Outdated npm packages: npm outdated
3. Django security advisories
4. Angular version updates

For each update:
- State the current version and available version
- Assess risk level (safe / moderate / risky)
- Recommend whether to update now or defer

Do not update anything until I confirm.
```

## New Feature Request Prompt

```text
Read `AI-CONTEXT.md` first, then inspect the current repo state.

I want to add: [describe feature]

Before coding:
1. Identify which Django apps this touches
2. Identify which Angular components this touches
3. List new models, serializers, views needed
4. List new Angular components, services needed
5. Assess impact on existing features
6. Estimate effort (small / medium / large)
7. Suggest the smallest first slice

Do not code until I confirm the plan.
```

## Universal Bounce / Resume Prompt

```text
Read `AI-CONTEXT.md` first, inspect the current repo state, and resume from the latest completed slice.

Then report:
1. current phase
2. whether the repo is on-plan, behind, ahead, or drifting
3. what the previous tool appears to have completed
4. the next exact slice
5. expected files to touch
6. blockers or risks

Then continue with one narrow slice only.
```

## One-Slice Implementation Prompt

```text
Implement exactly one slice only.

Before coding:
- restate the slice in one sentence
- list the files you expect to touch
- state what is intentionally out of scope

During implementation:
- preserve current architecture and guardrails
- do not widen into cleanup/refactor work
- add docstrings to public functions
- add type hints to all function signatures
- write tests for new functionality

At the end:
- summarize what changed
- list files changed
- summarize verification
- name the next exact slice
- update `AI-CONTEXT.md`
- if Git is safe, commit and push automatically
```

## Session Close-Out Prompt

```text
Before ending the session:
1. update `AI-CONTEXT.md`
2. summarize exactly what changed
3. list files changed
4. summarize verification performed
5. note shortcuts, blockers, or unresolved risks
6. name the next exact slice
7. if Git is safe, stage intended files, commit, push
8. if Git is not safe, explain why and list what should be staged
```

## Security Check Prompt

```text
Read `AI-CONTEXT.md` first, then inspect the current repo state.

Perform a security-focused review:
1. Django settings (DEBUG, SECRET_KEY, ALLOWED_HOSTS)
2. API authentication and permissions
3. CORS configuration
4. SQL injection (even with ORM, check raw queries)
5. XSS prevention in Angular templates
6. Secrets in code or git history
7. Docker security (exposed ports, default passwords)
8. Celery task input validation
9. WebSocket authentication
10. File upload/path traversal risks

Present findings ordered by severity with concrete file references.
```

## Architecture Guardrail Prompt

```text
Before implementing anything substantial, check the planned work against the project guardrails.

Explicitly confirm:
- GUI-first after setup
- Django + DRF backend, Angular frontend
- PostgreSQL + pgvector for all data
- Celery for background tasks (not inline)
- WebSockets for real-time (not polling)
- Read-only API access to XenForo and WordPress
- destination = title + distilled body text
- host = sentence-level within first 600 words
- max 3 links per host
- safe automatic commit/push when possible

If the proposed work conflicts with any guardrail, stop and explain the conflict before coding.
```

## Practical Prompting Rules

- Ask for one exact slice at a time.
- Name the files you expect the AI to touch before coding.
- Tell the AI whether to stop for confirmation or proceed immediately.
- Use Claude Code when you want judgment, skepticism, or strict review.
- Use Google Antigravity when the API contract is stable and the task is mainly visual/UX.
- Use Codex when the work is primarily implementation, logic, models, or tests.
- Re-anchor every new thread by reading `AI-CONTEXT.md` first.
- If a prompt starts drifting broad, reset it with the Scope Reset prompt.
- If a session ends midstream, restart with the Universal Bounce / Resume prompt.
```
