#!/usr/bin/env python3
"""Pre-commit gate for Rule G — code-review lessons logged to AutoIssue.

HARD-BLOCK on any code-changing commit that does not include a
[CODE REVIEW LESSONS: <N> logged from <M> files; deduped <K> against prior]
marker in the staged AGENT-HANDOFF.md.

Rule F compliant: every FAIL message has WHY + UNBLOCK.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_SUMMARY_RE = re.compile(
    r"\[CODE REVIEW LESSONS:\s*(?P<n>\d+)\s+logged\s+from\s+(?P<m>\d+)\s+files;\s*"
    r"deduped\s+(?P<k>\d+)\s+against prior\]"
)
_DETAIL_RE = re.compile(
    r"\[CODE REVIEW LESSON LOGGED:\s*AutoIssue=#(?P<id>\d+)\s+"
    r"title=\"([^\"]+)\"\s+abstract_words=(?P<w>\d+)\]"
)
_DEDUPED_RE = re.compile(
    r"\[CODE REVIEW LESSON DEDUPED:\s*matched\s+AutoIssue=#(?P<id>\d+)\]"
)
_CODE_PREFIXES = (
    "backend/",
    "frontend/",
    "scripts/",
    ".githooks/",
)
_NON_SOURCE_PATHS = (
    "AGENT-HANDOFF.md",
    "AI-CONTEXT.md",
    "docs/",
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
    out_lines = [line.strip() for line in (out.stdout or "").splitlines() if line.strip()]
    files: list[str] = []
    for line in out_lines:
        if any(line.startswith(p) for p in _NON_SOURCE_PATHS):
            continue
        if any(line.startswith(p) for p in _CODE_PREFIXES):
            files.append(line)
    return files


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
    code_files = _staged_code_files()
    if not code_files:
        return 0
    handoff = _staged_handoff_diff()
    summary = _SUMMARY_RE.search(handoff)
    if not summary:
        sys.stderr.write(
            "FAIL check-code-review-lessons: production code is staged but "
            "AGENT-HANDOFF.md has no [CODE REVIEW LESSONS: N logged from M "
            "files; deduped K against prior] marker.\n"
            "WHY: Rule G requires every code-changing commit to log at "
            "least one code-review lesson per touched file to "
            "AutoIssue.lessons_learned so future agents can search for "
            "prior reviews of the same area. Silent code changes are "
            "forbidden. The review must check for bugs, silent errors, "
            "correctness, tech debt, maintainability, duplication, and "
            "long functions before commit.\n"
            "UNBLOCK: For each touched file, run `docker compose exec -T "
            "backend python manage.py log_code_review_lessons --file "
            "<path> --title \"<descriptive title>\" --abstract "
            "\"<summary or no-issues note, max 600 words>\" --severity "
            "<none|low|medium|high|critical>`. Include the review result "
            "for bugs, silent errors, correctness, tech debt, "
            "maintainability, duplication, and long functions in the "
            "abstract, then paste each printed marker (LOGGED or DEDUPED) "
            "plus the final summary line into the AGENT-HANDOFF.md entry.\n"
        )
        return 2

    n = int(summary["n"])
    m = int(summary["m"])
    k = int(summary["k"])
    m_touched = len(code_files)

    if m < m_touched:
        sys.stderr.write(
            f"FAIL check-code-review-lessons: marker says only {m} file(s) "
            f"reviewed but {m_touched} production source file(s) are "
            f"staged.\n"
            "WHY: Rule G requires every touched file to be accounted for "
            "in the review. The review must cover bugs, silent errors, "
            "correctness, tech debt, maintainability, duplication, and "
            "long functions.\n"
            "UNBLOCK: Run `manage.py log_code_review_lessons` for the "
            "missing files, then update the marker to reflect the correct "
            "M value.\n"
        )
        return 2

    if n + k < m:
        sys.stderr.write(
            f"FAIL check-code-review-lessons: marker counts {n}+{k}={n+k} "
            f"reviews but {m} files were touched. Every file needs either a "
            f"new logged lesson (N) or a dedup match against a prior "
            f"lesson (K).\n"
            "WHY: Rule G — silent code changes without a logged or "
            "deduped review are forbidden. The review must cover bugs, "
            "silent errors, correctness, tech debt, maintainability, "
            "duplication, and long functions.\n"
            "UNBLOCK: Run `manage.py log_code_review_lessons --file <path> "
            "...` for the missing files, then update the summary marker.\n"
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
