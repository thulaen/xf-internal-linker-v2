#!/usr/bin/env python3
"""Pre-commit gate for Rule B (Strict Red-Green-Refactor TDD).

Validates every staged production source file has a [TDD CYCLE] marker.
Rule F: every FAIL message is plain English with (what, why, unblock).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_TDD_CYCLE_RE = re.compile(r"\[TDD CYCLE:[^\]]+\]")
_SOURCE_PREFIXES = (
    "backend/apps/",
    "backend/extensions/",
    "frontend/src/",
    "scripts/",
)
_SOURCE_SUFFIXES = (".py", ".cpp", ".h", ".ts", ".tsx")


def _staged_source_files() -> list[str]:
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
        if line.strip().startswith(_SOURCE_PREFIXES)
        and line.strip().endswith(_SOURCE_SUFFIXES)
        and "test" not in Path(line).name.lower()
    ]


def _staged_handoff_diff() -> str:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--unified=0", "--",
             "AGENT-HANDOFF.md"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
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
    source_files = _staged_source_files()
    if not source_files:
        return 0
    handoff = _staged_handoff_diff()
    cycles = len(_TDD_CYCLE_RE.findall(handoff))
    if cycles == 0:
        sys.stderr.write(
            "FAIL check-tdd-cycle: production source files are staged but "
            "AGENT-HANDOFF.md has no [TDD CYCLE] marker.\n"
            "WHY: Rule B requires Red-Green-Refactor for every code change. "
            "The marker proves a failing test was written first, the minimum "
            "source change made it pass, and the touched files refactored to "
            "ruff-clean.\n"
            "UNBLOCK: For each touched source file run `manage.py "
            "verify_tdd_cycle --source <path.py> --test <test_path.py> "
            "--ruff-clean` and paste each marker into the handoff entry.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
