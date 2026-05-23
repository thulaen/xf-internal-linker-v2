#!/usr/bin/env python3
"""
Pre-commit hook: enforce the Sticky #1 Read Rule (2026-05-23).

Every code-changing commit must carry a `[STICKY 1 READ: timestamp=...
sha256=<16-char-prefix> agent=...]` marker in the staged AGENT-HANDOFF
entry. The marker proves the agent ran `manage.py read_sticky --id 1`
in this session and received the sticky's full body. The hook
cross-checks the marker's SHA-256 prefix against the live sticky body
to catch mid-session amends that would let an in-session edit override
the constraints the session was supposed to honor.

Two exemption markers short-circuit the check:

* `[STICKY 1 BOOTSTRAP: commit=introduces-sticky]` — the single commit
  that introduces Sticky #1 itself.
* `[STICKY 1 EDIT: previous_sha=<prefix> new_sha=<prefix> reason="..."]`
  — a commit that amends the sticky body.

Pure-docs commits (no files under docs/specs/, docs/adr/, backend/,
frontend/, services/, scripts/, or .githooks/) are exempt.

Full spec at docs/specs/fr-sticky-1-read-rule.md.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Code-staging surfaces that the Sticky #1 read rule applies to. Pure-
# docs commits touching only .md / .txt / .json files outside these
# prefixes are exempt because they cannot introduce structural drift
# the sticky governs.
_CODE_PREFIXES = (
    "backend/",
    "frontend/",
    "scripts/",
    ".githooks/",
    "services/",
    "docs/specs/",
    "docs/adr/",
)

_STICKY_READ_RE = re.compile(
    r"\[STICKY\s+1\s+READ:\s*"
    r"timestamp=(?P<timestamp>\S+)\s+"
    r"sha256=(?P<sha>[0-9a-fA-F]{16})\s+"
    r"agent=(?P<agent>[^\]]+)\]"
)

_BOOTSTRAP_RE = re.compile(
    r"\[STICKY\s+1\s+BOOTSTRAP:\s*commit=introduces-sticky\]"
)

_EDIT_RE = re.compile(
    r"\[STICKY\s+1\s+EDIT:\s*"
    r"previous_sha=(?P<previous>[0-9a-fA-F]{16})\s+"
    r"new_sha=(?P<new>[0-9a-fA-F]{16})\s+"
    r'reason="(?P<reason>[^"]+)"\]'
)


def _fail(message: str) -> int:
    sys.stderr.write(message)
    return 2


def _staged_code_files() -> list[str]:
    """Return the staged-files list filtered to code-staging surfaces."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return [path for path in lines if any(path.startswith(p) for p in _CODE_PREFIXES)]


def _staged_handoff_diff() -> str:
    """Return the added-only lines of the staged AGENT-HANDOFF.md diff."""
    try:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--cached",
                "--unified=0",
                "--",
                "AGENT-HANDOFF.md",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    added_lines: list[str] = []
    for line in (result.stdout or "").splitlines():
        if line.startswith("+++"):
            continue
        if line.startswith("+"):
            added_lines.append(line[1:])
    return "\n".join(added_lines)


def _live_sticky_sha() -> str | None:
    """Return the live SHA-256 prefix for Sticky #1 (or None on error)."""
    try:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "backend",
                "python",
                "manage.py",
                "read_sticky",
                "--id",
                "1",
                "--print-sha-only",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip().splitlines()[-1] if result.stdout else None


def main() -> int:
    code_files = _staged_code_files()
    if not code_files:
        # Pure-docs commits are exempt.
        return 0

    handoff_text = _staged_handoff_diff()

    if _BOOTSTRAP_RE.search(handoff_text):
        # The single commit that introduces Sticky #1.
        return 0

    edit_match = _EDIT_RE.search(handoff_text)
    if edit_match:
        # The commit amends the sticky body; the new SHA is whatever
        # the agent just stored. We trust the marker because the
        # underlying log_sticky command is the source of truth.
        return 0

    read_match = _STICKY_READ_RE.search(handoff_text)
    if read_match is None:
        return _fail(
            "FAIL check-sticky-1-read: code-changing commit but the "
            "AGENT-HANDOFF.md entry is missing the [STICKY 1 READ: ...] "
            "marker.\n"
            "WHY: the 2026-05-23 Sticky #1 Read Rule requires every "
            "agent to run `manage.py read_sticky --id 1` at session "
            "start and paste the SHA-256-verified marker into the "
            "handoff entry before any code is written. The marker "
            "proves the policy text was received in this session, "
            "not paraphrased from memory. See "
            "docs/specs/fr-sticky-1-read-rule.md.\n"
            "UNBLOCK: run `docker compose exec -T backend python "
            "manage.py read_sticky --id 1` and paste the printed "
            "[STICKY 1 READ: ...] line verbatim into the AGENT-HANDOFF "
            "entry between the [REGISTRY READ: ...] and "
            "[GUIDELINES READ: ...] markers, then re-run the commit.\n"
        )

    marker_sha = read_match.group("sha").lower()
    live_sha = _live_sticky_sha()
    if live_sha is None:
        return _fail(
            "FAIL check-sticky-1-read: could not fetch the live SHA "
            "for Sticky #1 from the backend.\n"
            "WHY: the SHA cross-check requires the backend container "
            "to be reachable so the staged marker can be verified.\n"
            "UNBLOCK: confirm `docker compose ps backend` is running "
            "and the database is reachable; re-run the commit.\n"
        )
    if live_sha.lower() != marker_sha:
        return _fail(
            f"FAIL check-sticky-1-read: the marker's SHA ({marker_sha}) "
            f"does not match the live sticky body's SHA ({live_sha}).\n"
            "WHY: Sticky #1 has been amended since this session read "
            "it. The session-start SHA is now stale and the constraints "
            "the session was bound to may have changed. Re-reading is "
            "required so the commit lands under the current sticky.\n"
            "UNBLOCK: run `docker compose exec -T backend python "
            "manage.py read_sticky --id 1` again, replace the stale "
            "[STICKY 1 READ: ...] line in the AGENT-HANDOFF entry with "
            "the new one, and re-run the commit.\n"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
