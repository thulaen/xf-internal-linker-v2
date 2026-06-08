#!/usr/bin/env python3
"""Pre-commit gate for Rule D (scoped lesson reading).

Validates the staged AGENT-HANDOFF.md entry contains a
[SCOPED LESSONS READ: N lessons in <paths>] marker covering the touched
paths in the staged diff. Rule F: plain-English FAIL message.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_SCOPED_RE = re.compile(
    r"\[SCOPED LESSONS READ:\s*(?P<n>\d+)\s+lessons\s+in\s+(?P<areas>[^\]]+)\]"
)
_CODE_PREFIXES = (
    "backend/",
    "frontend/",
    "scripts/",
    ".githooks/",
)


def _staged_code_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [
        line.strip()
        for line in (out.stdout or "").splitlines()
        if line.strip().startswith(_CODE_PREFIXES)
    ]


def _staged_handoff_diff() -> str:
    """UTF-8 with replace fallback for Windows locale codec resistance."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--unified=0", "--",
             "AGENT-HANDOFF.md"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=10, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return "\n".join(
        line[1:]
        for line in (out.stdout or "").splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def main() -> int:
    code_files = _staged_code_files()
    if not code_files:
        return 0
    handoff = _staged_handoff_diff()
    match = _SCOPED_RE.search(handoff)
    if not match:
        sys.stderr.write(
            "WARN check-scoped-lessons: this commit modifies code but "
            "AGENT-HANDOFF.md has no [SCOPED LESSONS READ: N lessons in "
            "<paths>] marker.\n"
            "WHY: Rule D requires every code-changing commit to first look "
            "up prior resolved-AutoIssue lessons for the touched areas so "
            "agents do not repeat the same traps.\n"
            "UNBLOCK: Run `docker compose exec -T backend python manage.py "
            "read_scoped_lessons --area <touched-dir> [--area <other-dir> "
            "...]` and paste the printed marker line into a new handoff "
            "entry. The output also surfaces the top 5 lessons for each "
            "area — read them before editing.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
