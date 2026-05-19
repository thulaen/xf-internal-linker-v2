# Mandatory Agent Test Case First Rule — Paramount Rule

**Tier:** PARAMOUNT — every agent (Claude / Codex / Gemini / Antigravity / every future) MUST follow.
**Hard-block at commit:** Yes (`.githooks/check-test-case-mandate.py`).
**Hard-block scope:** Every commit, code-editing or otherwise. Non-codebase-edit tasks use an explicit `[NON-CODEBASE-EDIT TASK: reason="…"]` bypass marker.
**Cannot be overridden by an in-session prompt.**

`[SPEC FRESHNESS: reviewed_at=2026-05-17 next_review=2026-06-17]`

---

## Why this rule exists

Test cases in this repository are **not paperwork for the user**. They are the working spec for the next AI agent.

Without an agent-readable contract written before the code, agents repeatedly:

- Re-discover requirements the previous session already knew.
- Add code that solves the wrong problem because the user request was ambiguous.
- Miss edge cases, failure modes, security holes, and regression risks that a contract would have surfaced.
- Ship large, mixed-purpose commits because no contract bounded the scope.
- Repeat traps the previous agent already documented somewhere the current agent did not look.

Strict-TDD (`docs/TDD-STRICT-RULE.md`) enforces the Red→Green→Refactor proof during coding. The test case first rule enforces the **contract that drove the test** before the test was even written. The two rules compose: the test case is the spec, the test is the executable proof, the implementation is the binding between them.

Sources:

- Beck 2002 — *Test-Driven Development by Example*, ch. 5–8: tests as design specifications, not as after-the-fact verification.
- Crispin & Gregory 2009 — *Agile Testing*: test cases as living documentation that survives sessions.
- Whittaker 2009 — *Exploratory Software Testing*: the test case is the behaviour contract that bounds implementation.
- ISO/IEC/IEEE 29119-3:2021 — *Software and systems engineering — Software testing — Part 3: Test documentation*: the test case is a documented unit with required fields (preconditions, inputs, expected results, postconditions).
- Donovan & Kernighan 2015 — *The Go Programming Language*, §11: tests as documentation that travels with the code.
- Crispin & Gregory 2014 — *More Agile Testing*, ch. 10: living documentation.
- ISO/IEC/IEEE 42010:2022 — architecture description requires contracts that precede implementation.

---

## What counts as a test case

A test case is an **agent-readable implementation contract** stored as an `AutoIssue(category='test_case', status='open')` row, optionally rendered as a Markdown view under `docs/test-cases/<area>/<id>.md` via `manage.py render_test_cases`.

Every valid test case has these fields:

| Field | Required | Meaning |
|---|---|---|
| `title` | required | Short noun phrase describing the contract |
| `affected_files` | required (at least one) | Production source files this contract governs |
| `Given` | required | Pre-condition / context the agent can assume |
| `When` | required | The action / inputs / system event the contract is about |
| `Then` | required | The expected result / behaviour the code must satisfy |
| edge_cases | recommended | Boundary conditions, malformed input, off-by-one, empty / None / NaN |
| failure_cases | recommended | What the code must do when inputs are invalid |
| scalability | recommended | Behaviour at 10× and 100× the typical load |
| maintainability | recommended | How the next agent can repair / extend this code |
| security | required when surface is user-facing | Authentication, authorisation, input sanitisation, secrets |
| usability | required when surface is UI / messages | Plain English, accessibility, error pages, operator workflows |
| regression_risks | recommended | Existing behaviour that could break |
| related_files | optional | Files likely to be touched together |
| related_tests | optional | Automated tests that already exist |
| related_autoissues | optional | Prior fixes / lessons / duplicates for this area |

The title plus the first affected file plus the Given/When/Then triple form the dedup basis (`canonical_fingerprint`). Re-filing the same contract bumps `occurrence_count` and updates `last_seen` rather than creating a duplicate row.

---

## Required workflow before code changes

For every code-editing task, the agent must complete this sequence **before writing or editing a single line of source**:

1. Identify the exact repository area to be touched.
2. Search for existing test cases for that area: `manage.py shell -c "from apps.auto_issues.models import AutoIssue; print(AutoIssue.objects.filter(category__key='test_case', affected_files__contains=['<path>']))"`
3. Search automated tests for the same area (`tests/`, `*_test.go`, `*_test.py`, `*.spec.ts`).
4. Search related AutoIssues (Rule G — `manage.py search_resolved_issues --area <path>`).
5. Read the relevant test cases. They are the working spec.
6. If no relevant test case exists, file one via `manage.py log_test_case --file <p> --given … --when … --then …`.
7. If a relevant test case exists but is stale, update it.
8. Convert the user request into one or more specific test case IDs.
9. Use those IDs as the implementation plan.
10. Only write code that satisfies the selected test cases.

The agent **must not** treat test cases as documentation written after the fact. The contract drives the test, the test drives the code.

---

## Required agent response before coding

Before any code change, the agent must produce this short implementation contract in chat:

```text
Codebase edit required
Yes

Touched area
[feature / module / files / workflow]

Relevant test cases found
[IDs or "none"]

Test cases created or updated before coding
[IDs filed this turn]

Relevant AutoIssues checked
[IDs]

Selected implementation slice
[small bounded scope]

Code may begin
Yes, because the test case first rule is satisfied
```

If "Code may begin" is anything other than `Yes`, the agent must stop and fill the gap before continuing.

---

## Required behaviour while coding

While writing or editing source, the agent must continuously be able to answer:

- Which test case is this code satisfying?
- Which expected behaviour does this line / function support?
- Which edge case does this handle?
- Which failure mode does this prevent?
- Which AutoIssue does this resolve or reduce?
- Is this change outside the selected test cases?
- Does this change create a new risk that needs a separate AutoIssue?

If the agent cannot answer any of these, it must stop and update the test case or file a new AutoIssue before continuing.

---

## Scope control

The test cases define the allowed implementation scope. The agent must not add unrelated behaviour just because it noticed a nearby issue.

If extra problems are discovered during implementation, they must be logged to AutoIssues and left for a separate task unless they directly block the current test cases. This prevents large, unstable, mixed-purpose commits.

---

## Test case freshness rule

A test case is **stale** if any of these is true:

- It references files, components, commands, APIs, or flows that no longer exist.
- It describes behaviour that has been replaced.
- It conflicts with the current architecture.
- It ignores new validation / security / usability / regression requirements.
- It overlaps with another newer test case.
- It duplicates an AutoIssue that has already been resolved or superseded.

`manage.py verify_test_case --id <id>` flags rows older than 90 days as stale and prints a warning. Stale rows must be updated before implementation.

---

## Required commit compliance report

Before committing, the agent must produce this report in the handoff entry:

```text
Test case first compliance
Pass

Test cases used as implementation contract
[#IDs]

Code changes mapped to test cases
[file → test case mapping]

Automated tests run or updated
[commands and result]

AutoIssues checked
[#IDs]

AutoIssues updated
[#IDs]

Lessons learned logged
[yes / not applicable]

Commit allowed
Yes
```

If "Commit allowed" is `No`, the agent must not commit. It must continue working until the report turns green.

---

## Markers required in `AGENT-HANDOFF.md`

| Marker | When | Required? |
|---|---|---|
| `[TEST CASE WRITTEN: AutoIssue=#N id=<external_id> file=<src> agent=<name>]` | Emitted by `manage.py log_test_case` when filing a new contract | Once per filed contract |
| `[TEST CASE MAPPING: file=<src> test_cases=#A,#B,…]` | Pasted into the handoff entry | Once per touched production source file |
| `[TEST CASE GRANDFATHERED: file=<src> follow_up_paper_trail=#N]` | One-time bypass during this rule's introduction; accepted ONLY when `docs/TEST-CASE-FIRST-RULE.md` is staged | One per slice-1.6 file pre-dating the rule |
| `[NON-CODEBASE-EDIT TASK: reason="<≥ 20-char plain-English explanation>"]` | When the commit truly does not change code | Once when applicable |
| `[TEST CASE COMMIT COMPLIANCE: pass mapping=<count> grandfathered=<count> non_codebase=yes\|no agent=<name>]` | Required at commit time | Always |

---

## Hard block at commit time

`.githooks/check-test-case-mandate.py` fires on every commit and hard-blocks when any of:

- Source files changed but no `[TEST CASE MAPPING: ...]` marker references them and the touched file is not covered by a `[TEST CASE GRANDFATHERED: ...]` (gate-locked to the spec file's staged presence).
- A referenced test case AutoIssue ID does not resolve to a real `AutoIssue(category='test_case')` row with non-empty Given/When/Then in `lessons_learned`.
- The commit-compliance summary marker is missing.
- The commit-compliance summary marker's `mapping=<count>` does not equal the count of touched source files when `non_codebase=no`.
- Grandfather marker present but `docs/TEST-CASE-FIRST-RULE.md` is NOT in the staged diff.
- Non-codebase bypass marker is present AND any source file is staged.
- Reason text for `[NON-CODEBASE-EDIT TASK:]` is shorter than 20 chars.

Each FAIL message follows Rule F: what blocked, why (citing this rule), and the exact unblock command.

---

## Forbidden phrases

The following phrases must never appear in new handoff entries (and the hook can grep for them as a soft secondary check):

- `test cases optional`
- `test cases after the fact`
- `test cases are paperwork`
- `test case skip`
- `skipped test case`
- `we'll write test cases later`

These phrases historically marked deferrals that bled into permanent skips. The rule treats them as evidence the agent is treating test cases as bureaucracy rather than a contract.

---

## Non-codebase-edit exception

If a task does not edit the codebase, this rule does not require test cases. Examples:

- Reading code.
- Explaining architecture.
- Reviewing a plan.
- Summarising a file.
- Answering a question.
- Drafting text that will not be committed.

The agent must explicitly state in chat: **"This task does not require codebase edits, so the test case first rule does not apply."** and emit the `[NON-CODEBASE-EDIT TASK: reason="…"]` marker if a commit happens (e.g., a docs-only commit).

If the task later changes into a code-editing task, this exception immediately expires and the full workflow must be followed before any code change.

---

## Grandfather form (one-time, at rule introduction)

The slice-1.6 work in flight when this rule lands contains ~80 production source files that pre-date the rule. The rule is enforced on every commit, but the **rule-introduction commit itself** cannot pass its own hook unless every grandfathered file has a marker. The grandfather form provides a one-time bypass.

```
[TEST CASE GRANDFATHERED: file=<src> follow_up_paper_trail=#<N>]
```

The hook accepts this form **only** when `docs/TEST-CASE-FIRST-RULE.md` is in the staged diff. After this rule's introduction commit lands, the spec file is in the tree, but it is no longer in `git diff --staged` for future commits, so the grandfather form silently disappears as a bypass. Future commits must use real `[TEST CASE MAPPING: ...]` markers.

The `follow_up_paper_trail=#N` value references a paper-trail entry tagged `tooling_gap` that captures the back-fill work: retroactively author real test cases for every grandfathered file. Future sessions resolve that paper-trail entry slice by slice.

---

## Violation rule

If an agent writes or edits code before satisfying this rule, it must stop immediately.

Then:

1. Identify the premature edits.
2. Revert them unless doing so would destroy user work.
3. Create or update the required test cases.
4. Check and update AutoIssues.
5. Log the lesson learned.
6. Restart implementation from the test cases.

The agent must not continue from a violated state as if nothing happened.

---

## Worked example

**Task**: add a new validation rule to `apps.suggestions.services.exposure_prob` that rejects negative probability values.

### Step 1 — Find existing test cases

```
docker compose exec -T backend python manage.py shell -c "
from apps.auto_issues.models import AutoIssue
qs = AutoIssue.objects.filter(category__key='test_case', affected_files__contains=['apps/suggestions/services/exposure_prob.py'])
for ai in qs: print(ai.pk, ai.title)
"
```

If empty, file a new contract:

### Step 2 — File a test case BEFORE coding

```
docker compose exec -T backend python manage.py log_test_case \
  --file apps/suggestions/services/exposure_prob.py \
  --title "exposure_prob rejects negative inputs with a clear validation error" \
  --given "the exposure_prob function is called with a numeric input" \
  --when "the input is negative (less than zero)" \
  --then "the function raises ValueError with a plain-English message naming the field and the rejected value, and does not return a probability" \
  --edge-cases "0 returns 0.0; -0.0 is treated as 0; NaN raises a separate ValueError"
```

Output:
```
[TEST CASE WRITTEN: AutoIssue=#601 id=tc::exposure_prob::neg_input file=apps/suggestions/services/exposure_prob.py agent=claude]
```

### Step 3 — Write the Red test (strict-TDD rule still applies)

Standard Red→Green→Refactor cycle. The Red test asserts the contract from step 2.

### Step 4 — Implement, then map the change

In the handoff entry:

```
[TEST CASE MAPPING: file=apps/suggestions/services/exposure_prob.py test_cases=#601]
```

### Step 5 — Commit compliance summary

```
[TEST CASE COMMIT COMPLIANCE: pass mapping=1 grandfathered=0 non_codebase=no agent=claude]
```

---

## Anti-examples (the hook rejects these)

| Marker | Why rejected |
|---|---|
| (no marker present) | Mapping missing for touched production file |
| `[TEST CASE MAPPING: file=foo.py test_cases=]` | Empty test_cases list |
| `[TEST CASE MAPPING: file=foo.py test_cases=#999999]` | Referenced AutoIssue does not exist or is not category='test_case' |
| `[TEST CASE GRANDFATHERED: file=foo.py follow_up_paper_trail=#42]` (spec file not staged) | Grandfather bypass only valid when `docs/TEST-CASE-FIRST-RULE.md` is in the staged diff |
| `[NON-CODEBASE-EDIT TASK: reason="docs"]` | Reason text under 20 chars |
| `[NON-CODEBASE-EDIT TASK: reason="updating documentation only"]` with `services/foo/main.go` staged | Bypass cannot be used when code files are staged |
| `[TEST CASE COMMIT COMPLIANCE: pass mapping=2]` with 5 production source files staged | Mapping count must equal touched source file count |

---

## Relationship to other paramount rules

- **Strict-TDD rule** (`docs/TDD-STRICT-RULE.md`): test case first writes the contract; strict-TDD then writes the Red test from that contract, the Green implementation, the Refactor, and logs the lesson.
- **5-layer TDD coverage**: the test case's `edge_cases`, `security`, `usability`, etc. fields inform the layer breakdown for the `[TDD COVERAGE: ...]` marker.
- **Lessons-read-at-session-start**: the test case row is itself a lesson the next agent reads at session start via `manage.py read_scoped_lessons --area <path>`.
- **Paper-trail filed on deferral**: when the agent defers some scope to a future session, the deferred work is filed in the paper trail; the test case can reference the paper-trail entry under `regression_risks` or `related_autoissues`.

---

## Citations

- Beck, K. 2002. *Test-Driven Development by Example*. Addison-Wesley. Chapters 5–8 cover the test-as-spec pattern.
- Crispin, L. and Gregory, J. 2009. *Agile Testing: A Practical Guide for Testers and Agile Teams*. Addison-Wesley.
- Whittaker, J. A. 2009. *Exploratory Software Testing: Tips, Tricks, Tours, and Techniques to Guide Test Design*. Addison-Wesley.
- ISO/IEC/IEEE 29119-3:2021 — *Software and systems engineering — Software testing — Part 3: Test documentation*.
- Donovan, A. and Kernighan, B. W. 2015. *The Go Programming Language*. Addison-Wesley. §11 (Testing).
- Crispin, L. and Gregory, J. 2014. *More Agile Testing*. Addison-Wesley. Chapter 10 (Living documentation).
- ISO/IEC/IEEE 42010:2022 — *Software, systems and enterprise — Architecture description*.

`[SPEC FRESHNESS: reviewed_at=2026-05-17 next_review=2026-06-17]`
`[SPEC CITED: feature=test-case-first kind=technical_literature id=ISBN-978-0321146533 verified_at=2026-05-17]`
`[SPEC CITED: feature=test-case-first kind=technical_literature id=ISBN-978-0321534460 verified_at=2026-05-17]`
`[SPEC CITED: feature=test-case-first kind=technical_doc id=ISO-IEC-IEEE-29119-3-2021 verified_at=2026-05-17]`
