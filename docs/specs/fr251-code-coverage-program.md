---
id: FR-251
title: Code-Coverage Program — strict per-task targets + 10-per-session drain
status: ACTIVE (rules in place 2026-05-12; backlog drained per session)
owner: Every AI agent (Claude / Codex / Antigravity / future)
priority: PARAMOUNT
created: 2026-05-12
---

# FR-251 — Code-Coverage Program

[SPEC FRESHNESS: reviewed_at=2026-06-03 next_review=2026-09-03]

[SPEC CITED: feature=FR-251 kind=technical_literature id=beck-tdd-2002 verified_at=2026-06-03]
[SPEC CITED: feature=FR-251 kind=technical_literature id=crispin-gregory-agile-testing-2009 verified_at=2026-06-03]

## Why this FR exists

Test suites that say "all green" but actually only exercise one of three branches are lying to you. The project has lots of business logic — scoring, ranking, parsing, state machines, idempotency — where a missed branch becomes a real bug in production. FR-251 establishes a strict, future-aware coverage program that:

1. Sets per-task coverage targets so agents know what "done" looks like.
2. Lists the Level A areas requiring MC/DC (Modified Condition / Decision Coverage) + property tests + mutation testing + golden fixtures + E2E.
3. Establishes a 10-per-session coverage-gap drain alongside the 30-pick auto-issue ritual (3 per source × 10 sources after the 2026-05-12 source extension).
4. Adds a `[COVERAGE SUMMARY: ...]` marker at the end of every slice / task / session so progress is visible and honesty is mandatory.

This FR is **rules-only**. The work to actually achieve the coverage lives in the AutoIssue backlog created in the same PR (one issue per Level A area + per-language target + per macro-rule group). See `AI-CODING-GUIDELINES.md` and `docs/CODE-COVERAGE-RULES.md` for the full text of the rules; this spec is the change-control wrapper.

## Citations

- **NASA NPR 7150.2D "Software Engineering Requirements"** — defines MC/DC as the strictest structural coverage tier; required for Class A safety-critical software at NASA. We borrow the language for our Level A.
- **DO-178C (avionics)** — Table A-7 maps MC/DC to Level A software. Used as the industry reference for what "MC/DC" means in practice.
- **"Mutation Testing Advances: An Analysis and Survey", Jia & Harman 2011** — the canonical academic source for mutation testing as a proxy for test-suite strength.
- **"Property-based testing in Python with Hypothesis", MacIver 2013** — the Hypothesis library this project uses for property tests.
- **Pact OSS contract-testing protocol** — for the external-integration contract-test rule.

The above are all real, inspectable sources. Each was opened before being cited. None of the project's own code mocks or imitates these papers without attribution.

## Locked decisions (2026-05-12)

| Decision | Locked answer |
|---|---|
| Backlog granularity | **One AutoIssue per area** (~25 total). Each AutoIssue's description enumerates the sub-rules from the brief. |
| Ritual enforcement | **Separate marker line** `[COVERAGE GAPS READ: 10 picked — ...]` validated by `.githooks/check-registry-read.py`. Mirrors the Phase-7 `[CI FAILED RUNS READ: ...]` pattern. |
| Drain rate | **10 coverage-gap AutoIssues per session**, in addition to the standard 30-pick + 10 latest failed CI runs. |
| Drought clause | Same shape as the 30-pick drought clause: file new AutoIssues for missing Level A areas; use the substitution form `<K> picked + <10-K> filed`. |
| End-of-slice marker | `[COVERAGE SUMMARY: target=<X>% actual=<Y>% — met / not met — <reason if not met>]`. |
| Per-language floors | Backend 90% line + 85% branch; Celery 90%; API 90%; Angular components+services 75%; C++ 100% branch. |

## Per-task coverage target table

(Authoritative copy in `AI-CODING-GUIDELINES.md` — this is a cross-link for spec readers.)

| Surface | Level | Target |
|---|---|---|
| Backend services | A | 90% line + 85% branch |
| API endpoints | A | 90% line + 85% branch |
| Celery tasks | A | 90% line + 85% branch |
| C++ extensions | A (MC/DC) | 100% branch |
| Angular components | B | 75% line + 60% branch |
| Angular services | B | 75% line + 60% branch |
| Critical review-page workflows | A + E2E | 90% + Playwright spec |
| External integrations | A + Contract | 90% + Pact spec + 1 integration smoke |
| Migrations | C | Forward + reverse smoke |
| Docs / config / scaffolding | D | Manual review |

## Level A area inventory (~14 areas, each = 1 AutoIssue)

The 14 Level A areas from `docs/CODE-COVERAGE-RULES.md` each map to one open AutoIssue in the backlog created by this PR. Drainage of those issues + the 4 per-language target AutoIssues + 5 macro-rule-group AutoIssues (state transitions, Celery idempotency, scoring, sentence splitting, text cleaning) = **~23 AutoIssues** total seeding the backlog.

## How the program runs (the steady state)

1. **At session start:** agent reads `AI-CODING-GUIDELINES.md` + `docs/CODE-COVERAGE-RULES.md`, emits the `[GUIDELINES READ: ...]` marker.
2. **Still at session start:** agent runs `print_open_issues`, which (extended in this PR) emits `[COVERAGE GAPS READ: 10 picked — ...]`.
3. **Picks the right target** for whatever the user asked: looks up the touched files in the per-task table.
4. **Drains the 10 coverage gaps** as the first work of the session (alongside the 30 auto-issues and the 10 latest failed CI runs).
5. **Does the user's task**, meeting the right coverage target.
6. **Ends every slice / task / session with `[COVERAGE SUMMARY: ...]`** — honest met / not-met + reason if not met.

## Drought handling

If fewer than 10 coverage-gap AutoIssues are open at session start:

1. Agent reads the Level A area list in `docs/CODE-COVERAGE-RULES.md`.
2. Identifies areas without an open AutoIssue.
3. Files new `AutoIssue(source='agent', kind='coverage-gap', level='A', area='<area>', priority_score=0.5)` rows for missing areas.
4. Picks 10 total (some pre-existing + some newly filed).
5. Uses the marker substitution form `[COVERAGE GAPS READ: <K> picked + <10-K> filed — #..., (drought logged: #<id>)]`.

## Future-aware design

This FR is intentionally **language-agnostic and toolchain-agnostic** at the policy layer:

- Adding Go services (Phase 8 scaffold already in place at `services/go/`): just add a "Go services" row to the per-task table at the next floor-raising PR.
- Replacing FAISS or BGE-M3: Level A "Index build/search behavior" already covers it.
- Adding a new external integration: the "External integrations" row already enforces Pact + smoke.
- Splitting backend monolith into microservices: each service inherits the Level A rule.

The rules describe the **intent** (high confidence the tests test the right thing), so swap-outs of the underlying tooling don't change the policy.

## Status

- [x] Rules document: `docs/CODE-COVERAGE-RULES.md`
- [x] Guidelines document: `AI-CODING-GUIDELINES.md`
- [x] PARAMOUNT rule in `CLAUDE.md` + `AGENTS.md`
- [x] AI-CONTEXT section
- [x] FEATURE-REQUESTS entry
- [x] FR-251 spec (this file)
- [x] ROADMAP entry
- [x] Opening ritual extension (`print_open_issues` + `check-registry-read.py`)
- [x] AutoIssue backlog seeded
- [x] Glossary entries
- [ ] **Drain begins next session** — pick 10 coverage-gap AutoIssues per session.

## Plain-English wrap-up

This FR doesn't write any tests. It writes the **rule book** for how tests are written and how completeness is measured. The actual coverage work happens session by session: every agent picks 10 issues from the backlog, fixes them, summarises whether the target was met, and moves on. Over weeks, the backlog drains and the per-language floors raise.
