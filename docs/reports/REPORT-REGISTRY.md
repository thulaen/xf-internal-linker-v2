# Report Registry

This file is the single index of all audit reports and individual issues found by AI sessions. Every AI must read this file before starting work (see Session Gate in `AI-CONTEXT.md`).

## Rules

**Blocker Rule:** Any AI whose work area overlaps with an `OPEN` finding must either resolve it or explicitly justify in writing (in the Current Session Note in `AI-CONTEXT.md`) why it is skipping it — before writing any code.

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

_(None logged yet. Use the template below to add issues found during AI sessions.)_

---

## Resolved Reports

_(None yet. When all findings in a report are resolved, move the report entry here with resolution dates.)_

---

## Resolved Individual Issues

_(None yet. Resolved issues stay here permanently to prevent regressions and duplication.)_

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
