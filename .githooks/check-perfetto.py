#!/usr/bin/env python3
"""Hard check for unresolved Perfetto trace-analysis AutoIssues.

Perfetto traces surface performance regressions — slow spans, lock
contention, scheduling stalls. Each is filed as an AutoIssue. This gate
refuses the commit while any Perfetto AutoIssue is still open.
"""

from __future__ import annotations

import subprocess
import sys


def _fail(detail: str) -> int:
    sys.stderr.write(
        "\nFAIL check-perfetto: unresolved Perfetto trace-analysis AutoIssues.\n"
        "WHY: Perfetto findings are measured performance regressions (slow "
        "spans, lock contention, scheduling stalls). Committing past them lets "
        "the slowdown reach production unreviewed.\n"
        "UNBLOCK: resolve each open Perfetto AutoIssue (fix or optimize the "
        "hotspot, then mark it resolved with two-part lessons), or review it "
        "down. Inspect with:\n"
        "  docker compose exec -T backend python manage.py print_open_issues\n"
        f"\nDetail from the database check:\n{detail}\n"
    )
    return 1


def main() -> int:
    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "verify_perfetto_autoissues",
        "--max-open", "10", "--block-open",
    ]
    try:
        proc = subprocess.run(
            cmd, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False,
        )
    except FileNotFoundError:
        return _fail(
            "Docker is not available; the Perfetto database check could not run. "
            "Start Docker Desktop and re-run."
        )
    if proc.returncode != 0:
        return _fail((proc.stdout + proc.stderr).strip() or "(no output)")
    sys.stdout.write(proc.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
