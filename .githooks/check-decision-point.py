#!/usr/bin/env python3
"""PARAMOUNT — TDD pipeline Decision Point gate (Session S3, added 2026-05-18).

After every successful commit, `.githooks/post-commit` shells
`manage.py decision_point --commit <HEAD>` which files
`AutoIssue(category='decision_point')` rows in six buckets and prints a
`[DECISION POINT: commit=<short_hash> …]` marker.

This pre-commit hook validates that the staged AGENT-HANDOFF.md diff
carries the matching `[DECISION POINT: commit=<prior_HEAD> …]` marker
for the most recent prior commit. HARD-BLOCKS on missing / wrong /
malformed marker.

Exemptions:
  * Pure-docs commits (no production source files staged) — the rule
    doesn't apply.
  * Rule-introduction commit — when docs/TDD-PIPELINE-RULE.md is in
    the staged diff (or git has no prior commit at all), the gate is
    satisfied without a Decision Point marker.

Spec: docs/TDD-PIPELINE-RULE.md.
Rule-F compliant failure message: WHAT failed / WHY / UNBLOCK.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_helpers import (  # noqa: E402
    get_staged_files,
    get_staged_handoff_diff,
    is_production_source,
    run_git,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

_GRANDFATHER_SPEC = "docs/TDD-PIPELINE-RULE.md"

_DECISION_POINT_RE = re.compile(
    r"\[DECISION POINT:\s*"
    r"commit=(?P<commit>\S+)\s+"
    r"findings=(?P<findings>\d+)\s+"
    r"improvements=(?P<improvements>\d+)\s+"
    r"warnings=(?P<warnings>\d+)\s+"
    r"problems=(?P<problems>\d+)\s+"
    r"missing_spec=(?P<missing_spec>\d+)\s+"
    r"off_track_test_case=(?P<off_track_test_case>\d+)\s+"
    r"off_track_tdd=(?P<off_track_tdd>\d+)\s+"
    r"autoissues_filed=(?P<autoissues_filed>\S+)\s+"
    r"filed_at=(?P<filed_at>\S+)\]"
)

_LOOSE_DECISION_POINT_RE = re.compile(r"\[DECISION POINT:[^\]]*\]")


def _emit(msg: str) -> None:
    sys.stderr.write(msg)
    if not msg.endswith("\n"):
        sys.stderr.write("\n")


def _get_head_hash() -> str:
    """Full HEAD commit hash, or '' if no prior commit exists (fresh repo)."""
    out = run_git(REPO_ROOT, ["rev-parse", "HEAD"])
    return (out or "").strip()


def _hash_matches(marker_value: str, prior_commit: str) -> bool:
    """Marker carries 7-char prefix; prior_commit may be longer. Match by prefix."""
    if not marker_value or not prior_commit:
        return False
    return prior_commit.startswith(marker_value) or marker_value.startswith(prior_commit)


def validate_decision_point(
    diff: str, prior_commit: str, staged_files: list[str]
) -> int:
    """Return 0 (pass) or 2 (hard-block). Exposed for tests."""
    production_files = [f for f in staged_files if is_production_source(f)]
    if not production_files:
        return 0  # pure-docs / generated-only commit

    grandfather = _GRANDFATHER_SPEC in staged_files
    if grandfather:
        return 0

    if not prior_commit:
        _emit(
            "FAIL check-decision-point: this commit touches production "
            "source files but git has no prior commit AND "
            f"{_GRANDFATHER_SPEC} is not staged.\n"
            "WHY: PARAMOUNT TDD-pipeline rule says every code-changing "
            "commit must reference the prior commit's Decision Point "
            "marker in this session's handoff entry. A fresh repo has no "
            "prior commit, so the only legal first commit is the one "
            f"that introduces {_GRANDFATHER_SPEC}.\n"
            f"UNBLOCK: stage {_GRANDFATHER_SPEC} (the rule-introduction "
            "commit) before staging any other production source file.\n"
        )
        return 2

    full_match = _DECISION_POINT_RE.search(diff)
    loose_match = _LOOSE_DECISION_POINT_RE.search(diff)

    if full_match is None:
        if loose_match is None:
            _emit(
                "FAIL check-decision-point: this commit touches production "
                "source files but the staged AGENT-HANDOFF.md diff carries "
                "NO [DECISION POINT: ...] marker for the prior commit "
                f"{prior_commit[:7]}.\n"
                "WHY: PARAMOUNT TDD-pipeline rule says every successful "
                "commit triggers `manage.py decision_point` via the "
                "post-commit hook, which prints the marker the NEXT commit "
                "must echo into its handoff entry. A missing marker means "
                "the post-commit ritual was skipped, or the agent did not "
                "review what it just landed.\n"
                "UNBLOCK: run `docker compose exec -T backend python "
                f"manage.py decision_point --commit {prior_commit[:7]}` "
                "and paste the printed [DECISION POINT: ...] marker into "
                "this session's AGENT-HANDOFF.md entry. The post-commit "
                "hook runs this automatically — if you are committing for "
                "the first time after installing the hook, run it manually "
                "once to back-fill.\n"
            )
            return 2

        _emit(
            "FAIL check-decision-point: a [DECISION POINT: ...] marker is "
            "present but its shape does not match the strict regex.\n"
            "WHY: the marker MUST contain the exact field order: "
            "`commit findings improvements warnings problems missing_spec "
            "off_track_test_case off_track_tdd autoissues_filed filed_at`.\n"
            "UNBLOCK: re-run `manage.py decision_point` and paste its "
            "verbatim output; do not edit the marker by hand.\n"
        )
        return 2

    marker_commit = full_match.group("commit").strip()
    if not _hash_matches(marker_commit, prior_commit):
        _emit(
            "FAIL check-decision-point: the Decision Point marker carries "
            f"commit={marker_commit} but the prior commit is "
            f"{prior_commit[:7]}.\n"
            "WHY: the rule binds each Decision Point marker to a specific "
            "commit hash so the post-commit retrospective cannot be "
            "shifted onto an unrelated commit. A mismatch means the "
            "marker was generated for an older commit and the work since "
            "then was not analysed.\n"
            "UNBLOCK: run `docker compose exec -T backend python "
            f"manage.py decision_point --commit {prior_commit[:7]}` to "
            "produce a fresh marker for the current prior commit, then "
            "replace the stale one in the handoff entry.\n"
        )
        return 2

    return 0


def main() -> int:
    staged = get_staged_files(REPO_ROOT)
    if not staged:
        return 0
    diff = get_staged_handoff_diff(REPO_ROOT)
    prior = _get_head_hash()
    return validate_decision_point(diff, prior, staged)


if __name__ == "__main__":
    sys.exit(main())
