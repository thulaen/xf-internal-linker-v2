#!/usr/bin/env python3
"""Pre-commit gate for Rule A (20× speedup gate).

Hard-blocks when a staged source-file diff exists without a matching
[PERFORMANCE PROOF] or [PERFORMANCE EXEMPTION] marker in the staged
AGENT-HANDOFF.md entry. Rule F: every FAIL message is plain English
with (what fired, why, how to unblock).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_PERF_PROOF_RE = re.compile(r"\[PERFORMANCE PROOF:[^\]]+\]")
_PERF_EXEMPT_RE = re.compile(r"\[PERFORMANCE EXEMPTION:[^\]]+\]")
_SOURCE_PREFIXES = (
    "backend/apps/",
    "backend/extensions/",
    "backend/config/",
    "frontend/src/",
    "scripts/",
    ".githooks/",
)
_SOURCE_SUFFIXES = (".py", ".cpp", ".h", ".ts", ".tsx", ".js")


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
    source_files = _staged_source_files()
    if not source_files:
        return 0  # no production source files staged — gate doesn't fire
    handoff = _staged_handoff_diff()
    if not handoff:
        sys.stderr.write(
            "FAIL check-perf-proof: this commit modifies production source "
            f"({len(source_files)} files) but does not stage AGENT-HANDOFF.md.\n"
            "WHY: Rule A (20× speedup gate) requires every code change to "
            "include a [PERFORMANCE PROOF] or [PERFORMANCE EXEMPTION] marker "
            "in the handoff entry so the perf history is auditable.\n"
            "UNBLOCK: Run `docker compose exec -T backend python manage.py "
            "verify_perf_speedup --function <fn> --new-p50-ns <N>` and paste "
            "the marker line into a new AGENT-HANDOFF.md entry. Stage the "
            "handoff (`git add AGENT-HANDOFF.md`) and re-commit.\n"
        )
        return 2

    proofs = len(_PERF_PROOF_RE.findall(handoff))
    exemptions = len(_PERF_EXEMPT_RE.findall(handoff))
    if proofs + exemptions == 0:
        sys.stderr.write(
            "FAIL check-perf-proof: AGENT-HANDOFF.md was updated but does "
            "not include a [PERFORMANCE PROOF] or [PERFORMANCE EXEMPTION] "
            "marker.\n"
            "WHY: Rule A (20× speedup gate) — every staged production source "
            "file needs evidence of the perf measurement, either showing a "
            "≥20× speedup or a substantive exemption with the best-achieved "
            "ratio.\n"
            "UNBLOCK: Run `manage.py verify_perf_speedup --function <fn> "
            "--new-p50-ns <N> --iterations 10 --exemption-reason \"...\"` for "
            "each touched function and paste the output into the handoff.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
