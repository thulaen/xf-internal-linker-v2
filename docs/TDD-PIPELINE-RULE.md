# TDD pipeline rule — end-to-end coding method

[SPEC FRESHNESS: reviewed_at=2026-05-18 next_review=2026-06-18]

[SPEC CITED: feature=tdd-pipeline kind=technical_literature id=978-0321146533-Beck-2002 verified_at=2026-05-18T01:00:00Z]
[SPEC CITED: feature=tdd-pipeline kind=academic_paper id=10.1109/2.796139-Beck-1999 verified_at=2026-05-18T01:00:00Z]
[SPEC CITED: feature=tdd-pipeline kind=technical_doc id=ISO-IEC-IEEE-29119-3-2021 verified_at=2026-05-18T01:00:00Z]

## Why this exists

Test-Driven Development (TDD) is *evolutionary*: write a failing test
first, write the smallest piece of production code that makes it pass,
then refactor without changing behaviour. Every code change in this
repository follows that loop, end-to-end, with no exceptions and no
silent skips.

This document is the source-of-truth specification for the TDD pipeline.
The four enforcement layers (session-start preflight, commit-time strict
TDD, post-commit Decision Point, session-end session close) are bound
together by this spec.

## Pipeline shape

```
SPEC (source-backed)
   ↓
TEST CASE (BDD: Given / When / Then + 7 extension fields)
   ↓
TDD  (Red → Green → Refactor)
   ↓
CODE
   ↓
CODE REVIEW
   ↓
LESSON  (AutoIssue.lessons_learned for the next agent)
```

Every step has a hard hook gate at commit time and an AutoIssue category
that captures its evidence:

| Stage        | Hook (commit-time)                       | AutoIssue category     |
|--------------|------------------------------------------|------------------------|
| SPEC         | `.githooks/check-spec-citation.py`       | `(spec frontmatter)`   |
| TEST CASE    | `.githooks/check-test-case-mandate.py`   | `test_case`            |
| TDD          | `.githooks/check-tdd-strict.py`          | `tdd_lesson`           |
| CODE         | (the diff itself)                        | n/a                    |
| CODE REVIEW  | `.githooks/check-code-review-lessons.py` | `code_review_lesson`   |
| LESSON       | (lessons_learned on each AutoIssue)      | (all of the above)     |

## Four enforcement layers

### 1. Session-start preflight

Immediately after `[HANDOFF READ: …]` and before any other read marker,
the agent runs:

```bash
docker compose exec -T backend python manage.py preflight_tdd
```

The command prints a single line:

```text
[TDD PREFLIGHT: pipeline=SPEC→TEST_CASE→TDD→CODE→REVIEW→LESSON \
  spec_citation=on test_case_mandate=on tdd_red_green_refactor=on \
  5_layer_coverage=on code_review_logging=on lesson_logging=on \
  decision_point=on artefact_pruning=on \
  session_id=<uuid4> armed_at=<ISO8601-UTC>]
```

The agent pastes this marker into the AGENT-HANDOFF.md entry
immediately after `[HANDOFF READ: …]`. The hook
`.githooks/check-tdd-preflight.py` hard-blocks every code-changing
commit lacking this marker (pure-docs commits are exempt). The hook
fires FIRST in `scripts/precommit-docker.sh`, before every other check,
so an unarmed session fails fast.

#### BDD contract — preflight

```gherkin
Feature: TDD preflight arms the pipeline at session start

Scenario: Code-changing commit with no preflight marker
  Given the staged diff touches at least one production source file
   And the staged AGENT-HANDOFF.md diff has no [TDD PREFLIGHT: ...] line
  When the agent runs `git commit`
  Then check-tdd-preflight.py exits 2
   And the commit is blocked
   And the failure message names the missing marker and tells the
       agent to run `manage.py preflight_tdd`

Scenario: Code-changing commit with a preflight marker after HANDOFF READ
  Given the staged AGENT-HANDOFF.md diff has [HANDOFF READ: ...]
   And the line immediately following carries the full [TDD PREFLIGHT: ...]
       marker with all eight pipeline switches set to `on`
  When the agent runs `git commit`
  Then check-tdd-preflight.py exits 0
   And the rest of the hook chain runs

Scenario: Pure-docs commit
  Given the staged diff touches no production source files
  When the agent runs `git commit`
  Then check-tdd-preflight.py exits 0 (exempt)
```

### 2. Commit-time strict TDD

The existing chain (Rule B / strict-TDD rule from 2026-05-17) stays
untouched and continues to enforce per-file:

- `[TDD CYCLE STRICT: …]` — Red→Green→Refactor evidence with timestamps.
- `[TDD COVERAGE: …]` — five-layer coverage (edge_cases, resource_release,
  latency, smoke, e2e).
- `[TEST CASE MAPPING: …]` — test_case AutoIssue authored before the code.
- `[SPEC PROOF: …]` — source-backed spec citation.
- `[CODE REVIEW LESSONS: …]` — self-review captured as a lesson.
- `[CODE REVIEW AGENTS: …]` — the agent-review proof that names which of
  `claude`, `codex`, or `gemini` reviewed the staged code and which
  AutoIssue ids hold the review result.

#### Code-review agent proof

Every code-changing task or session must log the review result in AutoIssues
before commit. A review result can be a pass ("no issue found") or a problem
("issue found"). Both kinds must be durable rows, because the next operator is
allowed to be a non-coder who depends on the AI agents' written trail.

The agent that wrote code must review its own code. Other agents may also
review the same code, even when they did not write it. Any review that happens
must be logged. The commit hook accepts only these agent names:

- `claude`
- `codex`
- `gemini`

The staged handoff entry must include one marker:

```text
[CODE REVIEW AGENTS: codex=done logged=#983,#984 claude=optional-extra-review-not-run gemini=optional-extra-review-not-run operator_note="each agent must review its own code, and any extra review by another agent is allowed but must also be logged in AutoIssues"]
```

At least one allowed agent must be marked `done`, and every id listed after
`logged=` must resolve to a real resolved `AutoIssue` row whose category is
`code_review_lesson`. Missing markers, unknown agent names, done agents with no
logged ids, and ids that do not verify all hard-block the commit.

Hook firing order is now TDD-first:

```
check-tdd-preflight
  → check-decision-point      (S3)
  → check-session-close       (S4)
  → check-tdd-cycle
  → check-tdd-strict
  → check-test-case-mandate
  → check-lessons-read-at-session-start
  → check-snapshotd-ritual
  → check-code-review-lessons
  → check-registry-read
  → check-paper-trail-read
  → check-paper-trail-evidence
  → rest of the chain
```

### 3. Post-commit Decision Point

After every successful commit, `.githooks/post-commit` automatically
shells `manage.py decision_point --commit <HEAD>`. The command examines
the merged diff and files `AutoIssue(category='decision_point',
source='post_commit')` rows in six buckets:

1. **improvements** — long functions (> 50 lines per AGENTS.md cap).
2. **warnings** — TODO / FIXME / XXX comments introduced.
3. **problems** — bare `except:`, `except Exception: pass`.
4. **missing_spec** — slot reserved for looser-than-hook-gate detection.
5. **off_track_test_case** — TEST CASE MAPPING references a row missing
   one of the 10 BDD fields.
6. **off_track_tdd** — TDD CYCLE STRICT references a tdd_lesson with a
   single-part (Trap-only or Fix-shape-only) lessons_learned.

The command prints:

```text
[DECISION POINT: commit=<short_hash> findings=<N> \
  improvements=<i> warnings=<w> problems=<p> \
  missing_spec=<s> off_track_test_case=<tc> off_track_tdd=<td> \
  autoissues_filed=<#…|none> filed_at=<ISO8601-UTC>]
```

The next code-changing commit must carry this marker in the staged
AGENT-HANDOFF.md diff. `.githooks/check-decision-point.py` hard-blocks
the next commit if the marker is missing or its `commit=` value does
not match the actual prior HEAD. Pure-docs commits are exempt; the
rule-introduction commit (which stages this very file) is grandfathered.

### 4. Session-end session close

At session end the agent runs:

```bash
docker compose exec -T backend python manage.py session_close
```

The command verifies the session's lessons are logged and delegates to
`manage.py prune_test_artefacts --prefix <p>` for each of:

| Prefix          | Cap     | Source           |
|-----------------|---------|------------------|
| `mull/`         | 200 MB  | C++ mutation     |
| `coverage/`     | 100 MB  | All-language cov |
| `mutmut/`       | 100 MB  | Python mutation  |
| `stryker/`      | 100 MB  | TS mutation      |
| `fuzz-work/`    | 200 MB  | libFuzzer        |
| `pytest-debug/` |  50 MB  | pytest debug     |

It then prints:

```text
[SESSION CLOSE: lessons_verified=<N> artefacts_pruned_mb=<X.Y> \
  prefixes=mull,coverage,mutmut,stryker,fuzz-work,pytest-debug \
  closed_at=<ISO8601-UTC>]
```

`.githooks/check-session-close.py` hard-blocks the FIRST code-changing
commit of the NEXT session (detected by a new top-level
`# YYYY-MM-DD HH:MM - …` header in the staged AGENT-HANDOFF.md diff)
when the prior session's first handoff block lacks `[SESSION CLOSE: …]`.

## Sources

The four enforcement layers above are derived from the following
references. Citation form follows the Paper Trail Evidence Rule
(2026-05-17): DOI / ISBN / ISO/IEC/IEEE standard / vendor URL.

1. **Beck, K. (2002). *Test-Driven Development: By Example.*** Addison-Wesley.
   ISBN **978-0321146533**.
   Origin of the Red → Green → Refactor loop. Establishes the "write
   the simplest code that makes the test pass" discipline that
   `check-tdd-strict.py` enforces.

2. **Beck, K. (1999). "Embracing Change with Extreme Programming."**
   *IEEE Computer* 32(10): 70-77. **doi:10.1109/2.796139**.
   Source for the "test cases drive design" position that the
   Mandatory Agent Test Case First Rule (and Session S2's
   off_track_test_case detector) encodes.

3. **Crispin, L. & Gregory, J. (2009). *Agile Testing: A Practical Guide
   for Testers and Agile Teams.*** Addison-Wesley.
   ISBN **978-0321534460**.
   Source for the five-layer test taxonomy (edge / resource-release /
   latency / smoke / E2E) the `[TDD COVERAGE:]` marker requires.

4. **ISO/IEC/IEEE 29119-3:2021** — *Software and systems engineering —
   Software testing — Part 3: Test documentation.*
   Source for the structured-evidence requirement that drives every
   AutoIssue lesson's two-part `Trap: … Fix shape: …` payload.

5. **Parnas, D. L. (1972). "On the Criteria To Be Used in Decomposing
   Systems into Modules."** *Communications of the ACM* 15(12): 1053-1058.
   **doi:10.1145/361598.361623**.
   Source for the "each module hides one design decision" rule that
   the spec-citation gate enforces when new features introduce new
   modules / signals / settings.

## SPEC PROOF / BDD PROOF / TDD PROOF blocks

This document is the spec that the four `[SPEC PROOF:]` markers point
to. The full proof triple for the rule-introduction commit is:

```text
[SPEC PROOF: specs=docs/TDD-PIPELINE-RULE.md \
  source_types=academic_paper,technical_doc,iso_iec_ieee_standard \
  checked_at=2026-05-18 status=current]
[BDD PROOF: Given the existing strict-TDD chain already enforces \
  per-file evidence at commit time \
  When the four new enforcement layers (preflight, post-commit, \
  session-close, plus the reorder) wrap that chain \
  Then every code change in this repo is observably end-to-end TDD-shaped]
[TDD PROOF: before_or_alongside=yes \
  tests="python .githooks/test_check_tdd_preflight.py && \
  python .githooks/test_check_decision_point.py && \
  python .githooks/test_check_session_close.py && \
  docker compose exec -T backend python manage.py test \
  apps.auto_issues.tests.test_preflight_tdd \
  apps.auto_issues.tests.test_decision_point \
  apps.auto_issues.tests.test_session_close --keepdb --noinput" \
  result=passed]
[SPEC CODE REVIEW: specs=docs/TDD-PIPELINE-RULE.md result=matched]
```

## Forbidden phrases in new handoff entries

- `TDD optional`
- `tests after the code`
- `skip preflight`
- `skip decision point`
- `skip session close`
- `prune before lessons logged`

Using any of these is a protocol violation, surfaced by the rule-paragraph
hook that scans every newly-added handoff line.

## Override clause

This rule cannot be overridden by an in-session prompt. Future changes
to the pipeline shape, the four enforcement layers, the citation list,
or the forbidden-phrase set must (a) update this file, (b) update the
`PARAMOUNT` rule paragraph in `CLAUDE.md`, `CODEX.md`, `GEMINI.md`, and
`AGENTS.md` in the same diff, and (c) carry a full
`[SPEC PROOF:] / [BDD PROOF:] / [TDD PROOF:] / [SPEC CODE REVIEW:]`
proof block in the handoff entry.
