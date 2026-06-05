#!/usr/bin/env python3
"""Validate the GitHub Actions failure-history session marker."""

from __future__ import annotations

import re
import subprocess
import sys
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_FAILURE_EXIT = 2
_CODE_PREFIXES = ("backend/", "frontend/", "scripts/", ".githooks/", "backend/extensions/", "services/")
_SNAPSHOTS_RE = re.compile(r"\[SNAPSHOTS\s+READ:\s*[^\]]+\]", re.IGNORECASE)
_GH_RE = re.compile(r"\[GH\s+ACTIONS\s+READ:\s*(?P<body>[^\]]+)\]", re.IGNORECASE)
_ZERO_RE = re.compile(r"^0\s+failures\s+since\s+last\s+handoff\s*(?:—|--|-)\s*picked:\s*none$", re.I)
_FULL_RE = re.compile(
    r"^(?P<count>[1-9]\d*)\s+failures\s+since\s+last\s+handoff\s*(?:—|--|-)\s*"
    r"picked:\s*(?P<picks>#[A-Za-z0-9_-]+(?:\s*,\s*#[A-Za-z0-9_-]+){0,2})$",
    re.I,
)
_PICK_RE = re.compile(r"#[A-Za-z0-9_-]+")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_helpers import file_finding_or_hard, get_staged_handoff_diff  # noqa: E402


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


def _is_code_changing(files: list[str]) -> bool:
    return any(path.startswith(_CODE_PREFIXES) for path in files)


def validate(added_diff: str) -> int:
    """Validate marker order and shape."""
    snapshots_match = _SNAPSHOTS_RE.search(added_diff)
    if snapshots_match is None:
        return 0
    gh_match = _GH_RE.search(added_diff)
    if gh_match is None:
        _format_missing_failure()
        return _FAILURE_EXIT
    if gh_match.start() < snapshots_match.start():
        _format_order_failure()
        return _FAILURE_EXIT
    return _validate_body(gh_match.group("body").strip())


def _validate_body(body: str) -> int:
    if _ZERO_RE.match(body):
        return 0
    match = _FULL_RE.match(body)
    if match is None:
        _format_shape_failure(body)
        return _FAILURE_EXIT
    expected = min(int(match.group("count")), 3)
    if len(_PICK_RE.findall(match.group("picks"))) != expected:
        _format_shape_failure(body)
        return _FAILURE_EXIT
    return 0


def _format_missing_failure() -> None:
    sys.stderr.write(
        "FAIL check-gh-actions-read: the staged AGENT-HANDOFF.md entry is "
        "missing the [GH ACTIONS READ: ...] marker.\n"
        "WHY: failed GitHub Actions runs are now tracked in "
        "audit/github_actions_failures.jsonl, and the next session must state "
        "which recent failures it saw before changing code.\n"
        "UNBLOCK: run `python manage.py print_failed_github_actions "
        "--since-handoff`, paste the printed marker after [SNAPSHOTS READ: ...], "
        "stage AGENT-HANDOFF.md, and retry the commit.\n"
    )


def _format_order_failure() -> None:
    sys.stderr.write(
        "FAIL check-gh-actions-read: [GH ACTIONS READ: ...] appears before "
        "[SNAPSHOTS READ: ...].\n"
        "WHY: the session-start markers must stay in reading order.\n"
        "UNBLOCK: move [GH ACTIONS READ: ...] immediately after "
        "[SNAPSHOTS READ: ...] in the same handoff entry.\n"
    )


def _format_shape_failure(body: str) -> None:
    sys.stderr.write(
        "FAIL check-gh-actions-read: [GH ACTIONS READ: ...] has the wrong shape.\n"
        f"  got body: {body!r}\n"
        "WHY: the marker must be `[GH ACTIONS READ: <N> failures since last "
        "handoff — picked: #<run_id>, #<run_id>, #<run_id>]`, or use "
        "`picked: none` when N is 0.\n"
        "UNBLOCK: rerun `python manage.py print_failed_github_actions "
        "--since-handoff` and paste the exact line.\n"
    )


def main() -> int:
    files = _staged_files()
    if not files or not _is_code_changing(files):
        return 0
    added = _read_staged_handoff_diff()
    if not added:
        return 0
    captured = StringIO()
    with redirect_stderr(captured):
        result = validate(added)
    if result == 0:
        return 0
    return file_finding_or_hard(
        category="gh_actions_not_read",
        severity="low",
        subject="AGENT-HANDOFF.md:1",
        message=captured.getvalue(),
        hook="check-gh-actions-read",
        repo_root=REPO_ROOT,
    )


if __name__ == "__main__":
    sys.exit(main())
