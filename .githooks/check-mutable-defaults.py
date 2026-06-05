#!/usr/bin/env python3
"""Rule H.H4 — block mutable default arguments in Python (`def f(x=[])`).

File-scoped: only fires when staged Python files exist.
Reuses ruff's B006 rule (already wired). Reports a plain-English FAIL
with WHY + UNBLOCK when matches found.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_RUFF_ARGS = ["check", "--select=B006", "--no-fix"]


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


def _local_ruff_argv() -> list[str] | None:
    """Local ruff invocation if ruff is usable in this environment, else None.

    Prefers the `ruff` binary on PATH (fast); falls back to `python -m ruff`
    only when ruff is importable by this interpreter. Returns None when ruff
    is unavailable locally so the caller routes to the backend-quality
    container instead (the repo rule keeps ruff in backend-quality, not on
    the lean runtime/host).
    """
    if shutil.which("ruff"):
        return ["ruff", *_RUFF_ARGS]
    probe = subprocess.run(
        [sys.executable, "-c", "import ruff"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        timeout=15, check=False,
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", "ruff", *_RUFF_ARGS]
    return None


def _container_ruff_argv() -> list[str]:
    """Run ruff in backend-quality, where the quality toolchain lives."""
    return [
        "docker", "compose", "run", "--rm", "-T", "-w", "/repo",
        "backend-quality", "python", "-m", "ruff", *_RUFF_ARGS,
    ]


def _run_ruff(files: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Run ruff B006 over *files* locally, falling back to backend-quality.

    Returns the CompletedProcess, or None if neither path could run ruff
    (e.g. Docker is down and ruff is absent locally).
    """
    local = _local_ruff_argv()
    if local is not None:
        try:
            return subprocess.run(
                [*local, *files], cwd=str(REPO_ROOT),
                capture_output=True, text=True, timeout=60, check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # fall through to the container path
    # backend-quality fallback (no path conversion on git-bash for -w /repo)
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    try:
        return subprocess.run(
            [*_container_ruff_argv(), *files], cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=180, check=False, env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def main() -> int:
    files = _staged_py_files()
    if not files:
        return 0
    result = _run_ruff(files)
    if result is None or (
        result.returncode != 0 and "No module named ruff" in (result.stderr or "")
    ):
        sys.stderr.write(
            "FAIL check-mutable-defaults: ruff could not be run locally or in "
            "the backend-quality container.\n"
            "WHY: Rule H.H4 delegates to ruff's B006 rule "
            "(mutable-argument-default) to catch `def func(items=[])` style "
            "bugs that share state across calls. Per the quality-tool rule, "
            "ruff lives in the backend-quality image, not on the host.\n"
            "UNBLOCK: start Docker Desktop so `docker compose run --rm "
            "backend-quality python -m ruff` is reachable, then re-run.\n"
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
