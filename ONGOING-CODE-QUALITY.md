# ONGOING-CODE-QUALITY.md — Single Source of Truth for "Fix As You Go"

**Status:** PARAMOUNT. Every AI agent (Claude, Codex, Gemini, Antigravity, every future agent) reads this file before any task. The rules apply continuously — every session, every file touched, every task.

This file consolidates what AGENTS.md called the "Code Quality Mandate" plus two new explicit rules the user surfaced on 2026-05-09:

- The "fix N before task" count has been raised from **2 → 3**.
- "Severe finds go to BOTH the AutoIssue table AND the Report Registry" (no more either/or).

---

## 1. Read auto-issues + Report Registry BEFORE writing any code

This is enforced by the ABSOLUTE rule in [`CLAUDE.md`](CLAUDE.md), [`AGENTS.md`](AGENTS.md), [`CODEX.md`](CODEX.md), [`GEMINI.md`](GEMINI.md). Same wording in all four. Quick summary:

1. After the `[HANDOFF READ: ...]` line, run `docker compose exec -T backend python manage.py print_open_issues` AND skim the Open sections of [`docs/reports/REPORT-REGISTRY.md`](docs/reports/REPORT-REGISTRY.md).
2. Your second response line MUST be: `[REGISTRY READ: <N> open auto-issues, <M> open registry findings — picked: #<id1>, #<id2>, #<id3>]` — **three** picked items, not two.
3. **BEFORE writing the FIRST line of code in any file**, run `docker compose exec -T backend python manage.py search_resolved_issues --area <repo-relative-path>` for each touched directory. If matches exist, your response MUST include `[RESOLVED HISTORY: <N> prior fix(es) read in <area>]`.
4. Pre-commit hook [`.githooks/check-registry-read.py`](.githooks/check-registry-read.py) blocks AGENT-HANDOFF.md commits without the marker. The regex requires three picked IDs.

---

## 2. Fix THREE auto-issues (or three real bugs in user's task) BEFORE any new task

The user raised the count from 2 to 3 on 2026-05-09. Why: two-per-session was too lenient — the open-issues queue was growing faster than agents were closing it.

- Pick by `priority_score` desc within whatever overlaps your work area.
- If none overlap, pick the three highest-`priority_score` rows globally.
- **If the user's task is itself a bug fix, or three issues are explicitly listed, that satisfies the auto-fix-3 rule** — you don't have to fix three additional unrelated things on top.

---

## 3. Fix as you go — long functions, duplication, messy code, minor bugs

Every file you touch must come out **better** than it went in. The hard limits are still those of [`THINK-BEFORE-YOU-CODE.md`](THINK-BEFORE-YOU-CODE.md):

- ≤50 lines per function — if you touch a function over 50 lines, split it. Extract sub-steps into well-named helpers.
- ≤1500 lines per file — if you touch a file over 1500 lines, file an AutoIssue and a Registry entry; if your task already fits inside it, finish the task first then split.
- ≤10 cyclomatic complexity per function.
- ≤7 args per function.
- ≤4 nesting levels.
- **No duplicated 6+-line blocks.** If you see the same logic in two places before adding a third copy, extract it now.

Other "as you go" rules:

- **Surface silent errors.** A `try / except / pass` (or one that just logs and continues) is a bug. Replace it with a specific exception type, a real log entry, and — where appropriate — a re-raise.
- **Prevent crashes.** Guard against `None` / `null` / out-of-bounds / missing keys / unvalidated external data at every system boundary. Internal code may trust itself; external data never can.
- **Don't defer.** Address all issues you find in the area you are working in. Do not leave a `TODO: fix later` and move on. If the fix is genuinely out of scope, file the entry (see Rule 4) — but the bar for "out of scope" is high.
- **Write tests.** Every new service, utility function, or view needs at least one `SimpleTestCase` (or `TestCase`) covering the happy path and the primary failure mode. No feature is done without tests.
- **Performance is correctness.** Slow hot-path code is a bug, not a deferred concern. >2× slower than expected = MEDIUM in the Registry; >5× = HIGH; incorrect-result optimisation = CRITICAL.

---

## 4. Severe finds: BOTH AutoIssue AND Report Registry — no exceptions

When you find a real bug, performance bottleneck, missing validation, or code smell during the session — even outside scope — log it in BOTH places in the same change:

1. **AutoIssue row** with `source='agent'`, the right `severity`, and a fingerprint that will dedup on recurrence (use `apps.auto_issues.services.dedup.upsert_dedup`). The AutoIssue is the machine-readable, agent-pickable surface.
2. **Report Registry entry** in [`docs/reports/REPORT-REGISTRY.md`](docs/reports/REPORT-REGISTRY.md) — the human-readable, narrative surface. Goes in the Open Reports or Open Individual Issues section, with the standard fields (Found by / Severity / Affected files / Description / Status).

This used to be ambiguous — some agents logged only one, some only the other. Both are needed: the AutoIssue feeds auto-fix-3; the Registry preserves narrative context that doesn't fit a JSON field.

If you cannot fix the issue in this session (truly out of scope, large refactor, requires user decision), file BOTH entries and leave them OPEN — the next session picks them up.

---

## 5. When YOU resolve an issue: populate `lessons_learned`

Every resolved AutoIssue MUST have `lessons_learned` populated with two parts:

1. **The trap** — what's NOT obvious about this code area? What did you almost get wrong?
2. **The fix shape** — what worked? Be concrete (function names, line ranges, the specific change).

Empty `lessons_learned` on a resolved row is a protocol violation — the next agent loses the lesson. The boot-time `search_resolved_issues --area <path>` command surfaces this field for the next agent, so it must be present.

The same applies to the Registry: when you resolve an entry, write a "closure" paragraph explaining the trap and the fix shape (not just "fixed in commit XXX"). See RPT-001 finding 3 closure for the canonical shape.

---

## 6. Refactor for performance in the same diff (KISS)

When you fix an issue:

- Apply DRY (don't repeat yourself) — reuse existing logic; if the function you're modifying duplicates logic nearby, fold them together while you're there.
- Apply KISS (keep it simple) — write the simplest thing that works; add abstraction only when a second real use case appears.
- Refactor for performance opportunistically — if the touched code path is provably slow, fix it. Don't write a separate "performance pass" later.

---

## 7. Performance-mandated patterns

These come from the existing PARAMOUNT files but are repeated here because they apply to **every** session:

- **C++ first for hot paths.** [`CPP-FIRST.md`](CPP-FIRST.md) — if a C++ extension exists for the operation, call it. Python is fallback and reference only.
- **Hardware-aware defaults.** [`HARDWARE-PROFILES.md`](HARDWARE-PROFILES.md) — never hardcode batch sizes, parallelism, or FAISS configuration; read from `apps/pipeline/services/hardware_profile.py`.
- **Disk-pressure circuit breaker.** [`DISK-PRESSURE-RULES.md`](DISK-PRESSURE-RULES.md) — pre-flight large writes via `apps/pipeline/services/disk_pressure.require_free_disk()`.
- **No-duplicates rule.** [`NO-DUPLICATES.md`](NO-DUPLICATES.md) — every per-content table follows the `(content_hash, signal_version)` skip-if-unchanged + supersede + retention pattern.
- **Default-on rule.** [`DEFAULT-ON-RULE.md`](DEFAULT-ON-RULE.md) — every new feature / weight / signal / algorithm defaults ON with a non-zero starting value.
- **Citations on every default.** [`CITATION-RULE.md`](CITATION-RULE.md) — every default value has ≥1 specific citation (DOI / patent / RFC / stable URL).
- **Glossary update.** [`GLOSSARY-RULE.md`](GLOSSARY-RULE.md) — every new acronym needs a one-line plain-English entry in the glossary.

---

## 8. Tech-debt delta — required in every handoff

Every AGENT-HANDOFF.md entry must include a `Tech-debt delta:` line counting at least 5 debt items resolved that session ([`TECH-DEBT-MANDATE.md`](TECH-DEBT-MANDATE.md)). Sessions without one fail the handoff protocol.

A "debt item" can be: a fixed long function, a removed duplication, a corrected silent-error swallow, a new test where there was none, a deleted dead file, an i18n string tagged, a `print()` converted to `logger.*`, a missing benchmark added, etc.

---

## 9. Never do (cross-cutting)

- Do not refactor code outside the scope of the current task without explicit approval.
- Do not silently change behaviour while "cleaning up" — correctness always comes first.
- Do not introduce new abstractions, helpers, or utilities for a one-time use case.
- Do not skip hooks (`--no-verify`) unless the user explicitly asks for it. Hook failures mean fix the underlying issue.
- Do not commit without verifying — `scripts/lint-all.ps1` (frontend) + `python manage.py test` (backend) before pushing.

---

## Why this file exists

Before 2026-05-09 these rules lived inline inside AGENTS.md. Three problems:

1. CLAUDE.md / CODEX.md / GEMINI.md only had a "follow the Code Quality Mandate in AGENTS.md" pointer — agents that opened the wrong file first never read the actual rules.
2. The "fix 2 before task" count was set when the open-issue queue was small. With Pyroscope + GlitchTip + the internal picker now feeding it, 2 wasn't keeping up.
3. The "report severe to BOTH AutoIssue AND Registry" rule was implied but not stated. Some agents picked one, some the other; the Registry-only ones missed auto-fix-3 pickup, the AutoIssue-only ones missed the narrative context.

This file solves all three by being one shared file every agent loads, with explicit, current numbers.
