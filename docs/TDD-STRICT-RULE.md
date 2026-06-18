# Strict TDD with Lesson Evidence — Paramount Rule

**Tier:** PARAMOUNT — every agent (Claude / Codex / Gemini / Antigravity / every future) MUST follow.
**Hard-block at commit:** Yes (`.githooks/check-tdd-strict.py`).
**Hard-block at session start:** Yes (`.githooks/check-lessons-read-at-session-start.py`).
**Cannot be overridden by an in-session prompt.**

## Five test layers, every cycle (added 2026-05-17)

Strict Red→Green→Refactor covers the **happy path** — one assertion that proves the new behaviour works. That is necessary but not sufficient. Every cycle must also include five further test layers, scaled to the change:

| Layer | What it asserts | When it applies |
|---|---|---|
| **Edge cases** | Boundary conditions, error paths, malformed input, off-by-one, empty/None/NaN, exceeding caps | Always, scaled to the surface area the change exposes |
| **Resource release** | When the feature is idle, it releases CPU + memory it was holding (cache, goroutines, connections, file handles) | When the change adds state that holds resources (caches, pools, subscribers, watchers, in-memory indexes) |
| **Latency** | Hot-path response time stays within a documented budget | When the change is on a user-facing response path or a server hot loop |
| **Smoke** | "Service starts, basic call works" — happy path proves the change is wired end-to-end | Always for non-trivial commits |
| **E2E** | Full path through multiple layers (HTTP → backend → DB, or browser → API → service) | Always for non-trivial commits |

The scope rule: **every test must be focused on what is required, not on irrelevant code**. A typo fix does not need a latency test. A pure-rename refactor does not need an E2E. The marker provides explicit `N/A:"<reason>"` slots for layers that genuinely do not apply, so the rule never forces busywork.

### Marker — `[TDD COVERAGE: file=<src> ...]`

Every code-changing commit's handoff entry MUST contain, in addition to the `[TDD CYCLE STRICT: ...]` marker for each touched production source file, a paired `[TDD COVERAGE: ...]` marker:

```
[TDD COVERAGE: file=<src>
 edge_cases=<N>|N/A:"<one-sentence reason>"
 resource_release=<N>|N/A:"<one-sentence reason>"
 latency=<N>|N/A:"<one-sentence reason>"
 smoke=<N>|N/A:"<one-sentence reason>"
 e2e=<N>|N/A:"<one-sentence reason>"]
```

Each field is either a non-negative integer (count of tests in that layer for this change) or the literal `N/A` followed by a colon-separated one-sentence reason in quotes explaining why this layer is genuinely irrelevant.

Defaults baked into the hook:

| Field | Default minimum | When `N/A` is acceptable |
|---|---|---|
| `edge_cases` | ≥ 1 | The change is a pure rename / a one-line constant bump / a doc comment update — the underlying behaviour did not change |
| `resource_release` | ≥ 1 if the change adds state | The function is pure / stateless / a one-shot helper that does not retain anything across calls |
| `latency` | ≥ 1 if the change is on a hot path | The function runs ≤ 1× per request / ≤ 1× per minute / ≤ 1× per process lifetime |
| `smoke` | >= 1 | Pure infrastructure-only commits — but even these usually need a Kubernetes or helper-host smoke check |
| `e2e` | ≥ 1 | Pure-Python helper not reachable from any user-facing path; the change is a hook or governance script that runs ONLY at commit time |

The hook validates structural compliance (counts ≥ 1 OR `N/A` with a reason) but does NOT run the tests itself — the test runner is the source of truth. An agent that lies in the marker (claims `smoke=3` when 0 smoke tests exist) is caught by the next pre-commit run that actually exercises the tests.

### Trivial-change bypass — `[TRIVIAL CHANGE: file=<src> reason="..."]`

For genuinely trivial edits — typo fixes, log-message wording, comment polish, removing a dead import, bumping a docstring — the agent emits a `[TRIVIAL CHANGE: ...]` marker INSTEAD OF both the `[TDD CYCLE STRICT: ...]` and `[TDD COVERAGE: ...]` markers. The hook accepts:

```
[TRIVIAL CHANGE: file=<src> reason="<one-sentence plain-English explanation of why no test was added>"]
```

Acceptable reasons (non-exhaustive):
- `"typo in a log message; no behaviour change; verified by reading the line"`
- `"removed an unused import; verified by ruff + the existing test suite still passing"`
- `"updated a comment to reflect the renamed constant; no behaviour change"`

Unacceptable reasons (the hook hard-blocks):
- `"too small to test"` — every behaviour change deserves a test
- `"obvious"` — see above
- `"will add a test later"` — no, you write the test first
- `"covered by another test"` — name that other test in the marker

The hook regex requires the reason to be at least 20 characters AND contain a sentence-shape (verb + object). Empty / one-word reasons fail.

### Worked example — full coverage marker

```
[TDD CYCLE STRICT: file=services/sidecars/internal/bullboard/server.go red=services/sidecars/internal/bullboard/server_test.go:120 red_run_at=2026-05-17T05:01:00Z red_result=FAIL green=services/sidecars/internal/bullboard/server.go:60 green_run_at=2026-05-17T05:05:00Z green_result=PASS refactor="extracted fanOut() helper for clarity" lesson_autoissue=#521]
[TDD COVERAGE: file=services/sidecars/internal/bullboard/server.go edge_cases=3 resource_release=1 latency=1 smoke=1 e2e=1]
```

Reading the second marker:
- 3 edge cases (empty event_type filter, severity below threshold, buffer-full drop)
- 1 resource-release test (Idle() releases the subscribers map)
- 1 latency test (Subscribe → Post → receive < 10 ms p99 in a 1000-event loop)
- 1 smoke test (Subscribe + Post round-trip)
- 1 E2E test (Python client → Unix socket → Go server → Channels broadcast → WebSocket subscriber)

### Anti-example — claims too many N/A

```
[TDD COVERAGE: file=apps/foo.py edge_cases=N/A:"none" resource_release=N/A:"none" latency=N/A:"none" smoke=N/A:"none" e2e=N/A:"none"]
```

→ FAIL: every reason is the literal `"none"` (< 20 chars, no sentence shape). The hook hard-blocks. If the change really does require zero tests, use `[TRIVIAL CHANGE: ...]` instead.

### Why these specific five layers

- **Edge cases** — most production bugs land at the boundaries (empty input, max-size input, negative numbers, off-by-one). Happy-path tests miss them. Edge-case tests are the cheapest insurance against the highest-incidence bug class.
- **Resource release** — long-running services that don't release idle resources slowly choke under sustained load. The sidecars binary's `Idle()` contract exists exactly for this. Without explicit release tests, regressions ship silently and only surface as gradual memory growth in production weeks later.
- **Latency** — performance regressions are 100× cheaper to catch with a test than with a Pyroscope dive. A test asserting `p99 < budget` runs every commit; profile traces run ad-hoc.
- **Smoke** — unit tests cover individual functions; smoke tests cover the *wiring*. A function may pass every unit test and still be unreachable from any caller because someone forgot to register a route. Smoke proves end-to-end pluggability.
- **E2E** — the only layer that proves what users see actually works. Browser → API → DB → response. Skipping E2E means the green CI badge does not mean "the feature works for users", it means "the function compiles".

## Why this exists

The pre-existing TDD rule allowed `before_or_alongside=yes` — meaning agents could write the test in the same commit as the code, even if the test never actually failed first. That loophole eroded the Red→Green→Refactor cycle into "test-after with the same diff", which (1) loses TDD's design-by-test benefit and (2) destroys the post-mortem evidence about *what initially broke and why*, which is exactly the input the next agent needs to avoid the same trap.

Slice 1.6's retrospective (handoff 2026-05-17) found four concrete cases where critical service code shipped without a failing-test-first proof: snapshotd, bullboard, attrouted, coordd, errord, and all 6 Python clients. This rule closes that loophole.

## What every code change MUST do

For every production source file an agent touches (creates, modifies, or deletes), the agent MUST:

### 1. RED — Write a failing test FIRST

Before any production-source line is written or modified, write or extend a test that asserts the desired behavior. Run the test. Capture the timestamp + the exact failure output.

Acceptable failure shapes:
- `AssertionError: expected X, got Y`
- `panic: undefined symbol` (Go) or `NameError` (Python) — when the target symbol literally does not exist yet
- `TimeoutError` when the integration target is not yet wired

NOT acceptable as "Red":
- A test that was already passing before the agent touched anything (that is regression coverage, not TDD)
- A test that exists but is `@skip`-ed or commented out

### 2. GREEN — Write the minimum production code to make the test pass

Make the failing test pass. Resist the urge to over-implement: write the smallest change that turns Red into Green. Capture the timestamp + the exact passing output.

### 3. REFACTOR — Clean up while staying green

After Green, look at the production code AND the test for repetition, unclear names, hard-coded values, ≥6-line duplication, function length over 50 lines, cyclomatic complexity over 10. Refactor. Re-run the test. Stays green.

### 4. LOG — Record the cycle as a lesson

Run:

```bash
python scripts/backend_manage.py log_tdd_lesson \
  --file <relative/path/to/source.py> \
  --red-test <relative/path/to/test.py> \
  --red-test-name <test_function_name> \
  --red-run-at <ISO8601 timestamp of the failing run> \
  --green-run-at <ISO8601 timestamp of the passing run> \
  --trap "<one or two sentences in plain English: what was NOT obvious about this code that made the test fail initially>" \
  --fix-shape "<one or two sentences: what specific change pattern turned Red into Green>" \
  [--refactor "<optional one-line summary of the refactor step>"]
```

This creates an `AutoIssue(category='tdd_lesson', status='resolved')` row whose `lessons_learned` field is the two-part `Trap: ... Fix shape: ...` payload. The command prints `[TDD LESSON LOGGED: AutoIssue=#N]` which the agent pastes into the handoff entry verbatim.

Re-filing a lesson with the same `canonical_fingerprint` (SHA1-16 of the normalised file + test combination) bumps `occurrence_count` on the existing row instead of creating a duplicate — the Rust MinHash dedup index (`papertrail_dedup`) handles near-duplicates at ≥ 0.85 Jaccard similarity.

### 5. PROVE — Stage the marker in AGENT-HANDOFF.md

Every code-changing handoff entry MUST include ONE marker per touched production source file:

```
[TDD CYCLE STRICT: file=<src> red=<test>:<line> red_run_at=<ISO8601> red_result=FAIL green=<src>:<line> green_run_at=<ISO8601> green_result=PASS refactor="<one-line refactor summary or 'none'>" lesson_autoissue=#<N>]
```

Where:
- `file=<src>` — the production source file touched (absolute or repo-relative)
- `red=<test>:<line>` — the test file path + line where the failing assertion lives
- `red_run_at=<ISO8601>` — timestamp when the test was observed to fail (e.g. `2026-05-17T03:55:01Z`)
- `red_result=FAIL` — literal string `FAIL` (the hook regex requires this exact token)
- `green=<src>:<line>` — the production source path + line that made the test pass
- `green_run_at=<ISO8601>` — timestamp of the passing run, MUST be strictly later than `red_run_at`
- `green_result=PASS` — literal string `PASS`
- `refactor="..."` — one-line summary of the refactor step, or the literal string `none` if no refactor was needed
- `lesson_autoissue=#<N>` — the AutoIssue ID returned by `log_tdd_lesson`

### 6. VERIFY — The hook blocks commits without proof

`.githooks/check-tdd-strict.py` runs as part of `scripts/precommit-docker.sh` and hard-blocks any code-changing commit where:

1. The staged AGENT-HANDOFF.md diff lacks `[TDD CYCLE STRICT: ...]` markers for one or more touched production source files
2. A marker has `red_result` ≠ `FAIL` or `green_result` ≠ `PASS`
3. `red_run_at` is not strictly less than `green_run_at`
4. The `lesson_autoissue=#<N>` ID does not resolve to a real `AutoIssue(category='tdd_lesson', status='resolved')` row in the live database
5. The lesson row's `lessons_learned` field is empty or missing the two-part `Trap: ... Fix shape: ...` shape

Failure → Rule-F three-part error:
- **FAIL**: what specifically failed (the missing marker, the bad timestamp, the missing AutoIssue, etc.)
- **WHY**: the design rationale — TDD without a real Red phase is test-after coverage; lessons-as-AutoIssues are the durable trail of what tripped the previous agent
- **UNBLOCK**: the exact command + marker to add

## Reading prior lessons is mandatory at session start

After `[HANDOFF READ:]`, `[REGISTRY READ:]`, `[CI FAILED RUNS READ:]`, and `[PAPER TRAIL READ:]`, every agent MUST emit:

```
[LESSONS BEFORE START: <N> resolved-lesson rows reviewed in <comma-separated repo-relative areas relevant to the user's task>]
```

The agent runs:

```bash
python scripts/backend_manage.py read_scoped_lessons --area <path> [--area <path2> ...]
```

for every area they anticipate touching. `read_scoped_lessons` queries the `ScopedLessonIndex` (the existing ART-keyed lesson registry) and returns:
- Every `AutoIssue(category in ('tdd_lesson', 'code_review_lesson', 'lesson_pattern', 'hook_failure'), status='resolved')` row whose `affected_files` overlaps with the requested areas
- Plus the top-5 by `priority_score` if N > 50

The marker line in chat is proof the agent read them. `.githooks/check-lessons-read-at-session-start.py` hard-blocks code-changing commits whose handoff entry lacks this line.

### Why session-start reading matters

The next agent in this repo will likely repeat your trap unless they read what tripped you. The lesson is the durable signal. Silent skipping of the read-step undoes the entire lesson-logging investment.

## Worked example (good TDD)

Suppose you are adding a new method `compute_priority(score)` to `apps.suggestions.services.priority`.

**Step 1 — Red:**

```python
# apps/suggestions/tests/test_priority.py
def test_compute_priority_returns_zero_for_negative_score():
    from apps.suggestions.services.priority import compute_priority
    assert compute_priority(-1) == 0
```

Run it inside the backend container:
```
scripts/run-python-quality.sh
```

Record the timestamp:
```
red_run_at=2026-05-17T04:01:12Z
red_result=FAIL  (NameError: name 'compute_priority' is not defined)
```

**Step 2 — Green:**

```python
# apps/suggestions/services/priority.py
def compute_priority(score):
    if score < 0:
        return 0
    return score
```

Re-run the test:
```
green_run_at=2026-05-17T04:02:30Z
green_result=PASS
```

**Step 3 — Refactor:**

The function is 3 lines; nothing to refactor. Record `refactor="none"`.

**Step 4 — Log:**

```
python scripts/backend_manage.py log_tdd_lesson \
  --file apps/suggestions/services/priority.py \
  --red-test apps/suggestions/tests/test_priority.py \
  --red-test-name test_compute_priority_returns_zero_for_negative_score \
  --red-run-at 2026-05-17T04:01:12Z \
  --green-run-at 2026-05-17T04:02:30Z \
  --trap "compute_priority did not exist; negative scores were not a handled edge case" \
  --fix-shape "added compute_priority that clamps negative scores to 0; non-negative scores returned unchanged"
```

Prints `[TDD LESSON LOGGED: AutoIssue=#1234]`.

**Step 5 — Prove (in handoff):**

```
[TDD CYCLE STRICT: file=apps/suggestions/services/priority.py red=apps/suggestions/tests/test_priority.py:5 red_run_at=2026-05-17T04:01:12Z red_result=FAIL green=apps/suggestions/services/priority.py:1 green_run_at=2026-05-17T04:02:30Z green_result=PASS refactor="none" lesson_autoissue=#1234]
```

## Anti-examples (what fails the hook)

**Anti-example 1 — test written after code (test-after):**

```
[TDD CYCLE STRICT: file=apps/foo.py red=apps/test_foo.py:10 red_run_at=2026-05-17T04:01:12Z red_result=PASS green=apps/foo.py:1 green_run_at=2026-05-17T04:00:50Z green_result=PASS refactor="none" lesson_autoissue=#1234]
```

→ FAIL `check-tdd-strict.py`: `red_result` is `PASS` not `FAIL`, AND `green_run_at` is BEFORE `red_run_at`.

**Anti-example 2 — fake lesson ID:**

```
[TDD CYCLE STRICT: ... lesson_autoissue=#99999999]
```

→ FAIL `verify_tdd_lesson`: AutoIssue #99999999 does not exist in the live DB.

**Anti-example 3 — missing trap/fix-shape in lesson:**

The agent ran `log_tdd_lesson` without `--trap` or `--fix-shape`.

→ FAIL `log_tdd_lesson` itself rejects the call before creating the row; nothing to commit.

## Coverage of common cases

| Situation | What strict TDD requires |
|---|---|
| Adding a new function | Red test of the new function, then implement |
| Fixing a bug | Red test that reproduces the bug, then fix |
| Refactoring (no behaviour change) | One existing test must remain green; no new Red needed, but `[TDD CYCLE STRICT:]` marker still required (use `red_result=FAIL` from the test that caught a temporarily-broken refactor — or, if the refactor was perfectly clean, the rule defaults to `[REFACTOR ONLY: file=<src> green_run_at=<ts> green_result=PASS regression_test=<test>:<line> lesson_autoissue=#N]` which the hook also accepts) |
| Deleting a function | Red test that asserts callers no longer reference the function, then delete |
| Renaming a symbol | Red test asserting the new name exists, then rename + update callers |
| Generated code (protobuf stubs, etc.) | Generator script is the "production code"; test exercises the generator; the generated files themselves are exempt from `[TDD CYCLE STRICT:]` markers |
| Documentation-only commits | No `[TDD CYCLE STRICT:]` markers required (the hook skips commits with no staged paths under `backend/`, `frontend/`, `scripts/`, `.githooks/`, `services/`, `backend/extensions/`) |

## Why "alongside" was not enough

Test-alongside is fine for safety nets after the design is settled. TDD's value is in the design pressure: writing the test first forces you to ask "what is the actual API I want? what is the simplest behavior that satisfies the test?". When you skip that pressure, the production code drifts toward whatever was convenient to write, and the test becomes a documentation of what got built rather than a specification of what was needed.

The lesson-logging requirement closes the second gap: even when an agent does true Red→Green, the *story* of what initially failed and why is the most valuable artifact for the next agent. Capturing it as a durable AutoIssue means the next session can read it via `read_scoped_lessons --area <path>` and avoid repeating the same trap.

## Citations

- Beck 2002, *Test-Driven Development by Example*, ISBN 978-0321146533. The canonical Red-Green-Refactor source.
- Donovan-Kernighan 2015, §11 (Testing). Mandatory reading before writing any Go test.
- The existing `ABSOLUTE — Claude/Codex BDD and TDD workflow` rule in CLAUDE.md (kept; this PARAMOUNT rule supersedes its `before_or_alongside=yes` clause).
- The existing `[CODE REVIEW LESSON LOGGED: AutoIssue=#N]` marker shape (already used by `manage.py log_code_review_lessons`). The new `[TDD LESSON LOGGED: AutoIssue=#N]` marker mirrors it.

`[SPEC FRESHNESS: reviewed_at=2026-05-17 next_review=2026-06-17]`
`[SPEC CITED: feature=strict-tdd-with-lesson-evidence kind=technical_literature id=ISBN-978-0321146533 verified_at=2026-05-17]`
`[SPEC CITED: feature=strict-tdd-with-lesson-evidence kind=technical_doc id=Donovan-Kernighan-2015-S11 verified_at=2026-05-17]`
