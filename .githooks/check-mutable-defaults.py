#!/usr/bin/env python3
"""Rule H.H4 — block mutable default arguments in Python (`def f(x=[])`).

File-scoped: only fires when staged Python files exist.
Reuses ruff's B006 rule (already wired). Reports a plain-English FAIL
with WHY + UNBLOCK when matches found.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _staged_py_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [
        line.strip() for line in (out.stdout or "").splitlines()
        if line.strip().endswith(".py")
        and line.strip().startswith(("backend/", "scripts/"))
    ]


def _ruff_command(files: list[str]) -> list[str]:
    """Return the best-available ruff invocation.

    Tries the `ruff` binary on PATH first (fast), falls back to
    `python -m ruff` when ruff is pip-installed under a user/site path that
    isn't exported to PATH (common on Windows). Both forms invoke the
    same Python module, so semantics match.
    """
    return ["python", "-m", "ruff", "check", "--select=B006", "--no-fix", *files]


def main() -> int:
    files = _staged_py_files()
    if not files:
        return 0
    try:
        result = subprocess.run(
            _ruff_command(files),
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            timeout=30, check=False,
        )
    except FileNotFoundError:
        sys.stderr.write(
            "FAIL check-mutable-defaults: `python -m ruff` is not available.\n"
            "WHY: Rule H.H4 delegates to ruff's B006 rule "
            "(mutable-argument-default) to catch `def func(items=[])` style "
            "bugs that share state across calls.\n"
            "UNBLOCK: `pip install ruff` (host Python) or run the check from "
            "inside the compiled-tools / backend container where ruff is "
            "already installed.\n"
        )
        return 2
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "FAIL check-mutable-defaults: ruff timed out after 30s.\n"
            "WHY: The check needs to run to completion to be reliable.\n"
            "UNBLOCK: Investigate the slow file; usually means an "
            "extremely large file. Split or simplify it.\n"
        )
        return 2

    # `python -m ruff` returns non-zero when ruff itself is not importable
    # (no module). Distinguish "ruff missing" from "ruff found bugs".
    if result.returncode != 0 and "No module named ruff" in (result.stderr or ""):
        sys.stderr.write(
            "FAIL check-mutable-defaults: ruff is not installed in this "
            "Python environment.\n"
            "WHY: same as above.\n"
            "UNBLOCK: `pip install ruff`.\n"
        )
        return 2

    if result.returncode == 0:
        return 0
    sys.stderr.write(
        "FAIL check-mutable-defaults: ruff B006 (mutable-argument-default) "
        "matched on staged Python files.\n"
        "WHY: Rule H.H4 forbids `def f(x=[])` / `def f(x={})` — Python "
        "evaluates the default ONCE and shares it across every call, which "
        "is almost always a subtle bug. Use `None` and assign inside:\n"
        "  def f(x=None):\n"
        "      x = x or []\n"
        "UNBLOCK: Apply the None-sentinel fix above, OR if this is a "
        "deliberate intent (rare), add `# noqa: B006` with a short justifier "
        "comment, OR file:\n"
        "  docker compose exec -T backend python manage.py "
        "report_hook_false_positive --hook check-mutable-defaults "
        "--context \"<explanation>\"\n"
        f"\nruff output:\n{result.stdout}\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
