#!/usr/bin/env python3
"""Rule H.30 — auto-log every hook failure to AutoIssue.

When ANY pre-commit hook in `.githooks/check-*.py` exits non-zero,
the wrapper in `scripts/precommit-docker.sh` calls this helper to
file an `AutoIssue(category='hook_failure')` so the failure becomes
searchable, dedupable, fixable work — not just an ephemeral block.

This helper itself ALWAYS exits 0. The failing hook already set
the failing exit code that blocks the commit; we just record the
failure for later operator triage.

Usage:
    python .githooks/_auto_log_failure.py --hook <name> \\
        --stderr-snippet "<first 200 chars of the hook's stderr>"
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto-log a pre-commit hook failure to AutoIssue.",
    )
    parser.add_argument("--hook", required=True)
    parser.add_argument("--stderr-snippet", default="")
    args = parser.parse_args()

    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "log_code_review_lessons",
        "--file", f".githooks/{args.hook}.py",
        "--title", f"[hook_failure] {args.hook} blocked a commit",
        "--abstract",
        f"Pre-commit hook {args.hook} fired and blocked a commit. "
        f"First-200-chars stderr: {args.stderr_snippet[:200] or '(empty)'}. "
        f"This auto-log is informational; the operator should triage the "
        f"AutoIssue to decide whether the hook needs tuning (file "
        f"manage.py report_hook_false_positive) or the underlying code "
        f"needs fixing.",
        "--severity", "medium",
        "--agent", "auto-logger",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # Best effort — never block on the auto-logger.
        sys.stderr.write(
            "WARN _auto_log_failure: docker not available; hook failure "
            f"({args.hook}) was not persisted to AutoIssue. Operator can "
            "still triage manually.\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
