#!/usr/bin/env python3
"""PARAMOUNT — TDD pipeline session-close gate (Session S4, added 2026-05-18).

HARD-BLOCKS the FIRST code-changing commit of a NEW session when the
prior session's final AGENT-HANDOFF.md entry lacks a `[SESSION CLOSE: …]`
marker. Cleanly enforces "you can't start a new session with the
previous session's artefact bloat still on disk."

Detection of "first commit of a new session": the staged
AGENT-HANDOFF.md diff adds a new top-level session header
(line matching `^# \\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}\\s+-\\s+`).
Mid-session commits do not fire the gate.

Exemptions:
  * Pure-docs / generated-only commits.
  * Rule-introduction commit (docs/TDD-PIPELINE-RULE.md is staged).

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

_SESSION_HEADER_RE = re.compile(
    r"^#\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+-\s+",
    re.MULTILINE,
)


def _emit(msg: str) -> None:
    sys.stderr.write(msg)
    if not msg.endswith("\n"):
        sys.stderr.write("\n")


def _first_handoff_block(text: str) -> str:
    """Return the first `# YYYY-MM-DD HH:MM - …` block from text."""
    if not text:
        return ""
    headers = list(_SESSION_HEADER_RE.finditer(text))
    if not headers:
        return text  # no headers — treat whole text as one block
    first = headers[0]
    end = headers[1].start() if len(headers) > 1 else len(text)
    return text[first.start():end]


def _second_handoff_block(text: str) -> str:
    """Return the second handoff block, used when a new top entry is staged."""
    headers = list(_SESSION_HEADER_RE.finditer(text or ""))
    if len(headers) < 2:
        return ""
    second = headers[1]
    end = headers[2].start() if len(headers) > 2 else len(text)
    return text[second.start():end]


def _new_session_header_in_diff(diff: str) -> bool:
    """True iff the staged diff (added-lines only) introduces a new session header."""
    return bool(_SESSION_HEADER_RE.search(diff))


def _read_handoff_at_head() -> str:
    """Read AGENT-HANDOFF.md as it exists in the HEAD commit."""
    try:
        result = subprocess.run(
            ["git", "show", "HEAD:AGENT-HANDOFF.md"],
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
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def _read_handoff_at_index() -> str:
    """Read AGENT-HANDOFF.md as staged in the index, if present."""
    try:
        result = subprocess.run(
            ["git", "show", ":AGENT-HANDOFF.md"],
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
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def validate_session_close(
    *,
    head_handoff: str,
    staged_handoff_diff: str,
    staged_files: list[str],
    staged_handoff_full: str = "",
) -> int:
    """Return 0 (pass) or 2 (hard-block). Exposed for tests."""
    production_files = [f for f in staged_files if is_production_source(f)]
    if not production_files:
        return 0  # pure-docs / generated-only commit

    if _GRANDFATHER_SPEC in staged_files:
        return 0  # rule-introduction commit

    if not _new_session_header_in_diff(staged_handoff_diff):
        return 0  # mid-session commit — gate stays quiet

    prior_block = _second_handoff_block(staged_handoff_full) or _first_handoff_block(
        head_handoff
    )
    if "[SESSION CLOSE:" in prior_block:
        return 0

    _emit(
        "FAIL check-session-close: this commit starts a new session in "
        "AGENT-HANDOFF.md but the prior session's entry lacks a "
        "[SESSION CLOSE: ...] marker.\n"
        "WHY: PARAMOUNT TDD-pipeline rule says every session ends with "
        "`manage.py session_close` which verifies the session's lessons "
        "are logged and prunes the test-artefact prefixes (mull, coverage, "
        "mutmut, stryker, fuzz-work, pytest-debug). Skipping it leaves "
        "the next session inheriting hundreds of MiB of stale build "
        "output and breaks the chain of evidence that proves the "
        "previous TDD cycles were captured as lessons.\n"
        "UNBLOCK: STOP, then run `docker compose exec -T backend python "
        "manage.py session_close` to close out the prior session. Paste "
        "the printed [SESSION CLOSE: ...] marker into the bottom of the "
        "prior session's AGENT-HANDOFF.md entry, amend that prior entry "
        "into HEAD (or land a small docs-only commit), and re-run this "
        "commit.\n"
    )
    return 2


def main() -> int:
    staged = get_staged_files(REPO_ROOT)
    if not staged:
        return 0
    diff = get_staged_handoff_diff(REPO_ROOT)
    head_handoff = _read_handoff_at_head()
    staged_handoff = _read_handoff_at_index()
    return validate_session_close(
        head_handoff=head_handoff,
        staged_handoff_diff=diff,
        staged_files=staged,
        staged_handoff_full=staged_handoff,
    )


if __name__ == "__main__":
    sys.exit(main())
