#!/usr/bin/env python3
"""Slice 1.6 — snapshotd opening ritual.

Validates that the newly-staged AGENT-HANDOFF.md entry contains a
[SNAPSHOTS READ: ...] marker AFTER the [PAPER TRAIL READ: ...] marker.

Rule F-compliant (FAIL / WHY / UNBLOCK). Hard-block at commit.

What this hook enforces (per docs/specs/fr-sidecars-host.md § snapshotd):

  Every code-changing commit must surface which snapshotd evidence the
  agent reviewed before proposing fixes. The marker lives in the same
  handoff entry the paper-trail / registry rituals already populate, so
  no new file is involved.

Accepted forms:

  1. Full picked form (preferred once `manage.py print_open_snapshots`
     ships from paper-trail #568):
       [SNAPSHOTS READ: <N> snapshots attached to <M> open issues —
       picked: #<id>(<kind>), #<id>(<kind>), #<id>(<kind>)]

  2. Skipped form (during the rollout window when snapshotd isn't yet
     callable from Python):
       [SNAPSHOTS READ: skipped — snapshotd unavailable]

The hook deliberately does NOT shell `manage.py print_open_snapshots`
this slice — the command is deferred (paper-trail #568). Once #568
lands the hook can be extended to verify the picks against the live DB,
mirroring the check-paper-trail-read.py quota-verification pattern.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Code-changing path prefixes — the SNAPSHOTS READ ritual is only required
# for commits that change production source.
_CODE_PREFIXES = (
    "backend/",
    "frontend/",
    "scripts/",
    ".githooks/",
    "backend/extensions/",
    "services/",
)

_PAPER_TRAIL_RE = re.compile(r"\[PAPER\s+TRAIL\s+READ:", re.IGNORECASE)
_SNAPSHOTS_RE = re.compile(
    r"\[SNAPSHOTS\s+READ:\s*(?P<body>[^\]]+)\]",
    re.IGNORECASE,
)
# Full form: at least three #<id>(<kind>) picks. Captures the picks list.
_FULL_FORM_RE = re.compile(
    r"^\s*\d+\s+snapshots?\s+attached\s+to\s+\d+\s+open\s+issues?\s*"
    r"(?:—|--|-)\s*picked:\s*(?P<picks>.+)$",
    re.IGNORECASE,
)
_SKIPPED_FORM_RE = re.compile(
    r"^\s*skipped\s*(?:—|--|-)\s*snapshotd\s+unavailable\s*$",
    re.IGNORECASE,
)
# Empty form: snapshotd is reachable but the database is genuinely empty
# (no open AutoIssue has an attached snapshot yet). Accepted because the
# 3-pick rule would otherwise hard-block early-life commits.
_EMPTY_FORM_RE = re.compile(
    r"^\s*0\s+snapshots?\s+attached\s+to\s+0\s+open\s+issues?\s*"
    r"(?:—|--|-)\s*picked:\s*\(none\b[^)]*\)\s*$",
    re.IGNORECASE,
)
_PICK_RE = re.compile(r"#\d+\s*\([^)]+\)")


# _read_staged_handoff_diff() lives in _hook_helpers.py per paper-trail
# #585 / test_case #703.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_helpers import get_staged_handoff_diff  # noqa: E402


def _read_staged_handoff_diff() -> str:
    """Return the added lines from the staged diff of AGENT-HANDOFF.md."""
    return get_staged_handoff_diff(REPO_ROOT)


def _staged_files() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _is_code_changing(files: list[str]) -> bool:
    return any(f.startswith(_CODE_PREFIXES) for f in files)


def _format_missing_failure() -> None:
    sys.stderr.write(
        "FAIL check-snapshotd-ritual: the staged AGENT-HANDOFF.md entry is "
        "missing the [SNAPSHOTS READ: ...] marker.\n"
        "WHY: docs/specs/fr-sidecars-host.md § snapshotd requires every "
        "code-changing commit to surface which snapshotd evidence the agent "
        "reviewed before proposing the fix. The marker must appear in the "
        "same handoff entry as [PAPER TRAIL READ: ...] and AFTER it.\n"
        "UNBLOCK: Once `manage.py print_open_snapshots` lands (paper-trail "
        "#568), run it and paste the printed line into the handoff. Until "
        "then, the fallback form is accepted: "
        "`[SNAPSHOTS READ: skipped — snapshotd unavailable]`. Add the "
        "marker AFTER the [PAPER TRAIL READ: ...] line, stage the handoff, "
        "and re-commit.\n"
    )


def _format_order_failure() -> None:
    sys.stderr.write(
        "FAIL check-snapshotd-ritual: [SNAPSHOTS READ: ...] appears BEFORE "
        "[PAPER TRAIL READ: ...] in the staged AGENT-HANDOFF.md entry.\n"
        "WHY: The ritual order matters — paper-trail picks come first, "
        "then snapshot evidence for those picks. Reversing the order "
        "breaks the reading flow for the next agent.\n"
        "UNBLOCK: Move the [SNAPSHOTS READ: ...] line so it appears AFTER "
        "the [PAPER TRAIL READ: ...] line in the same handoff entry.\n"
    )


def _format_shape_failure(body: str) -> None:
    sys.stderr.write(
        "FAIL check-snapshotd-ritual: [SNAPSHOTS READ: ...] is present but "
        "the body shape does not match either accepted form.\n"
        f"  got body: {body!r}\n"
        "WHY: The marker must be either the full picked form\n"
        "  [SNAPSHOTS READ: <N> snapshots attached to <M> open issues — "
        "picked: #<id>(<kind>), #<id>(<kind>), #<id>(<kind>)]\n"
        "or the skipped fallback while paper-trail #568 is pending\n"
        "  [SNAPSHOTS READ: skipped — snapshotd unavailable]\n"
        "UNBLOCK: rewrite the marker body to match one of the two forms.\n"
    )


def validate(added_diff: str) -> int:
    """Validate the staged handoff diff. Returns 0 on pass, 2 on hard-fail.

    Exposed for unit testing — the test suite passes a synthetic diff
    string so it does not need a live git checkout.
    """
    paper_trail_match = _PAPER_TRAIL_RE.search(added_diff)
    if paper_trail_match is None:
        # The check-paper-trail-read.py hook handles the missing-paper-trail
        # case. This hook only runs after that one passes, so a missing
        # paper-trail marker here is not our problem to report.
        return 0

    snapshots_match = _SNAPSHOTS_RE.search(added_diff)
    if snapshots_match is None:
        _format_missing_failure()
        return 2

    if snapshots_match.start() < paper_trail_match.start():
        _format_order_failure()
        return 2

    body = snapshots_match.group("body").strip()
    if _SKIPPED_FORM_RE.match(body):
        return 0
    if _EMPTY_FORM_RE.match(body):
        return 0
    full_match = _FULL_FORM_RE.match(body)
    if full_match is None:
        _format_shape_failure(body)
        return 2
    # Full form requires at least 3 #id(kind) picks.
    picks = _PICK_RE.findall(full_match.group("picks"))
    if len(picks) < 3:
        sys.stderr.write(
            "FAIL check-snapshotd-ritual: the full-form picked list must "
            "contain at least 3 entries shaped #<id>(<kind>); got "
            f"{len(picks)}.\n"
            "UNBLOCK: include the top-3 highest-severity snapshots from "
            "`manage.py print_open_snapshots --by-severity --top 3`.\n"
        )
        return 2
    return 0


def main() -> int:
    files = _staged_files()
    if not files:
        return 0
    if not _is_code_changing(files):
        return 0
    added = _read_staged_handoff_diff()
    if not added:
        # check-paper-trail-read.py already handles "no handoff staged on a
        # code-changing commit"; we do not duplicate that error here.
        return 0
    return validate(added)


if __name__ == "__main__":
    sys.exit(main())
