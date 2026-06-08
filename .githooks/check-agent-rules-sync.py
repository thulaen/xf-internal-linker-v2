#!/usr/bin/env python
"""Pre-commit gate for shared agent-rule drift."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = subprocess.run(
        [sys.executable, "scripts/sync_agent_rules.py", "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return 0
    print(
        "FAIL check-agent-rules-sync: shared agent rules drifted. "
        "WHY: CLAUDE.md, AGENTS.md, CODEX.md, and GEMINI.md must keep "
        "manifest-listed shared sections byte-identical. UNBLOCK: apply the "
        "same shared-section edit to all four files.",
        file=sys.stderr,
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
