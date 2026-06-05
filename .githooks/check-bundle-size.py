#!/usr/bin/env python3
"""Pre-push gate against frontend bundle-size regression.

Closes Gap #11 from `docs/OBSERVABILITY-GAPS-EXTENSION.md`. Fails the
push if the prod Angular bundle's main.js grows more than 10 % above
the baseline. The baseline lives at `.bundle-size-baseline.json` at
repo root.

Workflow:
  1. Read the latest `frontend/dist/xf-internal-linker-frontend/main-*.js`.
  2. Sum file sizes of main + lazy chunks.
  3. Compare to `.bundle-size-baseline.json`'s `bytes`.
  4. If new > baseline × 1.10 → fail.
  5. If new < baseline × 0.90 → suggest updating the baseline.

Skips silently when no built bundle exists (the dev hasn't run
`scripts/build-smart.ps1 --target frontend-build` yet); the gate only
fires after a build has happened.

Usage:
    python .githooks/check-bundle-size.py
        — fails the push if regressed
    python .githooks/check-bundle-size.py --update-baseline
        — writes the current size as the new baseline
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / ".bundle-size-baseline.json"
DIST_DIR = REPO_ROOT / "frontend" / "dist" / "xf-internal-linker-frontend" / "browser"

_TOLERANCE = 1.10  # 10% growth allowed
_IMPROVEMENT_THRESHOLD = 0.90  # suggest update if shrunk 10 %+


def _measure_current_size() -> int | None:
    """Sum sizes of main-*.js + chunk-*.js + styles-*.css in the prod bundle."""
    if not DIST_DIR.exists():
        return None
    total = 0
    for pattern in ("main-*.js", "chunk-*.js", "styles-*.css"):
        for f in DIST_DIR.glob(pattern):
            try:
                total += f.stat().st_size
            except OSError:
                continue
    return total or None


def _read_baseline() -> int | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return int(json.loads(BASELINE_PATH.read_text())["bytes"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def _write_baseline(b: int) -> None:
    BASELINE_PATH.write_text(json.dumps({"bytes": b}, indent=2) + "\n")


def _fmt(b: int) -> str:
    return f"{b / 1024:.0f} KB ({b:,} bytes)"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    current = _measure_current_size()
    if current is None:
        print(
            "[check-bundle-size] no built bundle in "
            f"{DIST_DIR} — skipping (run `scripts/build-smart.ps1 "
            "--target frontend-build` first to enable).",
            file=sys.stderr,
        )
        return 0  # not a hard failure when nothing to measure

    if args.update_baseline:
        _write_baseline(current)
        print(f"[check-bundle-size] baseline updated → {_fmt(current)}")
        return 0

    baseline = _read_baseline()
    if baseline is None:
        _write_baseline(current)
        print(
            f"[check-bundle-size] no baseline — seeded with {_fmt(current)}. "
            "Re-run to enforce."
        )
        return 0

    ratio = current / baseline
    if ratio > _TOLERANCE:
        print(
            f"\033[31m[check-bundle-size] FAIL\033[0m: bundle grew from "
            f"{_fmt(baseline)} → {_fmt(current)} ({(ratio-1)*100:+.1f}%, "
            f"tolerance +{(_TOLERANCE-1)*100:.0f}%). Inspect the new "
            f"chunks (`ls -laS {DIST_DIR}`) to find the culprit, OR run "
            f"`python .githooks/check-bundle-size.py --update-baseline` "
            f"if the growth is intentional.",
            file=sys.stderr,
        )
        return 1
    if ratio < _IMPROVEMENT_THRESHOLD:
        print(
            f"[check-bundle-size] bundle shrank from {_fmt(baseline)} → "
            f"{_fmt(current)} ({(ratio-1)*100:+.1f}%). Run "
            f"`python .githooks/check-bundle-size.py --update-baseline` "
            f"to lock in the new baseline."
        )
    else:
        print(
            f"[check-bundle-size] OK ({_fmt(baseline)} → {_fmt(current)}, "
            f"{(ratio-1)*100:+.1f}%)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
