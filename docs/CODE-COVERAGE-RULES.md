# Code-Coverage Rules — XF Internal Linker V2

**Status:** PARAMOUNT, ABSOLUTE. Read me alongside `AI-CODING-GUIDELINES.md` at every session start. Every agent — Claude Code, Codex, Antigravity, every future agent — applies the right target for the task at hand and meets it without exception. The session ends with `[COVERAGE SUMMARY: ...]`.

This file is the complete coverage contract for the project. It defines:

- The **coverage levels** (A / B / C / D) and what each one requires.
- The **per-language minimum targets** (backend 90%, API 90%, Celery 90%, Angular 75%, C++ 100% branch + mutation).
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
- **Mutation testing** — mutmut (Python) / Stryker (Angular) / Mull (C++) must achieve mutation score above the documented threshold (see `docs/MUTATION-TESTING.md`).
- **Golden-fixture regression tests** — snapshot the expected output for known representative inputs; any change to the snapshot is reviewed.
- **End-to-end review-workflow tests** (Playwright) for any code path that participates in a user-facing review or approval flow.
- **Traceability** — each test references the rule, FR, or invariant it enforces, by ID or by comment.

### Level B — Standard line + branch

For first-class code paths that don't yet warrant Level A.

- Line coverage at the documented per-language minimum.
- Branch coverage at the documented per-language minimum.
- Tests for happy path + invalid input + empty input + boundary values.
- Mutation testing is **encouraged** via the Stryker / mutmut scope ratchet; not yet a hard gate at this level.

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
| C++ extensions (`backend/extensions/*.cpp`) | **100%** branch coverage + Mull mutation score ≥ 70% |
| Angular components (`frontend/src/app/**/*.component.ts`) | **75%** line + 60% branch |
| Angular services (`frontend/src/app/**/*.service.ts`) | **75%** line + 60% branch |
| Critical review-page workflows | **90%** + at least 1 Playwright E2E spec |
| External integrations (GSC, GA4, Matomo, WP, XF, OpenAI, Gemini, webhooks) | **90%** + Pact contract + at least 1 integration smoke (mocked or sandboxed) |

The current per-language floor is enforced by:

- Backend: `--cov-fail-under=68` in `backend/pytest.ini` (ratchet; raises only).
- Frontend: thresholds block in `frontend/karma.conf.cjs` (statements 30 / branches 25 / functions 30 / lines 30 — also a ratchet; raises only).
- C++: GoogleTest line/branch coverage instrumented in `cpp-clang-tidy` build (followup PR plumbs `lcov` output).

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

Every Level A change must run mutmut / Stryker / Mull on the touched module (changed-files scope in pre-push; full scope in CI nightly). Surviving mutants are non-zero exit.

Tooling reference: `docs/MUTATION-TESTING.md`. Initial scope (one module per language) is documented there; expansion is one module per PR via the AutoIssue ratchet.

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

Drain rate: **10 per session** alongside the standard 18-pick quota. Marker line in the opening ritual:

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

Honesty is mandatory. Claiming `met` when the suite is red is a protocol violation that the next agent will discover when CI fails or the coverage ratchet rejects the next PR.

---

## Pointers

- `AI-CODING-GUIDELINES.md` — the comprehensive guideline doc.
- `docs/specs/fr251-code-coverage-program.md` — the FR spec for this program.
- `docs/ROADMAP.md` — milestones and dates for raising the floor.
- `docs/MUTATION-TESTING.md` — mutmut / Stryker / Mull operating manual.
- `docs/CI-GATES.md` — what CI enforces.
- `CLAUDE.md` and `AGENTS.md` — the PARAMOUNT rules and opening ritual.

---

## Plain-English wrap-up

These rules say: **tests must cover what they claim to cover, and the bar is high for anything that touches your data or your business rules.** Backend code that ships features needs 90% coverage minimum. C++ kernels need 100% branch coverage and pass mutation testing. Angular components are looser at 75%. Anything in the "Level A" list — scoring, parsing, state machines, money — gets the full property-test + mutation-test + end-to-end-test treatment. Every session picks 10 coverage gaps from the backlog and chips away at them. Every task ends with a coverage summary that is honest.
