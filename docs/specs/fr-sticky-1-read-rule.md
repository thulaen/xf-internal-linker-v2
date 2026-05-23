# FR — Sticky #1 Read Rule (Spec-Driven Gradual Rewrite Policy)

[SPEC FRESHNESS: reviewed_at=2026-05-23 next_review=2026-06-23]

[SPEC CITED: feature=sticky-1-read-rule kind=academic_paper id=beck-2002-tdd verified_at=2026-05-23]
[SPEC CITED: feature=sticky-1-read-rule kind=academic_paper id=parnas-1972-modularity verified_at=2026-05-23]
[SPEC CITED: feature=sticky-1-read-rule kind=technical_doc id=iso-iec-ieee-42010-2022 verified_at=2026-05-23]
[SPEC CITED: feature=sticky-1-read-rule kind=technical_doc id=beyer-sre-2016 verified_at=2026-05-23]

## Summary

Sticky #1 of the Paper Trail is the Spec-Driven Gradual Rewrite Policy.
It is a standing-orders document with an abstract up to 10,000 words
(versus the 1,200-word cap on every other status). The sticky is
**ever-evolving between sessions and frozen mid-session**: between
sessions, the user or any agent may amend it via an edit-commit that
carries a `[STICKY 1 EDIT: ...]` marker; mid-session, the sticky is
the SHA-256 the agent read at session start, so an in-session amend
cannot retroactively change the constraints the session was bound to.

Every code-changing commit from this rule's installation onward MUST
carry a `[STICKY 1 READ: timestamp=<ISO8601> sha256=<16-char-prefix>
agent=<name>]` marker in the staged `AGENT-HANDOFF.md` entry. The
marker proves the agent ran `manage.py read_sticky --id 1` in this
session and received the sticky's full body, not a memory cache or a
paraphrase. The marker's SHA-256 prefix is cross-checked against the
current sticky body by `.githooks/check-sticky-1-read.py`; if the
prefix is stale (the sticky has been amended since the agent read it),
the hook hard-blocks and prompts the agent to re-read.

## Why

Past sessions repeatedly drifted from the documented discipline because
the only enforcement of "read the policy before writing code" was the
agent's promise that they had done so. A SHA-256-verified database read
removes the promise from the loop: the agent either has the marker, or
the commit blocks. The 10,000-word cap acknowledges that some
standing-orders documents need genuine room — the policy text the user
supplied for Sticky #1 is 8,529 words, well above the 1,200-word cap
that applies to ordinary deferral abstracts.

## Behavior

The read mechanism has three parts:

### 1. The read command

`docker compose exec -T backend python manage.py read_sticky --id 1`

* `--id <N>` is a 1-based sticky-sequence number (not the paper_trail
  row primary key). `--id 1` means "the first sticky filed", `--id 2`
  the second, and so on. This makes the rule's `--id 1` convention
  stable as new stickies arrive.
* The command prints the full sticky body to stdout, then a banner
  with the sticky's last-updated timestamp and SHA-256 prefix, then a
  single line of the form `[STICKY 1 READ: timestamp=<ISO8601>
  sha256=<16-char-prefix> agent=<name>]`.
* The agent name is read from the `XF_AGENT_NAME` environment variable
  (default `claude`).
* The command appends an audit row to `audit/sticky_reads.jsonl`
  recording every invocation.
* `--print-sha-only` prints just the 16-char SHA-256 prefix (used by
  the hook to cross-check the staged marker).
* The command exits non-zero if the sticky-sequence number is out of
  range, if the matched row has a status other than `sticky`, or if
  the database is unreachable.

### 2. The read marker

The agent copies the `[STICKY 1 READ: ...]` line verbatim into the
current `AGENT-HANDOFF.md` entry. The marker is placed immediately
after the existing `[REGISTRY READ: ...]` marker (Priority 1) and
before `[GUIDELINES READ: ...]` (Priority 3). Reformatting,
abbreviating, or paraphrasing the marker is a protocol violation.

### 3. The pre-commit hook

`.githooks/check-sticky-1-read.py` fires after `check-paper-trail-read`
in `scripts/precommit-docker.sh`. The hook scans the staged
AGENT-HANDOFF.md diff for the `[STICKY 1 READ: ...]` marker and
compares the marker's SHA-256 prefix against the live sticky body via
`manage.py read_sticky --id 1 --print-sha-only`. Two exemption markers
short-circuit the check:

* `[STICKY 1 BOOTSTRAP: commit=introduces-sticky]` — applies to the
  single commit that introduces Sticky #1 itself.
* `[STICKY 1 EDIT: previous_sha=<prefix> new_sha=<prefix> reason="..."]`
  — applies to a commit that amends the sticky body.

Pure-docs commits (no files under `docs/specs/`, `docs/adr/`,
`backend/`, `frontend/`, `services/`, `scripts/`, or `.githooks/`) are
exempt because they cannot introduce structural drift the sticky
governs. The hook does not have a skip exit; the pre-push hook catches
`--no-verify` bypasses.

## Source backing

* **Beck, K. (2002).** *Test Driven Development: By Example.* Addison-
  Wesley. ISBN 978-0321146533. Establishes the discipline of "test
  first, then code" that the sticky enforces. The read-gate ensures
  the discipline is checked before each code edit, not after.
* **Parnas, D.L. (1972).** *On the Criteria To Be Used in Decomposing
  Systems into Modules.* Communications of the ACM 15(12):1053-1058.
  doi:10.1145/361598.361623. Establishes the modularity principles
  the sticky's "Domain Partitioning Constraint" and "Language
  Ownership" sections enforce.
* **ISO/IEC/IEEE 42010:2022.** *Systems and software engineering —
  Architecture description.* Defines architecture-description
  requirements that the sticky's "Architecture as Hypothesis" and
  "Architectural Decision Records" sections honor.
* **Beyer, B., Jones, C., Petoff, J., Murphy, N.R. (2016).** *Site
  Reliability Engineering: How Google Runs Production Systems.*
  O'Reilly. ISBN 978-1491929124. Establishes the observability
  discipline the sticky's "Observability Stack Health Feeds AutoIssues"
  section adapts to local dev.

## Behavior tests

`.githooks/test_check_sticky_1_read.py` covers 7 scenarios:

1. Marker present + SHA prefix matches the live sticky body → exit 0.
2. Marker missing on a code-changing commit → hard-block.
3. Marker present but SHA prefix is stale → hard-block with a
   "re-read and re-paste" prompt.
4. `[STICKY 1 BOOTSTRAP: ...]` exemption on the sticky-introducing
   commit → exit 0.
5. `[STICKY 1 EDIT: ...]` exemption with matching previous/new SHAs
   → exit 0.
6. Pure-docs commit (no code files staged) → exit 0.
7. Code-changing commit with no AGENT-HANDOFF.md staged → hard-block.

Tests stub the SHA-fetch subprocess via `unittest.mock.patch` so no
live Docker call is needed.

## Rollout

This commit (Phase K.1) installs the rule, the model schema change,
the migration, the management commands, the hook, the tests, the
sticky entry itself, and the rule paragraphs in
`CLAUDE.md`/`AGENTS.md`/`CODEX.md`/`GEMINI.md`. Every subsequent
commit runs under the rule.
