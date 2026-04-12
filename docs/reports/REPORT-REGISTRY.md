# Report Registry

This file is the single index of all audit reports and individual issues found by AI sessions. Every AI must read this file before starting work (see Session Gate in `AI-CONTEXT.md`).

## Rules

**Blocker Rule:** Any AI whose work area overlaps with an `OPEN` finding must tell the user in chat before writing any code, and must then either resolve it or explicitly justify in writing (in the Current Session Note in `AI-CONTEXT.md`) why it is skipping it.

**Silence Is Forbidden Rule:** If an AI notices an open or reopened finding that overlaps with the area it is about to touch, it must not stay silent. It must tell the user in chat first. Silent continuation is a policy violation.

**Anti-Duplication Rule:** Before logging a new issue, search this file for existing entries. If the issue is already logged, add a note to the existing entry instead of creating a duplicate.

**Anti-Regression Rule:** Before changing code in any area, search the Resolved sections below for entries that touch the same files. If a match exists, read what was fixed and verify your changes don't undo it. Resolved entries are permanent history — never delete them.

**Recurrence Rule:** If a new feature or change re-introduces a previously resolved issue (same root cause, same affected area), reopen the original entry by moving it back to the Open section with a note explaining what brought it back. Do not create a duplicate.

**Logging Rule:** If you find any bug, performance bottleneck, logic flaw, missing validation, or code smell during your session — even if it's outside your current task scope — add it here. Don't ignore it. Future AIs will see it and can fix it.

---

## Open Reports

### RPT-001 — Research-Backed Business Logic Audit (2026-04-11)

- **Status:** OPEN (5 of 5 findings unresolved)
- **Report file:** [`repo-business-logic-audit-2026-04-11.md`](repo-business-logic-audit-2026-04-11.md)
- **Scope:** Import, ranking, reranking, attribution, and weight auto-tuning logic
- **Summary:** Five logic-quality gaps in shipped code paths. All fixable by extending existing FR-013, FR-017, and FR-018 implementations in place.

| # | Finding | Severity | Affected files | Status |
|---|---------|----------|----------------|--------|
| 1 | C# import lane hardcoded 5-page cap creates silent corpus bias | high | `PipelineServices.cs` | OPEN |
| 2 | Feedback reranker's inverse-propensity claim unsupported by stored signal granularity | high | `feedback_rerank.py`, `models.py` | OPEN |
| 3 | C++ fast path and Python reference path compute different math in feedback reranker | critical | `feedrerank.cpp`, `feedback_rerank.py` | OPEN |
| 4 | Attribution mixes two incompatible counterfactual models | high | `impact_engine.py`, `GSCAttributionService.cs` | OPEN |
| 5 | Auto-tuning optimizes a 4-number global summary instead of ranking quality | medium | `WeightObjectiveFunction.cs`, `WeightTunerService.cs` | OPEN |

---

## Open Individual Issues

### ISS-003 â€” FAISS startup index build hits the database during app initialization (2026-04-12)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/apps/pipeline/apps.py`, `backend/apps/pipeline/services/faiss_index.py`
- **Description:** Docker-side `showmigrations` and `makemigrations --check` emit Django's `APPS_NOT_READY_WARNING_MSG` because `PipelineConfig.ready()` calls `build_faiss_index()` during startup, which touches the database before app initialization is complete. This makes management-command startup noisy and risks future initialization fragility.
- **Status:** OPEN
- **Regression watch:** Keep FAISS index building out of `AppConfig.ready()` for management commands and other startup paths that should remain side-effect free.

---

## Resolved Reports

_(None yet. When all findings in a report are resolved, move the report entry here with resolution dates.)_

---

## Resolved Individual Issues

### ISS-001 â€” Backend container could miss required `drf_spectacular` dependency and fail at startup (2026-04-12)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/config/settings/base.py`, `backend/config/urls.py`, `backend/Dockerfile`, `docker-compose.yml`, `scripts/setup-dev.ps1`
- **Description:** The backend relied on `drf_spectacular` at runtime, but the running Docker container and some local setups could still start from a partially provisioned environment where that package was absent. This produced a confusing late failure during Django startup instead of a clear dependency-install failure.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-12
- **Regression watch:** Keep `drf_spectacular` required in Django settings and preserve the explicit import checks in Docker build/startup and local setup flows.

### ISS-002 â€” Local SQLite test database could drift behind migrations (2026-04-12)

- **Found by:** Codex
- **Severity:** medium
- **Affected files:** `backend/apps/plugins/apps.py`, `backend/apps/plugins/tests.py`, `scripts/setup-dev.ps1`
- **Description:** Local verification under `config.settings.test` could start against an incomplete `backend/test.sqlite3`, which made migration checks noisy and fragile. Plugin startup also needed to stay out of the way for test-settings and migration-oriented management commands.
- **Status:** RESOLVED
- **Resolved:** 2026-04-12
- **Fixed in:** Codex session note in `AI-CONTEXT.md` dated 2026-04-12
- **Regression watch:** Keep the plugin autoload skip for `.test` settings plus migration commands, and keep `scripts/setup-dev.ps1` running `migrate --settings=config.settings.test --noinput`.

---

## Templates

### New Report Entry

```markdown
### RPT-XXX — [Title] (YYYY-MM-DD)

- **Status:** OPEN (N of N findings unresolved)
- **Report file:** [`filename.md`](filename.md)
- **Scope:** [What code areas were audited]
- **Summary:** [One-line summary of key findings]

| # | Finding | Severity | Affected files | Status |
|---|---------|----------|----------------|--------|
| 1 | [description] | critical/high/medium/low | `file.py` | OPEN |
```

### New Individual Issue Entry

```markdown
### ISS-XXX — [Short description] (YYYY-MM-DD)

- **Found by:** [AI tool name, e.g. Claude / Codex / Gemini]
- **Severity:** critical / high / medium / low
- **Affected files:** `path/to/file.py`
- **Description:** [What the issue is and why it matters]
- **Status:** OPEN

_(When resolved, add:)_
- **Resolved:** YYYY-MM-DD
- **Fixed in:** [commit hash or session reference]
- **Regression watch:** [What to check if this area is changed again]
```
