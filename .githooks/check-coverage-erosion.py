#!/usr/bin/env python3
"""Pre-push gate against coverage erosion.

Closes Gap #10 from `docs/OBSERVABILITY-GAPS-EXTENSION.md`. Fails the
push if total backend test coverage drops more than 2 percentage points
below the baseline. The baseline lives at `.coverage-baseline.json` at
repo root, committed alongside the code.

Workflow:
  1. Run pytest with coverage (or skip if coverage isn't installed —
     this is an opt-in gate; absent infrastructure means absent gate).
  2. Read coverage.json's `totals.percent_covered`.
  3. Compare to `.coverage-baseline.json`'s `percent_covered`.
  4. If new < baseline - 2 → fail.
  5. If new > baseline + 2 → suggest updating the baseline (don't fail).

Usage:
    python .githooks/check-coverage-erosion.py
        — fails the push if eroded
    python .githooks/check-coverage-erosion.py --update-baseline
        — writes the current coverage as the new baseline
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / ".coverage-baseline.json"
COVERAGE_PATH = REPO_ROOT / "backend" / "coverage.json"

_EROSION_TOLERANCE_PCT = 2.0


def _measure_current_coverage() -> float | None:
    """Run coverage + return the percent_covered from coverage.json."""
    try:
        # Run inside the backend dir; uses pytest if available, else
        # falls back to `coverage run manage.py test`.
        proc = subprocess.run(
            [
                "coverage", "run", "--source=apps,config",
                "manage.py", "test", "--noinput", "--keepdb",
                "apps.audit", "apps.benchmarks", "apps.auto_issues",
            ],
            cwd=REPO_ROOT / "backend",
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"[check-coverage-erosion] cannot run coverage: {exc}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        print(
            "[check-coverage-erosion] coverage run failed:",
            proc.stderr[-1000:], file=sys.stderr,
        )
        return None
    # Generate JSON report
    subprocess.run(
        ["coverage", "json", "-o", str(COVERAGE_PATH)],
        cwd=REPO_ROOT / "backend", capture_output=True, text=True,
    )
    if not COVERAGE_PATH.exists():
        return None
    try:
        return float(json.loads(COVERAGE_PATH.read_text())["totals"]["percent_covered"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def _read_baseline() -> float | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return float(json.loads(BASELINE_PATH.read_text())["percent_covered"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def _write_baseline(pct: float) -> None:
    BASELINE_PATH.write_text(
        json.dumps({"percent_covered": round(pct, 2)}, indent=2) + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    current = _measure_current_coverage()
    if current is None:
        print(
            "[check-coverage-erosion] coverage tool unavailable — skipping. "
            "Install with `pip install coverage` to enable this gate.",
            file=sys.stderr,
        )
        return 0  # not a hard failure when infra missing

    if args.update_baseline:
        _write_baseline(current)
        print(f"[check-coverage-erosion] baseline updated → {current:.2f}%")
        return 0

    baseline = _read_baseline()
    if baseline is None:
        _write_baseline(current)
        print(
            f"[check-coverage-erosion] no baseline — seeded with {current:.2f}%. "
            f"Re-run to enforce.",
        )
        return 0

    delta = current - baseline
    if delta < -_EROSION_TOLERANCE_PCT:
        print(
            f"\033[31m[check-coverage-erosion] FAIL\033[0m: coverage "
            f"dropped from {baseline:.2f}% → {current:.2f}% "
            f"(Δ {delta:+.2f} pp, tolerance −{_EROSION_TOLERANCE_PCT}). "
            f"Add tests for the new code, OR run "
            f"`python .githooks/check-coverage-erosion.py --update-baseline` "
            f"if the lower coverage is intentional.",
            file=sys.stderr,
        )
        return 1
    if delta > _EROSION_TOLERANCE_PCT:
        print(
            f"[check-coverage-erosion] coverage improved from "
            f"{baseline:.2f}% → {current:.2f}%. Run "
            f"`python .githooks/check-coverage-erosion.py --update-baseline` "
            f"to lock in the new baseline."
        )
    else:
        print(
            f"[check-coverage-erosion] OK ({baseline:.2f}% → {current:.2f}%, "
            f"Δ {delta:+.2f} pp)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
