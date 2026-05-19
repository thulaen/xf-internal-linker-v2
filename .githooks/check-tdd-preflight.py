#!/usr/bin/env python3
"""PARAMOUNT — TDD pipeline preflight gate (Session S1, added 2026-05-18).

Validates that every code-changing commit's staged AGENT-HANDOFF.md entry
carries a `[TDD PREFLIGHT: …]` marker positioned IMMEDIATELY AFTER
`[HANDOFF READ: …]` and BEFORE the other session-start read markers
(REGISTRY / PAPER TRAIL / SNAPSHOTS / LESSONS BEFORE START).

The marker is emitted by `manage.py preflight_tdd`. Pure-docs commits
(no production source files staged) are exempt.

Spec: docs/TDD-PIPELINE-RULE.md (authored in Session S4).
Rule-F compliant failure message: WHAT failed / WHY it failed / UNBLOCK.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_helpers import (  # noqa: E402
    get_staged_files,
    get_staged_handoff_diff,
    is_production_source,
    parse_iso8601,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# Full shape of the marker emitted by `manage.py preflight_tdd`.
# 2026-05-18: added no_bypass, per_file_lookup, commit_failure_lookup switches
# per the user directive "nothing should be bypassed and that to the session
# preflight" plus the disk-backed per-file mandate + commit-failure lookup.
_PREFLIGHT_RE = re.compile(
    r"\[TDD\s+PREFLIGHT:\s*"
    r"pipeline=(?P<pipeline>\S+)\s+"
    r"spec_citation=(?P<spec_citation>\S+)\s+"
    r"test_case_mandate=(?P<test_case_mandate>\S+)\s+"
    r"tdd_red_green_refactor=(?P<tdd_red_green_refactor>\S+)\s+"
    r"5_layer_coverage=(?P<five_layer>\S+)\s+"
    r"code_review_logging=(?P<code_review>\S+)\s+"
    r"lesson_logging=(?P<lesson_logging>\S+)\s+"
    r"decision_point=(?P<decision_point>\S+)\s+"
    r"artefact_pruning=(?P<artefact_pruning>\S+)\s+"
    r"no_bypass=(?P<no_bypass>\S+)\s+"
    r"per_file_lookup=(?P<per_file_lookup>\S+)\s+"
    r"commit_failure_lookup=(?P<commit_failure_lookup>\S+)\s+"
    r"session_id=(?P<session_id>\S+)\s+"
    r"armed_at=(?P<armed_at>\S+)\s*\]"
)

# Loose detection — catches a bare `[TDD PREFLIGHT: ...]` even when its
# inner fields are malformed, so we can give a specific error message.
_LOOSE_PREFLIGHT_RE = re.compile(r"\[TDD\s+PREFLIGHT:[^\]]*\]")

_HANDOFF_READ_RE = re.compile(r"\[HANDOFF\s+READ:[^\]]*\]")

_OTHER_READ_MARKER_NAMES = (
    "REGISTRY READ",
    "PAPER TRAIL READ",
    "SNAPSHOTS READ",
    "LESSONS BEFORE START",
)

_SWITCH_FIELDS: tuple[str, ...] = (
    "spec_citation",
    "test_case_mandate",
    "tdd_red_green_refactor",
    "five_layer",
    "code_review",
    "lesson_logging",
    "decision_point",
    "artefact_pruning",
    "no_bypass",
    "per_file_lookup",
    "commit_failure_lookup",
)
_REQUIRED_PIPELINE = "SPEC→TEST_CASE→TDD→CODE→CODE_REVIEW→LESSON"


def _emit(msg: str) -> None:
    sys.stderr.write(msg)
    if not msg.endswith("\n"):
        sys.stderr.write("\n")


def _earliest_position(diff: str, names: tuple[str, ...]) -> int | None:
    """Earliest character index of any of the named markers, or None."""
    best: int | None = None
    for name in names:
        pattern = re.escape("[" + name + ":")
        for m in re.finditer(pattern, diff):
            pos = m.start()
            if best is None or pos < best:
                best = pos
    return best


def validate_preflight(diff: str, staged_files: list[str]) -> int:
    """Return 0 (pass) or 2 (hard-block). Exposed for tests."""
    production_files = [f for f in staged_files if is_production_source(f)]
    if not production_files:
        # Pure-docs / generated-only commit. Preflight not required.
        return 0

    preflight_match = _PREFLIGHT_RE.search(diff)
    loose_match = _LOOSE_PREFLIGHT_RE.search(diff)

    if preflight_match is None:
        if loose_match is None:
            _emit(
                "FAIL check-tdd-preflight: this commit touches production source "
                "files but the staged AGENT-HANDOFF.md diff carries NO "
                "[TDD PREFLIGHT: ...] marker.\n"
                "WHY: PARAMOUNT TDD-pipeline rule requires every code-changing "
                "session to arm the SPEC→TEST_CASE→TDD→CODE→CODE_REVIEW→LESSON "
                "pipeline at session start by running `manage.py preflight_tdd` "
                "and pasting the printed marker immediately after the "
                "[HANDOFF READ: ...] line. The check fires FIRST in the hook "
                "chain so an unarmed session fails before any other work.\n"
                "UNBLOCK: run `docker compose exec -T backend python "
                "manage.py preflight_tdd` and paste the printed [TDD PREFLIGHT: "
                "...] marker into this session's AGENT-HANDOFF.md entry, on the "
                "line directly after [HANDOFF READ: ...].\n"
            )
            return 2

        # Loose match but no full match — emit a marker-shape error so the
        # agent knows exactly which field is malformed.
        _emit(
            "FAIL check-tdd-preflight: a [TDD PREFLIGHT: ...] marker is "
            "present but its shape does not match the strict regex.\n"
            "WHY: the marker MUST contain the pipeline + eleven pipeline "
            "switches + session_id + armed_at in the exact order the hook "
            "validates (the order is `pipeline spec_citation test_case_mandate "
            "tdd_red_green_refactor 5_layer_coverage code_review_logging "
            "lesson_logging decision_point artefact_pruning no_bypass "
            "per_file_lookup commit_failure_lookup session_id armed_at`).\n"
            "UNBLOCK: re-run `manage.py preflight_tdd` and paste its "
            "verbatim output; do not edit the marker by hand.\n"
        )
        # Try to be specific: which named field is missing?
        for field in ("pipeline", "session_id", "armed_at"):
            if not re.search(rf"{field}=", loose_match.group(0)):
                _emit(f"  [missing field] {field}\n")
        return 2

    # Marker parsed — validate each subfield.
    pipeline = preflight_match.group("pipeline")
    if pipeline != _REQUIRED_PIPELINE:
        _emit(
            f"FAIL check-tdd-preflight: pipeline={pipeline} does not include "
            "the required CODE_REVIEW stage.\n"
            "WHY: preflight is the session-start contract that tells agents "
            "how to work. CODE REVIEW is an after-the-fact check after CODE "
            "and before LESSON, so it cannot be skipped or hidden as a vague "
            "`REVIEW` token.\n"
            "UNBLOCK: re-run `manage.py preflight_tdd` and paste the new "
            "marker with pipeline=SPEC→TEST_CASE→TDD→CODE→CODE_REVIEW→LESSON.\n"
        )
        return 2

    for field in _SWITCH_FIELDS:
        value = preflight_match.group(field)
        if value.lower() != "on":
            _emit(
                f"FAIL check-tdd-preflight: pipeline switch "
                f"`{field}={value}` is not `on`.\n"
                f"WHY: every pipeline component is required for the rule to "
                f"hold; a switch set to `off` advertises that the agent is "
                f"about to skip a piece of the SPEC→…→LESSON chain.\n"
                f"UNBLOCK: re-run `manage.py preflight_tdd` (do not edit the "
                f"marker by hand). All eleven switches MUST be `on`.\n"
            )
            return 2

    armed_at = parse_iso8601(preflight_match.group("armed_at"))
    if armed_at is None:
        _emit(
            "FAIL check-tdd-preflight: armed_at is not a valid ISO-8601 "
            "timestamp.\n"
            "UNBLOCK: re-run `manage.py preflight_tdd` to regenerate the "
            "marker with a fresh armed_at value.\n"
        )
        return 2

    # Position validation. Required ordering on the staged diff:
    #   [HANDOFF READ: ...] < [TDD PREFLIGHT: ...] < [REGISTRY READ: ...] |
    #                                              [PAPER TRAIL READ: ...] |
    #                                              [SNAPSHOTS READ: ...] |
    #                                              [LESSONS BEFORE START: ...]
    handoff_match = _HANDOFF_READ_RE.search(diff)
    if handoff_match is None:
        _emit(
            "FAIL check-tdd-preflight: a [TDD PREFLIGHT: ...] marker is "
            "present but no [HANDOFF READ: ...] marker precedes it in the "
            "staged diff.\n"
            "WHY: PARAMOUNT TDD-pipeline rule says the agent reads the "
            "previous handoff context FIRST, then arms the pipeline. A "
            "preflight marker without a handoff-read marker means the "
            "agent skipped the handoff step.\n"
            "UNBLOCK: paste the [HANDOFF READ: ...] line you produced from "
            "reading the previous AGENT-HANDOFF.md entry, on the line "
            "immediately above [TDD PREFLIGHT: ...].\n"
        )
        return 2

    preflight_pos = preflight_match.start()
    handoff_pos = handoff_match.start()
    other_pos = _earliest_position(diff, _OTHER_READ_MARKER_NAMES)

    if preflight_pos < handoff_pos:
        _emit(
            "FAIL check-tdd-preflight: [TDD PREFLIGHT: ...] appears BEFORE "
            "[HANDOFF READ: ...] in the staged diff.\n"
            "WHY: the rule requires reading the previous handoff context "
            "FIRST, then arming the pipeline. Preflight before handoff means "
            "the agent attested to TDD before knowing what the previous "
            "agent was doing.\n"
            "UNBLOCK: move [HANDOFF READ: ...] to be the first marker in this "
            "session's entry; [TDD PREFLIGHT: ...] comes after it.\n"
        )
        return 2

    if other_pos is not None and preflight_pos > other_pos:
        _emit(
            "FAIL check-tdd-preflight: [TDD PREFLIGHT: ...] appears AFTER "
            "at least one of the other session-start read markers "
            "([REGISTRY READ:] / [PAPER TRAIL READ:] / [SNAPSHOTS READ:] / "
            "[LESSONS BEFORE START:]).\n"
            "WHY: the rule says preflight is the SECOND marker — between "
            "[HANDOFF READ: ...] and every other read marker — so a missing "
            "or late preflight cannot be quietly buried under other rituals.\n"
            "UNBLOCK: move [TDD PREFLIGHT: ...] to sit immediately AFTER "
            "[HANDOFF READ: ...] and BEFORE any other [..READ:] / "
            "[LESSONS BEFORE START:] marker in this session's entry.\n"
        )
        return 2

    return 0


def main() -> int:
    files = get_staged_files(REPO_ROOT)
    if not files:
        return 0
    diff = get_staged_handoff_diff(REPO_ROOT)
    return validate_preflight(diff, files)


if __name__ == "__main__":
    sys.exit(main())
