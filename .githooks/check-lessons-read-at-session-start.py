#!/usr/bin/env python3
"""PARAMOUNT — mandatory lessons-read at session start (added 2026-05-17).

Hard-blocks any code-changing commit whose staged AGENT-HANDOFF.md diff
does not include a `[LESSONS BEFORE START: ...]` marker AFTER
`[REGISTRY READ: ...]` and `[PAPER TRAIL READ: ...]`.

The marker shape is:

  [LESSONS BEFORE START: <N> resolved-lesson rows reviewed in
   <comma-separated repo-relative areas>]

It proves the agent ran
`docker compose exec -T backend python manage.py read_scoped_lessons
--area <path> [--area <path2> ...]` for every area they anticipate
touching this session. Empty queries are allowed via the literal
`<no-prior-fixes-in-touched-area>` token so a greenfield area is not
rejected.

Spec: docs/TDD-STRICT-RULE.md § "Reading prior lessons is mandatory at
session start".
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_CODE_PREFIXES = (
    "backend/",
    "frontend/",
    "scripts/",
    ".githooks/",
    "services/",
    "backend/extensions/",
)

_REGISTRY_READ_RE = re.compile(r"\[REGISTRY\s+READ:", re.IGNORECASE)
_LESSONS_MARKER_RE = re.compile(
    r"\[LESSONS\s+BEFORE\s+START:\s*(?P<body>[^\]]+)\]",
    re.IGNORECASE,
)
_LESSONS_FULL_BODY_RE = re.compile(
    r"^\s*\d+\s+resolved-lesson\s+rows?\s+reviewed\s+in\s+\S",
    re.IGNORECASE,
)


def is_code_changing(staged_files: list[str]) -> bool:
    return any(p.startswith(_CODE_PREFIXES) for p in staged_files)


# _read_staged_handoff_diff() lives in _hook_helpers.py per paper-trail
# #585 / test_case #703.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_helpers import get_staged_handoff_diff  # noqa: E402


def _read_staged_handoff_diff() -> str:
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


def validate(added_diff: str) -> int:
    """Returns 0 on pass, 2 on fail. Exposed for tests."""
    lessons_match = _LESSONS_MARKER_RE.search(added_diff)
    if lessons_match is None:
        sys.stderr.write(
            "FAIL check-lessons-read-at-session-start: the staged "
            "AGENT-HANDOFF.md entry is missing the [LESSONS BEFORE START: "
            "...] marker.\n"
            "WHY: docs/TDD-STRICT-RULE.md requires every code-changing "
            "commit's session-opening entry to prove the agent read every "
            "resolved-lesson AutoIssue in the areas they touched. Without "
            "that read step, agents silently repeat traps the prior agent "
            "already documented.\n"
            "UNBLOCK: run `docker compose exec -T backend python manage.py "
            "read_scoped_lessons --area <touched-path> [--area <other>]` "
            "for every area you anticipate touching this session, then add "
            "[LESSONS BEFORE START: <N> resolved-lesson rows reviewed in "
            "<comma-separated-paths>] to the handoff entry AFTER the "
            "[REGISTRY READ: ...] line. If no prior fixes exist in your "
            "touched area, use the literal form `0 resolved-lesson rows "
            "reviewed in <no-prior-fixes-in-touched-area>`.\n"
        )
        return 2

    body = lessons_match.group("body").strip()
    if not _LESSONS_FULL_BODY_RE.match(body):
        sys.stderr.write(
            "FAIL check-lessons-read-at-session-start: the [LESSONS BEFORE "
            "START: ...] marker is present but the body shape does not "
            "match.\n"
            f"  got body: {body!r}\n"
            "WHY: the canonical shape is `<N> resolved-lesson rows reviewed "
            "in <comma-separated repo-relative paths>`. The hook regex "
            "requires a leading integer + the literal `resolved-lesson "
            "rows reviewed in` + at least one non-whitespace area.\n"
            "UNBLOCK: rewrite the marker body to match the canonical shape.\n"
        )
        return 2

    registry_match = _REGISTRY_READ_RE.search(added_diff)
    if registry_match is not None and lessons_match.start() < registry_match.start():
        sys.stderr.write(
            "FAIL check-lessons-read-at-session-start: [LESSONS BEFORE "
            "START: ...] appears BEFORE [REGISTRY READ: ...] in the handoff "
            "entry.\n"
            "WHY: the ritual order is HANDOFF READ → REGISTRY READ → "
            "PAPER TRAIL READ → SNAPSHOTS READ → LESSONS BEFORE START. "
            "Reversing the order breaks the reading flow for the next agent.\n"
            "UNBLOCK: move the [LESSONS BEFORE START: ...] line so it "
            "appears AFTER the [REGISTRY READ: ...] line.\n"
        )
        return 2

    return 0


def main() -> int:
    files = _staged_files()
    if not files:
        return 0
    if not is_code_changing(files):
        return 0
    added = _read_staged_handoff_diff()
    if not added:
        return 0  # no staged handoff diff -> nothing to validate here
    return validate(added)


if __name__ == "__main__":
    sys.exit(main())
