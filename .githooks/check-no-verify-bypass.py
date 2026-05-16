#!/usr/bin/env python3
"""Pre-push check that catches `git commit --no-verify` bypasses.

A normal commit lands the required markers in `AGENT-HANDOFF.md` via the
pre-commit hook chain. When an agent bypasses with `--no-verify`, the
markers never get added but the commit still lands locally. At push time
this hook scans every commit being pushed and refuses any code-changing
commit whose diff did NOT touch `AGENT-HANDOFF.md`. Touching the handoff is
the proof that the agent ran the pre-commit chain (or at least made the
markers visible to the next reviewer).

The hook is invoked by `.githooks/pre-push` BEFORE
`scripts/prepush-docker.sh` so the bypass check happens before any slow
language tooling. Stdin is forwarded from git in the standard pre-push
contract:

    <local_ref> <local_sha> <remote_ref> <remote_sha>

Rule F-compliant: three-part FAIL with what / why / unblock.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ZERO_SHA = "0" * 40
HANDOFF_FILE = "AGENT-HANDOFF.md"

_SOURCE_PREFIXES = (
    "backend/apps/",
    "backend/extensions/",
    "backend/config/",
    "frontend/src/",
    "scripts/",
    "services/",
    ".githooks/",
)
_SOURCE_SUFFIXES = (".py", ".cpp", ".h", ".ts", ".tsx", ".go", ".sh")


def _git(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout or ""


def commits_in_range(remote_sha: str, local_sha: str) -> list[str]:
    """Return the list of commits being pushed."""
    if local_sha == ZERO_SHA:
        return []  # Branch deletion; nothing to verify.
    if remote_sha == ZERO_SHA:
        out = _git(["rev-list", local_sha, "--not", "--remotes"])
    else:
        out = _git(["rev-list", f"{remote_sha}..{local_sha}"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def files_touched(commit: str) -> list[str]:
    out = _git(["show", "--name-only", "--pretty=format:", commit])
    return [line.strip() for line in out.splitlines() if line.strip()]


def production_source_hits(files: list[str]) -> list[str]:
    hits: list[str] = []
    for path in files:
        if not path.startswith(_SOURCE_PREFIXES):
            continue
        if not path.endswith(_SOURCE_SUFFIXES):
            continue
        name = Path(path).name.lower()
        # Test-only commits do not need a handoff marker.
        if (
            name.startswith("test_")
            or name.startswith("tests_")
            or name.endswith("_test.go")
            or "/test/" in path.replace("\\", "/")
            or "/tests/" in path.replace("\\", "/")
        ):
            continue
        hits.append(path)
    return hits


def commit_subject(commit: str) -> str:
    return _git(["show", "-s", "--format=%s", commit]).strip()


def _emit_failure(violations: list[tuple[str, str, list[str]]]) -> None:
    sys.stderr.write(
        "FAIL check-no-verify-bypass: one or more pushed commits look like "
        "a --no-verify bypass (production source changed but "
        "AGENT-HANDOFF.md was not touched).\n"
        "WHY: Rule B + Rule F forbid --no-verify. Every code-changing "
        "commit MUST update AGENT-HANDOFF.md with the required markers "
        "(TDD CYCLE, PERFORMANCE PROOF, REGISTRY READ, PAPER TRAIL READ, "
        "CODE REVIEW LESSONS). A commit that changes source but leaves "
        "the handoff untouched almost certainly bypassed the pre-commit "
        "chain, which means the markers are missing and the next agent "
        "loses the audit trail.\n"
        "UNBLOCK: For each commit below either (a) amend it to include an "
        "AGENT-HANDOFF.md entry with the required markers and "
        "force-push (only safe on a personal branch -- never main), or "
        "(b) reset, redo the commit through the normal pre-commit chain, "
        "and re-push. Do not push --no-verify.\n\n"
    )
    for sha, subject, hits in violations:
        sys.stderr.write(f"  {sha[:12]}  {subject[:60]}\n")
        for path in hits[:5]:
            sys.stderr.write(f"      touched: {path}\n")
        if len(hits) > 5:
            sys.stderr.write(f"      ... and {len(hits) - 5} more\n")


def main(stdin_lines: list[str] | None = None) -> int:
    """Scan pushed commits and FAIL on bypass shape.

    `stdin_lines` is exposed for tests so they can drive the hook without
    feeding real stdin. main() reads sys.stdin by default.
    """
    if stdin_lines is None:
        stdin_lines = list(sys.stdin)
    violations: list[tuple[str, str, list[str]]] = []
    for line in stdin_lines:
        parts = line.strip().split()
        if len(parts) < 4:
            continue
        _local_ref, local_sha, _remote_ref, remote_sha = parts[:4]
        for commit in commits_in_range(remote_sha, local_sha):
            files = files_touched(commit)
            source_hits = production_source_hits(files)
            if not source_hits:
                continue
            if HANDOFF_FILE in files:
                continue
            violations.append((commit, commit_subject(commit), source_hits))
    if violations:
        _emit_failure(violations)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
