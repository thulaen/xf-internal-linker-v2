#!/usr/bin/env python3
"""Hard check for unresolved GWP-ASan memory-safety AutoIssues.

GWP-ASan catches heap corruption (use-after-free, buffer overflow) in the
C++ extensions. Any finding it produces is a real memory-safety bug. This
gate refuses the commit while any GWP-ASan AutoIssue is still open.
"""

from __future__ import annotations

import subprocess
import sys


def _fail(detail: str) -> int:
    sys.stderr.write(
        "\nFAIL check-gwp-asan: unresolved GWP-ASan memory-safety AutoIssues.\n"
        "WHY: GWP-ASan findings are real heap-corruption bugs (use-after-free, "
        "buffer overflow) in the C++ extensions. Shipping them risks crashes "
        "and silent data corruption.\n"
        "UNBLOCK: resolve each open GWP-ASan AutoIssue (fix the C++ defect, then "
        "mark it resolved with two-part lessons), or review it down. Inspect with:\n"
        "  docker compose exec -T backend python manage.py print_open_issues\n"
        f"\nDetail from the database check:\n{detail}\n"
    )
    return 1


def main() -> int:
    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "verify_gwp_asan_autoissues",
        "--max-open", "10", "--block-open",
    ]
    try:
        proc = subprocess.run(
            cmd, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False,
        )
    except FileNotFoundError:
        return _fail(
            "Docker is not available; the GWP-ASan database check could not run. "
            "Start Docker Desktop and re-run."
        )
    if proc.returncode != 0:
        return _fail((proc.stdout + proc.stderr).strip() or "(no output)")
    sys.stdout.write(proc.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
