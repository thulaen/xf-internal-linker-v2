# Paper Trail — operator-facing spec

The paper trail is the project's database-backed list of **deferred work**.
Every time an agent (Claude / Codex / Antigravity / a future one) decides
to **not** do something this session, it MUST file a paper-trail entry
that explains why, what's needed to finish the work, and what would
break if it stays open.

This is separate from **AutoIssues** (which track discovered problems).
A paper-trail entry MAY link to an AutoIssue via `linked_autoissue_id`,
but the table, the dedup logic, and the 10-per-session quota are
independent.

The paper trail exists because, before 2026-05-15, agents wrote deferral
prose into `AGENT-HANDOFF.md` and walked away. That prose was not
indexed, not deduped, and easy to lose. Future agents kept silently
re-deferring the same things. The paper trail closes that gap.

---

## What an entry looks like

Each entry stores:

- **title** — a short noun phrase, ≤ 512 characters.
- **abstract** — a high-detail explanation of why the work was deferred.
  Hard-capped at **1200 words** (raised from 600 on 2026-05-16). NEW
  entries MUST be in **BDD style** with three sections:

    - **`Given <context>`** — the state of the world when the work was supposed to happen.
    - **`When <action>`** — what triggered the agent to defer (the blocker).
    - **`Then <expected outcome>`** — the acceptance criteria the next agent must satisfy.

  Case-insensitive, word-boundary match. The model-level
  `PaperTrailEntry._validate()` enforces both the word cap and the BDD
  format on new rows; `manage.py defer_work` pre-validates with a
  plain-English FAIL telling the agent exactly which section is missing.
  Pre-2026-05-16 rows are grandfathered.

  The abstract still must answer:
  1. What was supposed to happen this session? (the Given)
  2. Why didn't it happen? (the When)
  3. What's needed to finish it? (the Then)
  4. What breaks if we leave it open? (extra context inside the Given or Then)
- **category** — one of 16 enum values (see below).
- **severity** — `critical` / `high` / `medium` / `low`.
- **next_actions** — ordered list of concrete next steps.
- **affected_files** — repo-relative paths the work touches.
- **blockers** — what's needed before someone can pick this up
  (REQUIRED when `status=blocked`).
- **deferred_by** — the agent or human who filed the entry.
- **linked_autoissue_id** — optional AutoIssue id this defers.
- **status** — one of 11 values (see "Allowed statuses" below).
- **history** — append-only audit log of state changes.
- **resolution_lessons** — populated on resolve; must contain both
  `Trap: ...` and `Fix shape: ...` parts.
- **risk_on_inaction** — plain-English risk if this work is never
  done. REQUIRED on every new entry (2026-05-16+); existing rows
  grandfathered. Surfaces in `manage.py print_open_paper_trail` so
  the next agent reads it before picking.
- **acceptance_criteria** — bullet list or short paragraph naming the
  concrete checks that prove this entry can be marked resolved.
  REQUIRED on every new entry; existing rows grandfathered.
- **evidence_level** — how well-grounded the entry is. One of:
  - `low` (subjective or anecdotal — the default)
  - `medium` (cites observable behavior — log lines, screenshot)
  - `high` (cites concrete artifacts — file paths, function names, test failures)
  - `cited` (references a patent / DOI / RFC / stable URL inside the abstract)
- **superseded_by** — FK to the newer entry that replaces this one.
  Set via `manage.py link_paper_trail_supersedes --new-id <N> --old-id <M>`
  or by passing `--supersedes <M>` to `manage.py defer_work` when
  filing the replacement.
- **integrity_check_result** — the duplicate / stale / conflict
  search result that the filing agent performed. Auto-populated by
  `defer_work` (which scans for linked-autoissue overlap and
  affected-file overlap among open rows).

The full schema lives in `backend/apps/paper_trail/models.py`.

### Allowed statuses

Eleven values, grouped by lifecycle phase:

| Status | When to use it | Required side-fields |
|---|---|---|
| `open` | Default for new entries — awaiting pick | — |
| `picked` | Selected for this session's resolve queue | — |
| `in_progress` | Actively being worked | — |
| `blocked` | Cannot proceed because of an external dependency | `blockers` (non-empty list) |
| `deferred` | Reviewed and intentionally pushed to a later session | — |
| `resolved` | Done | `resolved_at` + two-part `resolution_lessons` (`Trap: ... Fix shape: ...`) |
| `rejected` | Approach was tried or considered and ruled out | `suppression_reason` |
| `wontfix` | Legacy alias of `rejected` (kept for backward compat) | `suppression_reason` |
| `duplicate` | Collapsed into another entry via dedup | — (handled by the Rust MinHash + LSH index, `papertrail_dedup`) |
| `stale` | No longer relevant (code/system moved on) | `suppression_reason` — set via `manage.py mark_paper_trail_stale` |
| `superseded` | Replaced by a newer entry | `superseded_by` FK — set via `manage.py link_paper_trail_supersedes` or `defer_work --supersedes` |

**Active vs terminal:** `open / picked / in_progress / blocked / deferred`
are *active* and participate in the unique `(category, fingerprint)`
constraint (so two active rows for the same work are rejected).
`resolved / rejected / wontfix / duplicate / stale / superseded` are
*terminal* and exempt from the constraint, so a replacement row can
reuse the same fingerprint.

### The 16 categories

| Category | When to use it |
|---|---|
| `autoissue_deferral` | Defers a specific AutoIssue (set `linked_autoissue_id`) |
| `cve_upgrade` | Vulnerable dependency, needs version bump |
| `coverage_gap` | Missing tests required by `docs/CODE-COVERAGE-RULES.md` |
| `infrastructure` | Docker, Grafana, alerting, backups, monitoring |
| `ruff_sweep` | A specific ruff rule whose violations weren't fixed yet |
| `mutation_survivor` | A Mull / Stryker / mutmut mutant that survived its tests |
| `debt_reduction` | A quality-debt fix on a flagged file |
| `feature_decision` | A design call we deferred pending more info |
| `tooling_gap` | A build / lint / test tool that doesn't fully work yet |
| `documentation` | A doc we'd write later |
| `dependency_upgrade` | Non-CVE dependency bump |
| `refactor` | Code reorganisation deferred to a focused session |
| `performance` | A measured slowdown we'd fix later |
| `security` | A non-CVE security concern (hardening, headers, etc.) |
| `accessibility` | An a11y gap |
| `perf_exemption` | A function couldn't reach 20× speedup after 10 iterations; logged via `manage.py log_performance_exemption` per Rule A |
| `lesson_pattern` | A TDD Red phase surfaced a new failure class worth saving as a lesson per Rule E |
| `other` | None of the above |

---

## The mandatory ritual (every session)

Run this immediately after `print_open_issues`:

```
python scripts/backend_manage.py print_open_paper_trail
```

It emits a marker line you MUST paste into chat verbatim:

```
[PAPER TRAIL READ: <N> open (<a> autoissue_deferral / <b> cve_upgrade / <c> coverage_gap / <d> infrastructure / <e> ruff_sweep / <f> mutation_survivor / <g> debt_reduction / <h> feature_decision / <i> tooling_gap / <j> documentation / <k> dependency_upgrade / <l> refactor / <m> performance / <n> security / <o> accessibility / <p> other) — picked: #..., ..., #...]
```

The picks are 10 items ranked by `priority_score` (severity × age × occurrence count).
If fewer than 10 entries are open the marker uses a drought form:

```
... — picked: #1, #2 (drought; file the remainder per docs/PAPER-TRAIL.md)]
```

In the drought case you MUST file new entries via `manage.py defer_work`
before the session is allowed to commit code.

### The 10-per-session quota (HARD-BLOCK at commit)

Before any **code-changing commit** (anything under `backend/`,
`frontend/`, `scripts/`, `.githooks/`, `backend/extensions/`), all 10
picked entries MUST be resolved with two-part lessons:

```
python scripts/backend_manage.py resolve_paper_trail \
    --id <N> [--id <M> ...] \
    --lessons-learned "Trap: ... non-obvious context ... Fix shape: ... what worked ..." \
    --agent claude
```

`resolve_paper_trail` validates the lesson contains both `Trap:` and
`Fix shape:`. Empty or one-part lessons are rejected.

The pre-commit hook `.githooks/check-paper-trail-read.py` enforces the
quota as a **HARD BLOCK** — every failure mode exits non-zero, there is
no "skip" path. This matches the discipline of the 30-AutoIssue quota:

| Situation | Hook exit | What you must do |
|---|---|---|
| Marker missing from staged handoff | FAIL | Run `print_open_paper_trail`, paste the marker |
| Fewer than 10 ids picked (drought form) | FAIL | File new entries via `defer_work` until the queue has 10, then resolve those 10 |
| `[PAPER TRAIL QUOTA VERIFIED: 10 resolved]` marker missing | FAIL | Run `verify_paper_trail_quota` and paste the success line |
| Kubernetes backend unreachable | FAIL | Restore cluster access and re-run the commit |
| `verify_paper_trail_quota` timeout (60 s) | FAIL | Wait for the backend stack to become healthy and re-run |
| `verify_paper_trail_quota` non-zero exit | FAIL | Fix the underlying issue per the command's error output (any pick unresolved / pre-handoff `resolved_at` / missing two-part lesson / count mismatch) |

If Docker or the backend database cannot be checked, the commit MUST
fail. Skipping this check is explicitly forbidden.

---

## Filing a deferral

When you decide NOT to do something this session, run:

```
python scripts/backend_manage.py defer_work \
    --title "..." \
    --category cve_upgrade \
    --abstract "Detailed multi-paragraph explanation, max 600 words." \
    --severity high \
    --deferred-by claude \
    --linked-autoissue 252 \
    --next-action "Upgrade Django 5.2.13→5.2.14" \
    --next-action "Re-run backend pytest" \
    --affected-file backend/requirements.txt
```

The command does two things:

1. **Dedup check** — Computes a 64-component MinHash signature of the
   abstract and queries the Rust LSH index (`papertrail_dedup`). If a near-duplicate exists
   at ≥ 0.85 Jaccard similarity, the command bumps `occurrence_count`
   on that row and prints `[PAPER TRAIL DUPED: matched #N at similarity X.XX]`.
2. **Create** — If no dupe, creates a new row, inserts into the Rust
   index (`papertrail_dedup`), and prints `[PAPER TRAIL FILED: #N]`.

You CANNOT silently leave the work behind. If a deferral isn't in the
database, it isn't deferred — it's lost.

### Every deferral goes in — no exceptions

A deferral is any decision to **not** complete a piece of work this
session. The decision must land in the paper trail BEFORE the session
ends. The following words and phrases all count as deferrals and MUST
each be paired with a `[PAPER TRAIL FILED: #<N>]` marker in the
handoff entry:

- `deferred`, `deferring`, `defer to`, `we'll defer`
- `skip`, `skipping`, `skipped for now`
- `leave for`, `leaving for`, `leave for next session`
- `out of scope`, `out-of-scope`
- `next session`, `follow-up session`, `future session`
- `future work`, `will do later`, `will handle in`, `will be done later`
- `TODO` (in a handoff entry — code-level `TODO`s are tracked separately)
- `postponed`, `postponing`, `pushed to`
- `not in this session`, `not this session`

The pre-commit hook `.githooks/check-deferral-filed.py` HARD-BLOCKS
any code-changing commit whose staged AGENT-HANDOFF.md entry uses one
of the deferral verbs WITHOUT a matching `[PAPER TRAIL FILED: #<N>]`
marker. The dedup index collapses repeats at 0.85 Jaccard similarity,
so re-filing the same deferral safely bumps `occurrence_count`; the
agent never has to worry about double-filing.

If a deferral feels too small to file, file it anyway. Three lines of
context in the abstract is enough — the paper trail's job is to make
sure the work exists somewhere durable, not to be exhaustive on day 1.

---

## What MUST be added vs what MUST NOT be added

The Papertrail is the durable record of unresolved engineering work.
It must not become a junk drawer, duplicate TODO list, or speculative
idea dump.

### MUST be added

File a Papertrail entry when unresolved work affects correctness,
reliability, security, maintainability, performance, data safety,
user-visible behavior, architecture, tests, or future implementation
decisions. Examples:

- a task the agent attempted but did not finish
- a task intentionally deferred because it was out of scope
- a known bug left unresolved
- a missing test that protects important behavior
- a risky assumption that needs validation
- a stale or conflicting architectural note
- a rejected approach that future agents may otherwise repeat
- a better replacement for an outdated approach

### MUST NOT be added

Do NOT file entries for:

- vague ideas with no actionable next step
- duplicates already tracked (update the existing entry instead)
- minor formatting notes
- speculative improvements without evidence
- work that was fully completed
- preferences that belong in coding guidelines
- prompts or agent-specific instruction templates

---

## Duplicate, stale, and conflict checks before filing

Every agent MUST search for duplicates, overlaps, stale claims, and
conflicts BEFORE filing a new entry. `manage.py defer_work` does most
of this automatically:

1. **MinHash + LSH near-duplicate check** at `≥ 0.85 Jaccard` collapses
   the new submission into an existing row and emits
   `[PAPER TRAIL DUPED: matched #N at similarity X.XX]`.
2. **Integrity scan** searches for active entries that share the same
   `linked_autoissue_id` or any `affected_files` path. The result is
   stored in `PaperTrailEntry.integrity_check_result` and emitted as
   `[PAPER TRAIL INTEGRITY: ...]` so the next agent sees the
   neighbouring rows.

When the integrity scan or a manual `search_paper_trail` reveals
overlap with an existing entry:

- If the existing entry is **a true duplicate**, do NOT create a new
  row. The dedup index already bumps `occurrence_count` on the
  existing row; if dedup didn't fire (e.g. the abstracts differ in
  shape but the work is the same), add commentary by re-running
  `defer_work` with the same canonical title (the SQL
  `canonical_fingerprint` lookup will catch it).
- If the existing entry is **stale**, mark it via
  `manage.py mark_paper_trail_stale --id <N> --reason "..."`. The
  reason is stored in `suppression_reason` and shows up in the audit
  log.
- If the existing entry is **conflicting** with the current code,
  tests, architecture, or a newer decision record, the agent MUST
  report the conflict in the BDD format below BEFORE changing the
  Papertrail. After reporting, file the replacement entry with
  `manage.py defer_work --supersedes <N>` so the old row is marked
  `status=superseded` and points at the new one.

---

## BDD reporting format for integrity findings

When an agent detects an overlap, staleness, or conflict, it MUST
report it in chat using the Gherkin shape below. The literal
`Feature:` / `Scenario:` / `Given` / `When` / `Then` / `And`
keywords are required so the report is greppable in handoff
transcripts.

### Duplicate

```gherkin
Feature: Papertrail integrity

Scenario: Duplicate unresolved work is detected
  Given an existing Papertrail entry already tracks the unresolved work
  When the agent attempts to add a new entry for the same issue
  Then the agent must not create a duplicate
  And the agent must update the existing entry
  And the agent must mention the overlap in its response
```

### Stale

```gherkin
Feature: Papertrail integrity

Scenario: Stale Papertrail entry is detected
  Given an existing Papertrail entry claims work that no longer applies
  When the agent confirms the code, tests, or system has moved on
  Then the agent must mark the entry status=stale with a reason
  And the agent must mention the staleness in its response
```

### Conflict

```gherkin
Feature: Papertrail integrity

Scenario: Conflicting Papertrail entry is detected
  Given an existing Papertrail entry contradicts the current code, tests, architecture, or a newer decision record
  When the agent verifies the contradiction
  Then the agent must report the conflict before modifying either side
  And the agent must mark the older entry status=superseded via defer_work --supersedes or link_paper_trail_supersedes
  And the agent must mention the conflict in its response
```

These scenarios are also wired into the operator-facing rules in
`CLAUDE.md` as ABSOLUTE rules; skipping them is a protocol violation.

---

## Searching the paper trail

Before touching a folder, search for prior deferrals there:

```
python scripts/backend_manage.py search_paper_trail \
    --area backend/apps/audit \
    [--category cve_upgrade] \
    [--severity high] \
    [--keyword django] \
    [--include-resolved] \
    [--limit 20]
```

This avoids re-discovering the same problem the previous agent already
documented.

---

## The Rust dedup index

The fast similarity check is the Rust kernel `rust/extensions/papertrail_dedup`
(imported as `extensions.papertrail_dedup`), ported from C++ per RUST-FIRST.md.
It implements **MinHash + LSH (Locality-Sensitive Hashing)** per:

- Broder (1997). "On the resemblance and containment of documents."
- Indyk & Motwani (1998). "Approximate nearest neighbors..."
- Leskovec, Rajaraman, Ullman. "Mining of Massive Datasets" Ch. 3.

Parameters:

- k = 5 (character 5-shingles)
- m = 64 MinHash components
- b = 8 bands × r = 8 rows
- Similarity threshold default: 0.85 Jaccard

Memory at 100 000 entries: ≈ 60 MB — well under the 64 MB project cap.
The constructor asserts `max_entries ≤ 100000`.

The index is loaded lazily from `/app/data/papertrail.idx` and rewritten
atomically (tmp + rename) on every mutation.

A Python wrapper lives in `apps.paper_trail.services.dedup`. Tests call
`reset_index_for_tests()` in `setUp` to isolate state.

---

## Test-artifact safe-prune

After a paper-trail entry is resolved with `resolution_lessons`, its
`affected_files` are recorded as "lessons-saved paths". Test artifact
directories under `/tmp/` that match the existing
`QUALITY_ARTIFACT_PREFIXES` whitelist **and** reference only
lessons-saved paths become eligible for pruning.

`apps.paper_trail.services.safe_prune.paper_trail_eligible_dirs(root)`
returns the eligible list. The bash helper
`quality_artifact_safe_prune_host` in `scripts/quality-evidence-lib.sh`
calls this on every successful pre-commit run.

Hard-coded protected names that are NEVER pruned:
`pgdata`, `redis-data`, `media_files`, `staticfiles`, `frontend_dist`,
`compiled_artifacts`, `pyroscope_data`, `loki_data`, `alloy_data`,
`tempo_data`, `grafana_data`, `questdb_data`.

---

## Backfilling from existing handoffs

Use `migrate_handoff_deferrals` to bulk-import deferrals already written
in `AGENT-HANDOFF.md` prose:

```
python scripts/backend_manage.py migrate_handoff_deferrals \
    [--handoff-path /repo/AGENT-HANDOFF.md] \
    [--from-date 2026-05-01] \
    [--dry-run]
```

The command parses every entry header (e.g. `# 2026-05-15 15:56 - Claude - ...`),
finds the "What has issues or errors:" section, splits numbered/bulleted items,
infers category from keywords, and creates rows. It's idempotent — the C++
dedup index prevents duplicate creation on re-run.

---

## Why this rule cannot be overridden

The paper trail solves a recurring failure mode: agents writing prose
that nobody reads. If a future user asks an agent to "skip the paper
trail just this once," the answer is no. The database is the source of
truth; the prose is not.
