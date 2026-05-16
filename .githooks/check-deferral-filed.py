#!/usr/bin/env python3
"""Every deferral filed in the paper trail (added 2026-05-16).

When the staged AGENT-HANDOFF.md entry uses a deferral verb (deferred,
deferring, postponed, postponing, skipping, leaving for next session,
out-of-scope this session, etc.) it MUST be paired with a matching
`[PAPER TRAIL FILED: #<N>]` marker. The hook counts both on the staged
ADDED lines only (so past entries in the same file don't trip it) and
fails when verbs > markers.

Rule F compliant: every FAIL message has WHY + UNBLOCK.
Scope: only fires when `AGENT-HANDOFF.md` is in the staged diff.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HANDOFF_PATH = "AGENT-HANDOFF.md"

# Forward-looking deferral phrasings. Each pattern requires explicit
# grammar (subject + verb or verb + object) so descriptive mentions of
# the word "deferred" inside rule definitions, docs, or past-tense
# references to already-filed deferrals do NOT trip the hook. Patterns
# are case-insensitive and word-bounded.
_DEFERRAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "I/we (will) defer / deferring / deferred"
    re.compile(
        r"\b(?:i|we)\s*['’]?(?:ll|m|re)?\s+(?:will\s+|am\s+|are\s+)?"
        r"defer(?:ring|red)?\b",
        re.IGNORECASE,
    ),
    # "deferring/deferred to/until/for next|a future|the next|follow-up"
    re.compile(
        r"\bdefer(?:ring|red)\s+(?:to|until|for)\s+"
        r"(?:next|a\s+future|the\s+next|follow)",
        re.IGNORECASE,
    ),
    # "postponed/postponing to/until/for next|a future|the next"
    re.compile(
        r"\bpostpon(?:ed|ing)\s+(?:to|until|for)\s+"
        r"(?:next|a\s+future|the\s+next)",
        re.IGNORECASE,
    ),
    # "pushed/pushing to next|a future|the next session"
    re.compile(
        r"\bpush(?:ed|ing)\s+to\s+(?:next|a\s+future|the\s+next)\s+session\b",
        re.IGNORECASE,
    ),
    # "skipping this|for now|the rest|the next" — first-person intent
    re.compile(
        r"\bskip(?:ping|ped)\s+(?:this|for\s+now|the\s+rest|the\s+next)\b",
        re.IGNORECASE,
    ),
    # "leaving for/to next|the next|a future|follow-up"
    re.compile(
        r"\bleaving\s+(?:for|to)\s+(?:next|the\s+next|a\s+future|follow)",
        re.IGNORECASE,
    ),
    # "out-of-scope this session"
    re.compile(r"\bout[- ]of[- ]scope\s+(?:this|for\s+this)\s+session\b", re.IGNORECASE),
    # "not in this session"
    re.compile(r"\bnot\s+in\s+this\s+session\b", re.IGNORECASE),
)

_MARKER_PATTERN = re.compile(r"\[PAPER TRAIL FILED:\s*#\d+\]")


def _staged_handoff_diff() -> str:
    """Return the git diff for AGENT-HANDOFF.md (staged), or empty string."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--", HANDOFF_PATH],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return out.stdout or ""


_RITUAL_MARKER_PREFIXES = (
    "[REGISTRY READ:",
    "[PAPER TRAIL READ:",
    "[CI FAILED RUNS READ:",
    "[COVERAGE GAPS READ:",
    "[HANDOFF READ:",
    "[CODE REVIEW LESSON LOGGED:",
    "[CODE REVIEW LESSONS:",
    "[STANDARDS READY:",
    "[SCOPED LESSONS READ:",
    "[SELF REVIEW RESULT:",
    "[BDD PROOF:",
    "[TDD PROOF:",
    "[TDD CYCLE:",
)


def _extract_added_lines(diff: str) -> str:
    """Pull the added-only lines out of a unified diff.

    Lines beginning with `+` are additions; `+++` is the file header
    and is excluded. Status-report ritual markers (REGISTRY READ /
    PAPER TRAIL READ / etc.) are also excluded because they report
    on the queue state rather than commit new deferrals. Return value
    is plain text (newline-joined).
    """
    added: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++"):
            continue
        if not line.startswith("+"):
            continue
        body = line[1:]
        stripped = body.lstrip()
        if any(stripped.startswith(p) for p in _RITUAL_MARKER_PREFIXES):
            continue
        added.append(body)
    return "\n".join(added)


def _count_deferrals(text: str) -> int:
    """Sum matches across every deferral pattern in `text`."""
    total = 0
    for pat in _DEFERRAL_PATTERNS:
        total += len(pat.findall(text))
    return total


def _count_markers(text: str) -> int:
    """Count `[PAPER TRAIL FILED: #<N>]` markers in `text`."""
    return len(_MARKER_PATTERN.findall(text))


def main() -> int:
    diff = _staged_handoff_diff()
    if not diff:
        # AGENT-HANDOFF.md is not in the staged diff; nothing to check.
        return 0

    added = _extract_added_lines(diff)
    deferrals = _count_deferrals(added)
    markers = _count_markers(added)

    if deferrals <= markers:
        return 0

    deficit = deferrals - markers
    sys.stderr.write(
        "FAIL check-deferral-filed: AGENT-HANDOFF.md mentions deferred work "
        f"without a matching paper-trail entry ({deferrals} deferral verb(s) "
        f"found, {markers} `[PAPER TRAIL FILED: #N]` marker(s) — short by "
        f"{deficit}).\n"
        "WHY: The ABSOLUTE rule added 2026-05-16 says every deferral MUST "
        "be filed in the paper trail before the session ends, so the next "
        "agent can pick it up. Deferred work that is not in the database is "
        "lost work.\n"
        "UNBLOCK: For each deferral, run:\n"
        "  docker compose exec -T backend python manage.py defer_work \\\n"
        "    --title \"<short title>\" \\\n"
        "    --category <one of the 17 categories> \\\n"
        "    --abstract \"Given ... When ... Then ...\" \\\n"
        "    --severity <low|medium|high|critical> \\\n"
        "    --deferred-by <your agent name>\n"
        "Then add the printed `[PAPER TRAIL FILED: #<N>]` line to the new "
        "handoff entry. Re-stage and re-commit. The C++ dedup index "
        "collapses repeats automatically, so re-filing the same deferral is "
        "safe.\n"
        "\n"
        "If you believe this is a false positive (e.g. the regex flagged a "
        "past-tense reference to an already-filed deferral), report it "
        "first with:\n"
        "  docker compose exec -T backend python manage.py "
        "report_hook_false_positive --hook check-deferral-filed "
        "--context \"<explanation>\"\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
