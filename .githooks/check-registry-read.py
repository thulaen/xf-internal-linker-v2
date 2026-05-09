#!/usr/bin/env python3
"""Pre-commit guard for the auto-fix-2-issues rule.

When an AGENT-HANDOFF.md entry is added or edited in this commit, the new
content MUST include the `[REGISTRY READ: ...]` marker proving the agent
read the open auto-issues list before starting work. This is the same
pattern as the `[HANDOFF READ: ...]` marker, but enforced.

Why a hook instead of a memory rule: agents have repeatedly forgotten to
log new bugs into the registry / auto_issues table even though the rules
exist as text. A hook makes silent skipping impossible — the commit fails
loudly until the marker is present.

Bypass (intentional, e.g. mechanical merge): commit with --no-verify ONLY
if you can explain to the user in chat why the marker was skipped. The
hook has no allowlist.

Run manually:
    python .githooks/check-registry-read.py [path/to/AGENT-HANDOFF.md]
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDOFF = REPO_ROOT / "AGENT-HANDOFF.md"
MARKER_RE = re.compile(
    r"\[REGISTRY READ:\s*\d+\s+open auto-issues",
    re.IGNORECASE,
)


def _staged_diff_for(path: Path) -> str:
    """Return the staged additions for *path* (lines starting with '+ ')."""
    rel = path.relative_to(REPO_ROOT).as_posix()
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--unified=0", "--", rel],
            cwd=REPO_ROOT,
            text=True,
        )
    except subprocess.CalledProcessError:
        return ""
    added = "\n".join(
        line[1:] for line in out.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    return added


def _commit_touches_handoff() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            cwd=REPO_ROOT,
            text=True,
        )
    except subprocess.CalledProcessError:
        return False
    return any(line.strip() == "AGENT-HANDOFF.md" for line in out.splitlines())


def main() -> int:
    if not _commit_touches_handoff():
        return 0  # commit does not touch the handoff — rule does not apply
    added = _staged_diff_for(HANDOFF)
    if MARKER_RE.search(added):
        return 0
    sys.stderr.write(
        "\n\033[31m[check-registry-read]\033[0m FAIL: This commit modifies "
        "AGENT-HANDOFF.md but the new lines do not contain the "
        "`[REGISTRY READ: <N> open auto-issues ... — picked: #..., #...]` "
        "marker required by the ABSOLUTE rule in CLAUDE.md.\n"
        "  Run `docker compose exec -T backend python manage.py print_open_issues` "
        "first, pick two issues you will fix this session, and add the marker "
        "to the new handoff entry.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
