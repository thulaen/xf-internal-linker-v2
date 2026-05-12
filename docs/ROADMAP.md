# Roadmap — XF Internal Linker V2

Multi-phase plan for raising the project's quality floor. Updated when new programs land or milestones complete. This file is the place to look when a session asks "what's the next big-picture goal?"

## Active programs

### Test-Hardening — 8 phases (2026-05-12)

**Status:** Phases 1-8 SHIPPED on `master`. Plan: `~/.claude/plans/please-review-the-codebase-ancient-starfish.md`.

| Phase | What lands | Status |
|---|---|---|
| 1 | Random-order tests across Python / Angular / C++ / Playwright | SHIPPED |
| 2 | Pre-commit fast band + hardware-aware MAX_JOBS caps | SHIPPED |
| 3 | Ruff `select=["ALL"]` + Clang-Tidy WarningsAsErrors curated | SHIPPED |
| 4a | mutmut + Stryker + Mull (mutation testing) | SHIPPED (Mull advisory) |
| 4b | libFuzzer (3 starter targets + 60s smoke) | SHIPPED |
| 4c | MemorySanitizer (project-only blacklist) | SHIPPED |
| 4d | Pre-push heavy band wiring | SHIPPED |
| 5 | Super-Linter + Pact contract scaffold | SHIPPED |
| 6 | 5 new AutoIssue pickers (mutation/fuzz/lint_error/contract/gh_ci) | SHIPPED |
| 7 | Opening ritual extension + Auto-Iterate PARAMOUNT rule | SHIPPED |
| 8 | Go scaffold + CI-Gates inventory | SHIPPED |

### FR-251 — Code-Coverage Program (2026-05-12)

**Status:** Rules + AutoIssue backlog SHIPPED 2026-05-12. Drain begins next session.

| Milestone | What it means | Status |
|---|---|---|
| **M0** — Rules in place | `docs/CODE-COVERAGE-RULES.md` + `AI-CODING-GUIDELINES.md` + PARAMOUNT links | SHIPPED |
| **M1** — Backlog seeded | ~23 AutoIssues filed (14 Level A areas + 4 per-language targets + 5 macro-rule groups) | SHIPPED |
| **M2** — Ritual gates | `[COVERAGE GAPS READ: 10 picked]` enforced by pre-commit hook | SHIPPED |
| **M3** — First per-language ratchet | Backend `--cov-fail-under` raised from 68 → 75 | PENDING — after the first 50 coverage AutoIssues drain |
| **M4** — Stryker mutation score ≥ 60% on scope module | Angular `a11y-prefs.service.ts` first; expand per ratchet | PENDING |
| **M5** — mutmut mutation score ≥ 60% on scope module | Python `fingerprinting.py` first; expand per ratchet | PENDING |
| **M6** — Mull mutation gate FLIPS from advisory to blocking | Requires Mull-compatible Clang in CI runner | PENDING |
| **M7** — libFuzzer coverage-gap detection live | Picker emits `kind=fuzz-coverage-gap` rows for every public C++ API without a fuzz target | PENDING |
| **M8** — Backend floor → 90% | Per-task table is the contract; this is the project-wide ratchet target | LONG-TERM |
| **M9** — Angular floor → 75% | Same shape; component-level ratchet | LONG-TERM |
| **M10** — C++ 100% branch + Mull ≥ 70% | Level A C++ contract met | LONG-TERM |

### Cleanup sweeps (parallel)

| Sweep | Source | Status |
|---|---|---|
| Ruff strict ignore-list shrink | AutoIssue #162 + per-rule-family AutoIssues filed in this PR | OPEN — drain per session |
| Coverage backlog | The ~23 AutoIssues created in this PR | OPEN — drain 10/session |

## Recently shipped

### 2026-05-11 — Faro + Tempo deployment + 18-pick ritual

Grafana Faro (frontend RUM) + Tempo (distributed traces) deployed alongside the existing Sentry → GlitchTip pipeline (fan-out, not substitution). Opening ritual raised from 12 picks across 4 sources to 18 picks across 6 sources. See `docs/reports/REPORT-REGISTRY.md` RPT-007.

### 2026-05-10 — Prevention Sweep (RPT-006)

4 new pre-commit hooks landed (file-size cap, no-downgraded-gates, frontend-routes, missing-tests). 5 warning-only CI gates hardened to blocking. See `docs/reports/REPORT-REGISTRY.md` RPT-006.

## How to read this file

- "**SHIPPED**" means landed on master with tests.
- "**PENDING**" means in active work, with an owner and a target session.
- "**LONG-TERM**" means in the program but no specific target session yet.

Update this file whenever a milestone flips status or a new program starts.
