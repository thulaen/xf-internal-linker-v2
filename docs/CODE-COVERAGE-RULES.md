# Code-Coverage Rules — XF Internal Linker V2

**Status:** PARAMOUNT, ABSOLUTE. Read me alongside `AI-CODING-GUIDELINES.md` at every session start. Every agent — Claude Code, Codex, Antigravity, every future agent — applies the right target for the task at hand and meets it without exception. The session ends with `[COVERAGE SUMMARY: ...]`.

This file is the complete coverage contract for the project. It defines:

- The **coverage levels** (A / B / C / D) and what each one requires.
- The **per-language minimum targets** (backend 90%, API 90%, Celery 90%, Angular components/services 95% line + 85% branch + 95% mutation, C++ 100% branch + 100% mutation).
- The **Level A areas** that require MC/DC + property tests + golden fixtures + mutation testing.
- The **property-test invariant menus** for text cleaning, sentence splitting, scoring, idempotency, state transitions.
- The **drought clause** when fewer than 10 coverage-gap AutoIssues are open.

See `AI-CODING-GUIDELINES.md` for the per-task target table, the work-loop, and the coverage-summary marker.

---

## Coverage levels

### Level A — Modified Condition/Decision Coverage (MC/DC), strict

Level A is the project's strictest tier. Applies to anything that touches business logic, scoring, ranking, parsing, security, or financial decisions.

**Requirements:**

- **MC/DC coverage** — every condition in every Boolean decision is independently exercised showing it can affect the outcome.
- **100% line coverage** measured at PR time.
- **100% branch coverage** (not just line — every `if` / `else` / `match` arm exercised).
- **Property-based tests** for any function with combinatorial input space.
- **Mutation testing** — mutmut (Python) / Stryker (Angular) must achieve mutation score above the documented threshold (see `docs/MUTATION-TESTING.md`).
- **Golden-fixture regression tests** — snapshot the expected output for known representative inputs; any change to the snapshot is reviewed.
- **End-to-end review-workflow tests** (Playwright) for any code path that participates in a user-facing review or approval flow.
- **Traceability** — each test references the rule, FR, or invariant it enforces, by ID or by comment.

### Level B — Standard line + branch

For first-class code paths that don't yet warrant Level A.

- Line coverage at the documented per-language minimum.
- Branch coverage at the documented per-language minimum.
- Tests for happy path + invalid input + empty input + boundary values.
- Mutation testing is mandatory for configured code targets. Angular components and services require a 95% mutation score. Backend Python and C++ targets require a 100% mutation score.

### Level C — Smoke

For migrations, scripts, scaffolding, and configuration changes.

- One test that the change runs forward without raising.
- For migrations: one test that the migration is reversible (or an explicit irreversibility marker).
- No coverage floor at this level.

### Level D — Manual review

For docs, comments, config files, dotfiles, and other non-code artefacts. No automated coverage gate.

---

## Per-language minimum coverage targets

These are **floors**. The strictest target wins when a task touches multiple areas.

| Surface | Target |
|---|---|
| Backend services (`backend/apps/*/services/**`) | **90%** line + 85% branch |
| API endpoints (`backend/apps/api/`, `backend/apps/*/views*.py`) | **90%** line + 85% branch |
| Celery tasks (`backend/apps/*/tasks*.py`) | **90%** line + 85% branch |
| Backend domain modules (`backend/apps/*/models.py`, `backend/apps/*/services/dedup.py`, etc.) | **90%** line + 85% branch |
| C++ extensions (`backend/extensions/*.cpp`) | **100%** branch coverage + **100%** Mull mutation score |
| Angular components (`frontend/src/app/**/*.component.ts`) | **95%** line + 85% branch + **95%** Stryker mutation score |
| Angular services (`frontend/src/app/**/*.service.ts`) | **95%** line + 85% branch + **95%** Stryker mutation score |
| Critical review-page workflows | **90%** + at least 1 Playwright E2E spec |
| External integrations (GSC, GA4, Matomo, WP, XF, OpenAI, Gemini, webhooks) | **90%** + Pact contract + at least 1 integration smoke (mocked or sandboxed) |
| Go modules (`**/go.mod`) | **95%** line coverage + blocking Go mutation testing |

## Realistic commit policy

Normal commits use a ratchet. A ratchet means coverage may rise, but it may not fall.

- New Angular components and services must meet 95.0% line coverage, 85.0% branch coverage, and 95.0% mutation score.
- Changed Angular components and services must not reduce coverage. If they are below target, they must improve above the stored baseline in `.coverage-baseline.json`.
- New backend code must meet the full backend coverage and mutation target.
- Changed backend code must run mutation testing for the changed module or closest test target. If the installed tool cannot scope the run, the check fails and records evidence instead of silently running the wrong target.
- C++ and Go checks stay Docker-managed and mandatory for touched modules. New modules must meet the full target. Existing modules use the ratchet until they reach target.
- Full global coverage and mutation are quality-debt checks until the repo reaches the target. They create evidence and AutoIssues, but they do not block unrelated commits.

Backend currently means Python backend plus C++ backend extensions. It also includes Go modules once they are added.

The current per-language floor is enforced by:

- Backend: `--cov-fail-under=68` in `backend/pytest.ini` (ratchet; raises only).
- Frontend: `scripts/run-angular-quality.sh` reads the Karma coverage report, records full-app coverage as quality debt, and blocks only new or changed Angular component/service targets that violate the ratchet policy.
- C++: GoogleTest line/branch coverage is instrumented through Docker-managed coverage scripts and must fail below 100% branch coverage.
- Go: `go-quality` in `.github/workflows/ci.yml` and `.githooks/pre-push` run Go tests with `-coverprofile=cover.out`, fail below 95% total coverage, and run Go mutation testing when a Go module exists.

**The floor only goes up.** Lowering it without a documented incident is a protocol violation.

---

## Level A areas — full list

Every change touching one of these areas requires Level A: MC/DC + property-based tests + full branch coverage + mutation testing + golden-fixture regression + end-to-end review-workflow tests where applicable.

1. **Import normalization** — from XenForo, WordPress, sitemaps, crawls, webhooks.
2. **Text cleaning** — HTML stripping, quote removal, shortcode handling, forum markup handling.
3. **Sentence splitting** — including abbreviation handling, URL handling, decimal-number handling.
4. **Embedding job lifecycle + retry behavior** — including pausing, resuming, checkpoints.
5. **Index build + search behavior** — FAISS index lifecycle, candidate shortlisting.
6. **Scoring logic** — composite, semantic, hybrid retrieval, RRF.
7. **Meta-algorithm parameters** — RRF k, BM25 k1/b, MMR lambda, etc.
8. **All business logic** — the explicit, named domain rules in `backend/apps/*/services/`.
9. **Scoring algorithm** end-to-end — input → final ranked list.
10. **Near-duplicate removal** — semantic / hash-based / shingle-based.
11. **Existing-link detection** — at write time and read time.
12. **Broken-link detection** — scheduled and on-demand.
13. **Approval / rejection / manual-review state transitions** — every allowed and forbidden transition.
14. **Permissions on review and admin screens** — every gate, deny path, escalation.
15. **Analytics import correctness** from GSC, GA4, and Matomo.
16. **Celery idempotency** — repeated jobs must not corrupt data.
17. **Local database integrity and uniqueness rules** — every `unique=True` and every implicit invariant.

Each entry above maps to one or more AutoIssue(s) in the coverage-gap backlog (see [`docs/specs/fr251-code-coverage-program.md`](specs/fr251-code-coverage-program.md)).

---

## Property-test invariant menus

When implementing or reviewing the areas below, the property-test suite **must** include the listed invariants. Property tests live next to the unit tests (`backend/apps/.../tests_<area>_props.py` for Python; `frontend/.../<area>.props.spec.ts` for TypeScript).

### Text cleaning

- `clean(clean(x)) == clean(x)` — idempotent.
- `clean(x)` never returns invalid Unicode.
- Removing forum quotes does not remove the author's own content.
- HTML stripping preserves visible-text order.
- Shortcode removal does not join unrelated words.
- Cleaning preserves the count of newlines that bound paragraphs (no silent paragraph collapse).

### Sentence splitting

- Abbreviations (`Dr.`, `e.g.`, `i.e.`, `etc.`, `Mr.`, `Mrs.`) do not always create sentence breaks.
- URLs do not create bogus sentence breaks.
- Decimal numbers (`3.14`, `99.9%`) do not split sentences.
- Forum signatures (`-- Joe`, `~~ JaneDoe`) do not become linkable content.
- Very short fragments (≤ 3 chars) are filtered.
- Empty input yields an empty list (does not crash).

### Scoring

- Final score stays within the documented valid range (`[0, 1]` for normalised scores).
- Identical source and destination is rejected (no self-link).
- Already-linked destinations are penalised or removed.
- Near-duplicate destinations do not both survive.
- Higher semantic similarity does not reduce score unless another penalty applies.
- Blocked domains are never suggested.

### Approval state transitions

- `pending` → `approved` allowed.
- `pending` → `rejected` allowed.
- `pending` → `manual_review` allowed.
- `approved` → `pending` forbidden (no silent reversal).
- `rejected` → `approved` forbidden (no auto-approval without explicit user action).
- `manual_review` preserves reviewer notes.

### Celery idempotency

- Running the same import twice does not duplicate posts.
- Running the same embedding job twice does not duplicate embeddings.
- Retrying after a crash continues from the last checkpoint.
- Partial failure does not mark the whole pipeline complete.
- Cancelled jobs do not leave approved suggestions in an invalid state.

---

## Mutation-testing contract

Every Level A change must run mutation testing on the touched module. Backend Python uses mutmut and must reach 100%. Angular components and services use Stryker and must reach 95%. C++ extensions use Mull and must reach 100%. Surviving mutants are a non-zero exit.

Tooling reference: `docs/MUTATION-TESTING.md`. Missing tools, missing reports, tool crashes, and surviving mutants all fail the local hook and the GitHub check.

---

## Golden-fixture regression tests

Every Level A area maintains at least one **golden fixture file** under `backend/apps/<area>/tests_data/golden/` (or `frontend/.../tests_data/golden/`). Each fixture is a `(input, expected_output)` pair captured from a known representative call. Changes to the snapshot trigger explicit review.

When updating a golden fixture:

1. Inspect the diff visually.
2. Document why the change is intentional in the commit message.
3. If the change is a regression, **revert and fix the code** rather than the fixture.

---

## Coverage-gap AutoIssue backlog

Coverage gaps live in the AutoIssue table as `source='agent'`, metadata `{"kind": "coverage-gap", "level": "A/B/C", "area": "..."}`.

Drain rate: **10 per session** alongside the standard 30-pick quota (3 per source × 10 sources). Marker line in the opening ritual:

```
[COVERAGE GAPS READ: 10 picked — #163, #164, ...]
```

Enforced by `.githooks/check-registry-read.py` (extended in this PR).

**Drought clause:** if fewer than 10 coverage-gap AutoIssues are open at session start, the agent files new ones for missing Level A areas from the list above and uses the substitution form `[COVERAGE GAPS READ: <K> picked + <10-K> filed — #..., (drought logged: #<id>)]`.

---

## Coverage-summary marker (end of slice / task / session)

After every meaningful unit of work, emit:

```
[COVERAGE SUMMARY: target=<X>% actual=<Y>% — met / not met — <reason if not met>]
```

**Percentage format is mandatory.** Both `target=` and `actual=` MUST be percentages with the `%` symbol. The pre-commit hook `.githooks/check-registry-read.py` enforces this. Bad examples that the hook rejects: `target=Level A`, `actual=8/8`, `target=N/A`. Good examples: `target=90% actual=92.5% — met`, `target=75% actual=68.0% — not met — reason`.

When the task is documentation only, use `target=0% actual=0% — met (no code changes; no coverage applicable)` so the marker still parses.

**No analogies or metaphors in the reason field.** Write the literal cause. Per `PLAIN-ENGLISH-RULE.md` § Plain-English Absolutism, every word an agent sends must be direct and literal.

Honesty is mandatory. Claiming `met` when the suite is failing is a protocol violation that the next agent will discover when CI fails or the coverage ratchet rejects the next pull request.

---

## Pointers

- `AI-CODING-GUIDELINES.md` — the comprehensive guideline doc.
- `docs/specs/fr251-code-coverage-program.md` — the FR spec for this program.
- `docs/ROADMAP.md` — milestones and dates for raising the floor.
- `docs/MUTATION-TESTING.md` — mutmut / Stryker operating manual.
- `docs/CI-GATES.md` — what CI enforces.
- `CLAUDE.md` and `AGENTS.md` — the PARAMOUNT rules and opening ritual.

---

## Plain-English wrap-up

These rules say: **tests must cover what they claim to cover, and the bar is high for anything that touches your data or your business rules.** Backend code that ships features needs 90% coverage minimum and 100% mutation score for configured targets. C++ kernels need 100% branch coverage and 100% mutation score, and must pass native tests, sanitizers, fuzz tests, and benchmarks. Angular components and services require 95% line coverage, 85% branch coverage, and 95% mutation score. Anything in the "Level A" list — scoring, parsing, state machines, money — gets the full property-test + mutation-test + end-to-end-test treatment. Every session picks 10 coverage gaps from the backlog and reduces them. Every task ends with a coverage summary that is honest.
