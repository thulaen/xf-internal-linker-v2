# AI Coding Agent Guidelines — XF Internal Linker V2

**Status:** PARAMOUNT, ABSOLUTE. Read me on every session start, before every task, and re-check me when you doubt an approach. Every AI agent that touches this repo — Claude Code, Codex, Antigravity, and every future agent — must follow these guidelines without exception. The goal is **reliable software, not fast hallucinated code.**

This file is the single source of truth for how to write code in this repository. Other rule documents (`CLAUDE.md`, `AGENTS.md`, `AI-CONTEXT.md`, `PLAIN-ENGLISH-RULE.md`, `ONGOING-CODE-QUALITY.md`, `docs/CODE-COVERAGE-RULES.md`) reference and reinforce what is written here; if any of them ever drift apart, **this file wins**.

---

## How to use this file

1. **Read it once per session, at session start, before any work.** Confirm with the marker `[GUIDELINES READ: AI-CODING-GUIDELINES.md + docs/CODE-COVERAGE-RULES.md]` immediately after the `[REGISTRY READ: ...]` marker.
2. **Pick the right coverage target for the task.** Find the task type in the [Per-task coverage targets](#per-task-coverage-targets) table below. Note the target. Plan the change to meet it.
3. **End every slice, task, and session with a coverage summary.** Output `[COVERAGE SUMMARY: target=<X>% actual=<Y>% — met / not met — <one-line reason if not met>]`. Honesty is mandatory; the auto-iterate rule (see `CLAUDE.md`) requires you to chase the gap to zero, not paper over it.
4. **Drain the coverage backlog every session.** Alongside the 18 auto-issues from the standard quota and the 10 latest failed CI runs, pick **10 coverage-gap AutoIssues** (source='agent', kind='coverage-gap'). Marker `[COVERAGE GAPS READ: 10 picked — #..., ...]`.

---

## Prime directive

**Do not guess.**

When uncertain, inspect the codebase, tests, documentation, package files, database schema, API contracts, issues, or source material before editing code. If the answer is still uncertain, state the uncertainty in plain English and make the smallest safe change.

---

## Source-of-truth order

When two sources disagree, the higher-priority source wins. Never let a lower source override a higher one without an explicit, written justification.

1. Existing tests
2. Existing production code
3. Database schema and migrations
4. API contracts and type definitions
5. Product requirements and specs
6. Architecture docs
7. Official library documentation
8. Standards documents
9. Academic papers
10. Patents
11. Comments in code
12. Guesses by the model — **last resort, requires written caveat**

---

## No-hallucination rules

Agents must **not invent**:

- Functions
- Classes
- Database columns
- API endpoints
- Config keys
- Environment variables
- Package names
- CLI flags
- Business rules
- Authentication behaviour
- Error codes
- External service behaviour

Before using an API, verify it via one of:

- Existing usage in the repo
- Official docs (read them, don't recall)
- Installed package source
- Type definitions
- Tests
- Lockfile + installed package version

**If an API cannot be verified, do not use it.** Pick an alternative that you can verify, or stop and ask.

---

## Required work loop

For every task, follow this loop in order. Do not jump to step 5 before step 4.

1. **Understand the request.** Read it twice. State your interpretation in one sentence before editing anything.
2. **Inspect relevant files.** Glob, Grep, Read. Note existing patterns.
3. **Identify source of truth.** Pick the highest-priority source you can find for the area being changed.
4. **Locate affected code paths.** Map call sites, imports, tests, migrations.
5. **Make the smallest correct change.** Surgical, not architectural — unless the task demands architecture work.
6. **Add or update tests.** Per the [Per-task coverage targets](#per-task-coverage-targets) and [Code-coverage rules](docs/CODE-COVERAGE-RULES.md).
7. **Run relevant checks.** Lint, type-check, the new tests, the random-order suite. If a check is skipped, say so.
8. **Summarize what changed.** Per PLAIN-ENGLISH-RULE.md — what's doing, what was accomplished, what has issues.
9. **Emit the coverage summary marker.** `[COVERAGE SUMMARY: ...]` — see the format above.

---

## Scope control

Avoid unrelated rewrites. **Do not change** formatting, naming, file structure, dependencies, or architecture unless the task requires it. If a refactor is genuinely needed, write one sentence explaining why before refactoring. Prefer surgical changes; bundle refactors and feature work only when one strictly enables the other.

---

## Code-smell policy

Fix code smells in the area you're touching, when safe. Do not perform sweeps outside the task scope.

Fix these when they are in your diff path:

- Duplicated logic
- Long functions (see [Long-function rule](#long-function-rule))
- Large classes
- Deep nesting (≥ 4 levels)
- Boolean flag arguments
- Dead code
- Unused variables
- Unclear names (see [Naming rules](#naming-rules))
- Magic numbers
- Hidden side effects
- Repeated conditionals
- Primitive obsession
- Shotgun surgery
- Tight coupling
- Leaky abstractions
- Overly broad `try`/`catch`
- Silent failures
- Inconsistent error handling

---

## Long-function rule

Refactor a function when any of these is true:

- Does more than one job
- Has multiple abstraction levels
- Needs many comments to explain itself
- Has deeply nested conditionals (≥ 4 nesting levels)
- Is hard to test directly
- Exceeds roughly **50 lines** without strong justification (hard cap: 80 lines)

Refactor by extracting **named helper functions** with clear responsibility. Don't shatter code into meaningless tiny wrappers; the goal is readability, not line-count theatre.

---

## Bug-fixing rules

When fixing a bug:

1. Reproduce the failure or reason from a concrete trace.
2. Identify the root cause — not the symptom.
3. Add a regression test (preferably one that would have caught it earlier).
4. Fix the smallest affected path.
5. Look for nearby similar bugs (same module, same pattern). Fix them in-scope if cheap; file AutoIssues otherwise.
6. Do not hide the bug with broad exception handling.

**A bug fix without a test is incomplete.** If a test is impossible, write the explicit reason and a verification-by-eye plan in the commit message.

---

## Test requirements

Every change in the following areas requires new or updated tests:

- Business logic
- Parsing (HTML, sitemaps, feeds)
- Import normalization
- Scoring
- Ranking
- Permission checks
- State transitions
- Retry behavior
- Idempotency
- Database constraints
- Edge cases
- Previously broken behaviour (regression tests)

Each test set should cover:

- Happy path
- Invalid input
- Empty input
- Boundary values (zero, one, max, off-by-one)
- Duplicate data
- Permission denied
- Retry cases
- Partial failure cases

**Never delete tests** unless they are provably obsolete. If you must, justify in the commit message and link the test you removed.

---

## Property-based testing

Use property tests (Hypothesis on Python; fast-check on TypeScript) when logic has many input combinations. Good candidates:

- Text cleaning
- HTML stripping
- URL normalization
- Slug generation
- Deduplication
- Scoring
- Ranking
- Import parsing
- Checkpoint resume logic

Property tests verify **invariants**, not examples:

- Normalisation is idempotent: `f(f(x)) == f(x)`
- Deduplication never increases item count
- Scores remain within valid bounds
- Retried jobs do not create duplicate rows
- Sorting is deterministic
- Empty input does not crash

See `docs/CODE-COVERAGE-RULES.md` for the full Level A list of areas where property tests are mandatory.

---

## Evidence-based algorithm work

When implementing algorithmic logic, cite a real source:

- Internal product spec
- Existing implementation
- Academic paper
- Patent
- Standard
- Official documentation
- Explicit user instruction

If using a paper, patent, or standard, record in the spec or commit:

- Title
- Author or assignee (where available)
- Year (where available)
- Link or local reference
- Which part was used
- What was intentionally not implemented

**Do not cite a paper you have not inspected.** Cite-and-move is hallucination.

---

## Business-logic rules

Business logic must be **explicit and testable**.

Do not bury business rules inside:

- UI components
- Controllers
- Celery tasks
- Database callbacks
- Template code
- Ad-hoc scripts

Prefer dedicated service modules, domain modules, or pure functions. Business logic must not depend on hidden global state unless unavoidable (and then it needs a comment explaining why).

---

## State-transition rules

For workflows like approval, rejection, manual review, import, indexing, retries:

- Define allowed states.
- Define allowed transitions.
- Reject invalid transitions.
- **Test every allowed transition.**
- **Test every invalid transition** (must raise / refuse).
- Log important transition events.

Never update a status field casually without checking transition validity.

**Approval state contract (mandatory tests):**

- `pending` → `approved` allowed
- `pending` → `rejected` allowed
- `pending` → `manual_review` allowed
- `approved` → `pending` forbidden (no silent reversal)
- `rejected` → `approved` forbidden (no auto-approval without explicit user action)
- `manual_review` preserves reviewer notes

---

## Idempotency rules

Jobs, imports, retries, webhooks, and background tasks must be idempotent. Repeated execution must not:

- Duplicate records
- Corrupt state
- Double-charge
- Double-notify
- Rebuild inconsistent indexes
- Lose checkpoints
- Skip valid work

Use stable keys, unique constraints, upserts, locks, or transaction boundaries.

**Celery idempotency contract (mandatory tests):**

- Running the same import twice does not duplicate posts.
- Running the same embedding job twice does not duplicate embeddings.
- Retrying after a crash continues from the last checkpoint.
- Partial failure does not mark the whole pipeline complete.
- Cancelled jobs do not leave approved suggestions in an invalid state.

---

## Database rules

- Inspect the existing schema before changing models.
- Add migrations for every schema change.
- Preserve existing data where possible.
- Add `unique=True` for true uniqueness rules.
- Add indexes for new query patterns when justified.
- Avoid `null=True` unless null has business meaning.
- Avoid silent `on_delete=CASCADE` unless explicitly intended.

Every data migration must be either **reversible** or **clearly marked irreversible** with a written justification.

See also: `NO-DUPLICATES.md`, `DEFAULT-ON-RULE.md`.

---

## Error-handling rules

Errors must be **explicit**.

- Do not swallow exceptions silently.
- Do not use `except Exception:` (or `catch (e)`) unless:
  - The error is logged.
  - The fallback behaviour is intentional.
  - The caller receives a meaningful result.
  - Tests cover the failure path.

Error messages should help diagnose the problem **without leaking secrets**.

---

## Logging rules

Log the following:

- Job start and finish
- Retry attempts
- Import failures
- External API failures
- Permission denials
- Invalid state transitions
- Data-corruption risks
- Skipped records (with reasons)

**Never log:**

- API keys
- Tokens
- Passwords
- Private user content (unless necessary and safe)
- Large payloads by default

---

## Security rules

Never:

- Bypass authentication
- Bypass authorization
- Hardcode secrets
- Log secrets
- Disable CSRF protection
- Trust client-supplied user IDs
- Trust unsanitised HTML
- Use `eval` on untrusted input
- Add broad admin permissions
- Expose internal errors to users

Permission changes require tests.

---

## External-service rules

For integrations (GSC, GA4, Matomo, WordPress, XenForo, OpenAI, Gemini, webhooks):

- Verify the API contract.
- Handle rate limits.
- Handle partial failure.
- Handle retries (with backoff).
- Validate payloads at the boundary.
- Store external IDs when needed for dedup.
- Avoid duplicate imports.
- Test mocked responses.
- Keep provider-specific logic isolated.

Do not assume all providers behave the same.

---

## Performance rules

Before adding "performance" code:

- Identify the bottleneck (profile, don't guess).
- Estimate data size.
- Count queries.
- Estimate algorithmic complexity.
- Prefer simple improvements first.

Avoid:

- N+1 queries
- Loading huge datasets into memory
- Recomputing expensive results
- Rebuilding indexes unnecessarily
- Calling paid APIs repeatedly without caching or gating

---

## Paid-API rules

Paid API calls must be controlled.

Do not introduce code that:

- Calls paid APIs in loops without limits.
- Retries paid calls excessively.
- Re-embeds unchanged content without reason.
- Compares many paid models unnecessarily.
- Runs expensive work without user confirmation where appropriate.

Add cost guards, caching, sampling, or dry-run modes when relevant. Read `apps/pipeline/services/api_rate_limiter.py` (FR-250) before adding any new outbound paid call.

---

## Documentation rules

Update documentation when behaviour changes. Documentation should include:

- What changed
- Why it changed
- How to use it
- Configuration needed
- Edge cases
- Known limitations

Do not write misleading documentation for features that are not implemented.

---

## Comments

Comments explain **why**, not **what**.

Good comments explain:

- Business rules
- Non-obvious tradeoffs
- External API quirks
- Algorithm choices
- Security decisions
- Data-migration risks

Bad comments restate obvious code.

---

## Naming rules

Names must be **specific and domain-accurate**.

Avoid vague names:

- `data`, `item`, `thing`, `result`, `helper`, `manager`, `processor`, `handler`

Prefer names that describe the domain concept:

- `normalize_imported_post_url`
- `calculate_candidate_link_score`
- `detect_existing_internal_link`
- `build_embedding_checkpoint`
- `reject_invalid_review_transition`

---

## Dependency rules

Before adding a dependency, check:

- Is it already installed?
- Is it actively maintained?
- Is it necessary?
- Can the standard library do this?
- Does it increase security risk?
- Does it increase bundle size?
- Does it conflict with existing packages?

New dependencies require justification in the commit message.

---

## Formatting rules

Follow the repo's existing formatter and style. **Do not reformat unrelated files.** Do not mix style changes with logic changes unless requested. `ruff format` (Python) and `prettier` (frontend) are the canonical formatters.

---

## Type-safety rules

- Preserve type annotations.
- Add types for new public functions.
- Avoid `Any` (or TypeScript `any`) unless justified.
- Keep interfaces narrow.
- Prefer explicit return types for important functions.
- Validate external input at boundaries.

---

## UI rules

For user-facing flows:

- Show clear loading states.
- Show actionable errors.
- Avoid silent failure.
- Confirm destructive actions.
- Explain expensive operations.
- Explain long-running operations.
- Keep novice users in mind.
- Avoid exposing internal jargon unnecessarily.

---

## Accessibility rules

UI changes preserve accessibility:

- Keyboard access
- Labels
- Focus states
- Contrast ratios
- Screen-reader text
- Form errors
- Button states

Do not replace semantic elements with generic `<div>`s unless necessary.

---

## Concurrency rules

For any new async, queue, or worker behaviour, consider:

- Race conditions
- Duplicate workers
- Retry overlap
- Locking
- Transaction boundaries
- Partial failure
- Checkpoint consistency

Concurrent code requires tests or a clearly-written verification plan.

---

## Refactoring rules

Before refactoring:

- Identify current behaviour (read tests + read code).
- Preserve public interfaces unless intentionally changed.
- Add **characterization tests** if behaviour is unclear.
- Make small steps.
- Avoid mixing refactor and feature work unnecessarily.

After refactoring:

- Run relevant tests.
- Summarize what behaviour was preserved.
- Mention any intentional behavioural change.

---

## Generated-code rules

Treat AI-generated code as **untrusted until checked**. Review for:

- Fake APIs
- Broken imports
- Wrong assumptions
- Security issues
- Missing edge cases
- Inconsistent naming
- Untested logic
- Excess abstraction
- Hidden performance costs

Do not submit generated code just because it looks plausible.

---

## File-editing rules

Before editing a file, inspect enough surrounding code to understand:

- Existing patterns
- Imports
- Error-handling style
- Naming conventions
- Test strategy
- Ownership boundaries

Do not create duplicate modules when an existing place already owns the behaviour. Search before you write.

---

## Test-running policy

Run the narrowest useful checks first:

- Single unit test for changed function
- Related test file
- Related integration test
- Type check
- Lint
- Full test suite (where practical)

If checks cannot be run, **state why**.

---

## Final response format (every task)

After completing work, the response must report:

- **Files changed** (list)
- **What changed** (one-line per file is fine)
- **Tests added or updated**
- **Checks run**
- **Checks not run** (and why)
- **Risks or follow-ups**
- **Coverage summary marker** — `[COVERAGE SUMMARY: target=X% actual=Y% — met / not met]`

Do not claim tests passed unless they were actually run.

---

## Definition of done

A task is done **only when**:

- Requested behaviour is implemented.
- Change follows existing architecture.
- Relevant tests exist.
- Relevant checks pass (or skipped checks are disclosed).
- No unrelated rewrites were made.
- No fake APIs were introduced.
- Error handling is appropriate.
- Security was not weakened.
- Documentation was updated where needed.
- **Coverage target for the task type was met** (see table below) OR an explicit `[COVERAGE SUMMARY: not met — <reason>]` was filed.

---

## Per-task coverage targets

The coverage target for a task is determined by what the task touches. If a task touches multiple areas, the **strictest applicable target** wins.

| Task type / area | Coverage Level | Target |
|---|---|---|
| Backend service modules (`backend/apps/*/services/**`) | Level A | **90%** |
| API endpoints (`backend/apps/api/`, `backend/apps/*/views*.py`) | Level A | **90%** |
| Celery tasks (`backend/apps/*/tasks*.py`) | Level A | **90%** |
| C++ extensions (`backend/extensions/*.cpp`) | Level A (MC/DC) | **100% branch + mutation** |
| Angular components (`frontend/src/app/**/*.component.ts`) | Level B | **75%** |
| Angular services (`frontend/src/app/**/*.service.ts`) | Level B | **75%** |
| Critical review-page workflows | Level A + E2E | **90% + Playwright spec** |
| External integrations (GSC, GA4, Matomo, WP, XF, OpenAI, Gemini) | Level A + Contract | **90% + Pact spec + 1 integration smoke** |
| Migrations | Level C | Smoke test that runs forward + backward |
| Docs / config / scaffolding | Level D | No coverage gate (manual review) |

**Level A** — Modified Condition/Decision Coverage (MC/DC), formal structural coverage with traceability, 100% code coverage, property-based tests, full branch coverage, mutation testing, golden-fixture regression tests, end-to-end review-workflow tests where applicable. See `docs/CODE-COVERAGE-RULES.md`.

**Level B** — Standard line + branch coverage at the documented threshold. Mutation testing optional but encouraged via the Stryker / mutmut scope ratchet.

**Level C** — Smoke-level only. The change must be runnable; the migration must be reversible.

**Level D** — No formal gate; manual review.

---

## How to pick the target for the task you've been given

1. List the files the task will touch.
2. For each file, find its row in the table above.
3. Take the **strictest** target across all touched files.
4. Emit at session start (or before writing code for the task):
   `[COVERAGE TARGET: <area>, Level <A/B/C/D>, target <X>% (current <Y>% if known)]`
5. Drive the change so the target is met before claiming done.

---

## Coverage-gap backlog — drain 10 per session

Independently of whatever feature work the user asked for, every agent picks **10 coverage-gap AutoIssues** at session start. These live in the AutoIssue table with `source='agent'` and metadata `{"kind": "coverage-gap", "level": "A/B/C", "area": "..."}`. The marker line is:

```
[COVERAGE GAPS READ: 10 picked — #163, #164, #165, #166, #167, #168, #169, #170, #171, #172]
```

Validated by `.githooks/check-registry-read.py`. This is **in addition** to the standard 18-pick (`[REGISTRY READ: ...]`) and the 10 latest failed CI runs (`[CI FAILED RUNS READ: ...]`). Total per session: **38 items to triage**, with the agent then doing the user-requested work on top.

If fewer than 10 coverage-gap AutoIssues are open (drought), the agent must:

1. Read `docs/CODE-COVERAGE-RULES.md` and identify which Level A areas are underseeded.
2. File new `AutoIssue(source='agent', kind='coverage-gap', ...)` rows for missing areas.
3. Use the marker form `[COVERAGE GAPS READ: <K> picked + <10-K> filed — #..., (drought logged: #<id>)]`.

---

## End-of-slice / end-of-task / end-of-session coverage summary

After every meaningful unit of work, emit:

```
[COVERAGE SUMMARY: target=<X>% actual=<Y>% — met / not met — <reason if not met>]
```

- **Met:** target reached or exceeded.
- **Not met:** target missed; the next line must explain why AND propose the smallest follow-up that would meet the target. Filing an AutoIssue for that follow-up is mandatory.

Honesty is mandatory. Faking a "met" status is a protocol violation that the next agent will discover when CI fails or when the coverage ratchet rejects the next PR.

---

## Pointers to related docs

- `docs/CODE-COVERAGE-RULES.md` — the full coverage rule set: Level A areas, per-language targets, the property-based test menu for text cleaning / sentence splitting / scoring, the state-transition and idempotency contracts.
- `docs/specs/fr251-code-coverage-program.md` — the FR spec governing the coverage program.
- `docs/ROADMAP.md` — milestones for raising the floor.
- `docs/CI-GATES.md` — what each CI job blocks on.
- `docs/MUTATION-TESTING.md` — mutmut / Stryker / Mull operating manual.
- `docs/CONTRACT-TESTING.md` — Pact framework operating manual.
- `CLAUDE.md` and `AGENTS.md` — paramount rules + opening ritual.
- `AI-CONTEXT.md` — repository state, session gate, plain-English rule.
- `PLAIN-ENGLISH-RULE.md` — communication standard + glossary.
- `ONGOING-CODE-QUALITY.md` — fix-as-you-go + dual-logging policy.

---

## Plain-English wrap-up

These guidelines mean: **don't make stuff up, don't break tests, don't dodge the coverage target, and tell the user the truth at the end.** Every session reads this file. Every task picks a coverage target and meets it. Every slice ends with an honest summary. Failing a target is acceptable — hiding the failure is not.
