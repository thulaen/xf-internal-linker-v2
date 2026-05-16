"""Shared helpers for the .githooks/ pre-commit hook scripts.

Extracted 2026-05-16 to keep Rules J/K/L hooks under the duplicate-block
quality-debt threshold. Each hook used to carry its own copy of the
subprocess wrapper + staged-file diff + handoff-diff readers; this module
hosts the one shared implementation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_DEFAULT_TIMEOUT = 10


def run_git(repo_root: Path, args: list[str], timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Run a git subcommand from `repo_root` and return its stdout text.

    Returns an empty string if git is not on PATH or if the command
    times out. The hook's job is to report violations, not to bubble
    subprocess errors up to the user.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout or ""


def staged_paths(repo_root: Path) -> list[str]:
    """Return staged file paths added/modified/deleted (repo-relative)."""
    stdout = run_git(
        repo_root,
        ["diff", "--cached", "--name-only", "--diff-filter=ACMD"],
    )
    return [line.strip() for line in stdout.splitlines() if line.strip()]
