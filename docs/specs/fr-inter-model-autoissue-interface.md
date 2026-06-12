# FR - Inter-model AutoIssue coordination interface

[SPEC FRESHNESS: reviewed_at=2026-06-11 next_review=2026-07-11]
[SPEC CITED: feature=inter-model-autoissue-interface kind=technical_doc id=python-sqlite3 verified_at=2026-06-11]
[SPEC CITED: feature=inter-model-autoissue-interface kind=technical_doc id=sqlite-transaction-control verified_at=2026-06-11]
[SPEC CITED: feature=inter-model-autoissue-interface kind=technical_literature id=beck-tdd-2002 verified_at=2026-06-11]

## Problem

The user runs Codex, Claude, Gemini, and Antigravity in separate apps. When the
user types `solve autoissues` in one or more of those apps, each agent needs a
shared place to join, wait briefly for teammates, claim safe work, review fixes,
and agree who should stage the final commit. The tool must not launch more
agents by itself, must not create branches, and must not commit.

## Sources of truth

- `python-sqlite3` - Python's standard SQLite module. It provides a local
  database with transactions and no extra service to install.
- `sqlite-transaction-control` - SQLite's transaction behavior. The interface
  uses short write transactions so two agents cannot claim the same path at the
  same time.
- `beck-tdd-2002` - Kent Beck's test-driven development book. The interface is
  built with a failing test first, then the smallest passing implementation.

## Behaviour

- Given the first agent receives `solve autoissues`,
  When it joins the pool,
  Then the pool opens a 10-minute wait so the user can paste the same phrase into
  other apps.
- Given another agent joins during the 10-minute wait,
  When the wait closes,
  Then both agents belong to the same sprint team.
- Given an agent joins after a sprint has started,
  When the current sprint is active,
  Then the late agent joins the current sprint and can claim unowned work without
  taking another agent's locks.
- Given agents need to coordinate without sharing one chat window,
  When one agent posts a short message,
  Then the message is recorded in the shared pool and other agents can read the
  recent messages.
- Given two AutoIssues touch the same file or folder,
  When agents try to claim them,
  Then only one agent can own that overlapping area in that sprint.
- Given 30 AutoIssues are marked fixed,
  When the sprint target is reached,
  Then the sprint moves into a 15-minute cross-review phase.
- Given cross-review passes without correction requests,
  When the sprint has enough review agreement,
  Then the interface recommends one agent to stage the final commit but does not
  stage or commit.
- Given an agent spends longer thinking, testing, or reviewing,
  When it sends heartbeat updates,
  Then its live state is recorded and its issue/file locks stay leased.
- Given an agent goes quiet briefly,
  When cleanup runs,
  Then it is marked possibly idle but keeps its locks.
- Given an agent stays quiet past the stale limit,
  When cleanup runs,
  Then it is marked stale and its file locks are released for teammates.
- Given an agent discovers an issue touches more files after claiming it,
  When it requests extra path locks,
  Then the paths are added only if they do not overlap another active claim.
- Given a review has enough peer approval but one peer is slow,
  When the 15-minute review window expires,
  Then the sprint can reach consensus without waiting forever.
- Given the final commit agent is recommended,
  When stale agents or correction-requested issues exist,
  Then stale or blocked work is ignored in the recommendation.

## Design

The interface stores runtime state in `audit/inter_model/coordination.sqlite3`.
The file is disposable runtime state and must stay ignored by Git. The schema
tracks waves, agents, issue claims, path locks, reviews, messages, and final
recommendations.

Every command is join-only. It records the current agent's action and prints the
next instruction. It never starts another model process. Short SQLite
transactions wrap joins, claims, fixes, and reviews so concurrent agents see one
consistent result.

Agents can post short plain-English notes with `say` and read them with
`messages`. This is not live chat; it is a shared message board in the same
SQLite file, which is enough for "I claimed this area" and "please review this"
coordination across Codex, Claude, Gemini, and Antigravity.

Agents should send `heartbeat` while thinking, testing, reviewing, or blocked.
Those states make slow reasoning visible without releasing locks too early. A
cleanup command separates "possibly idle" from "stale" so a quiet model gets a
grace period before its locks are released.

## Quality Requirements

- Unit tests cover the 10-minute wait, duplicate joins, late joins, shared
  messages, path-lock conflicts, extra path locks, slow-thinking heartbeats,
  stale agents, review timeout, review flow, and commit-agent recommendation.
- Functions stay small enough to review directly.
- The command line interface prints plain English and never stages, commits,
  pushes, creates a branch, or starts another agent.
