#!/usr/bin/env python3
"""Per-module coverage ratchet — FR-251 Gap #1.

Reads `.coverage-baseline.json` at repo root and, for every file in the
staged diff (or in HEAD vs upstream for pre-push usage), verifies the
current coverage percentage is AT LEAST the recorded baseline.

The baseline only goes UP — when a PR raises a file's coverage past its
recorded value, the agent updates the entry; entries are never lowered.

Usage (pre-push hook):
    python .githooks/check-per-module-coverage.py [--against=origin/master]

Usage (CI):
    python .githooks/check-per-module-coverage.py --against=$BASE_SHA

Exit codes:
    0 — every touched file meets or exceeds its baseline (or has no entry,
        which is allowed during the gradual roll-out).
    1 — at least one touched file dropped below its baseline.
    2 — couldn't measure coverage (test failure upstream; surface honestly).

"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / ".coverage-baseline.json"

_TOTAL_LINE_RE = re.compile(
    r"^TOTAL\s+(?P<stmts>\d+)\s+(?P<miss>\d+)\s+(?:(?P<branch>\d+)\s+(?P<brmiss>\d+)\s+)?(?P<pct>[\d.]+)%",
    re.MULTILINE,
)


def _load_baseline() -> dict[str, float]:
    if not BASELINE_PATH.is_file():
        return {}
    with BASELINE_PATH.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("files", {})


def _changed_files(against: str) -> list[str]:
    """Files changed vs *against* — pre-push uses origin/master; staged
    use git diff --cached.
    """
    if against == "STAGED":
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
    else:
        cmd = ["git", "diff", "--name-only", f"{against}...HEAD", "--diff-filter=ACM"]
    try:
        out = subprocess.check_output(cmd, cwd=REPO_ROOT, text=True, errors="replace")
    except subprocess.CalledProcessError:
        return []
    return [
        line.strip() for line in out.splitlines()
        if line.strip().endswith(".py") and line.startswith("backend/")
    ]


def _measure(target: str) -> float | None:
    """Run coverage on *target*, return % or None on failure."""
    backend = REPO_ROOT / "backend"
    rel = target.removeprefix("backend/")
    try:
        subprocess.run(
            ["coverage", "erase"],
            cwd=backend, capture_output=True, check=False,
        )
        run = subprocess.run(
            [
                "coverage", "run",
                "--source", rel,
                "-m", "pytest", rel,
                "--override-ini", "addopts=",
                "-p", "randomly", "-q", "--no-cov", "--maxfail=5",
            ],
            cwd=backend, capture_output=True, text=True, check=False,
        )
        if run.returncode != 0:
            return None
        report = subprocess.run(
            ["coverage", "report", "--include", f"{rel}*"],
            cwd=backend, capture_output=True, text=True, check=False,
        )
        m = _TOTAL_LINE_RE.search(report.stdout)
        return float(m.group("pct")) if m else None
    except (FileNotFoundError, OSError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--against",
        default="origin/master",
        help="Git ref to diff against. Use 'STAGED' for pre-commit.",
    )
    opts = parser.parse_args()

    baseline = _load_baseline()
    if not baseline:
        print("check-per-module-coverage: empty baseline; nothing to enforce yet")
        return 0

    touched = _changed_files(opts.against)
    if not touched:
        return 0

    failures: list[tuple[str, float, float]] = []
    unmeasured: list[str] = []

    for path in touched:
        rel = path.removeprefix("backend/")
        floor = baseline.get(rel)
        if floor is None:
            continue  # file not yet in the baseline — allowed during roll-out

        current = _measure(path)
        if current is None:
            unmeasured.append(path)
            continue

        if current + 0.01 < floor:  # 0.01 fudge for float roundtrip
            failures.append((path, floor, current))

    if unmeasured:
        sys.stderr.write(
            "FAIL check-per-module-coverage: coverage could not be measured for "
            + ", ".join(unmeasured)
            + " (coverage tooling is unavailable or tests failed)\n"
        )
        return 2

    if failures:
        sys.stderr.write("\nFAIL check-per-module-coverage: regressions detected\n\n")
        for path, floor, current in failures:
            sys.stderr.write(
                f"  {path}: floor={floor:.1f}% actual={current:.1f}% "
                f"(drop of {floor - current:.1f}pp)\n"
            )
        sys.stderr.write(
            "\nThe per-module coverage ratchet only goes UP. To fix:\n"
            "  1. Add tests until each file is back AT OR ABOVE its floor.\n"
            "  2. OR if the floor was wrong, raise it in .coverage-baseline.json\n"
            "     in a SEPARATE commit with a clear reason (rare).\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
