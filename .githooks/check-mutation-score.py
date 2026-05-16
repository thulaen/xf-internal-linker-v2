#!/usr/bin/env python3
"""Mutation-score ratchet — FR-251 Gap #4.

Reads `.mutation-score-baseline.json` at repo root and the latest
mutation-tool report (mutmut, Stryker, or Mull JSON) and fails
if the mutation score for the named (tool, target) pair has dropped
below the recorded floor.

Usage:
    python .githooks/check-mutation-score.py \\
        --tool mutmut \\
        --target apps/auto_issues/services/fingerprinting.py \\
        --report backend/reports/mutmut.json

    python .githooks/check-mutation-score.py \\
        --tool stryker \\
        --target src/app/core/services/a11y-prefs.service.ts \\
        --report frontend/reports/stryker.json

    python .githooks/check-mutation-score.py \\
        --tool mull \\
        --target test_fieldrel \\
        --report backend/extensions/reports/mull/mutants.json

Exit codes:
    0 — score met or exceeded the baseline, OR baseline is null (not seeded).
    1 — score dropped below the baseline.
    2 — report file unparseable or tool not recognised.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / ".mutation-score-baseline.json"


def _load_baseline() -> dict[str, float | None]:
    if not BASELINE_PATH.is_file():
        return {}
    with BASELINE_PATH.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("baselines", {})


def _read_report(path: Path) -> Any:
    if not path.is_file():
        sys.stderr.write(f"check-mutation-score: report {path} not found\n")
        sys.exit(1)
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"check-mutation-score: report unparseable: {e}\n")
        sys.exit(2)


def _mutmut_score(data: Any) -> float | None:
    """mutmut JSON: list of mutants with status. Score = killed / total."""
    items = data if isinstance(data, list) else data.get("mutants", [])
    if not items:
        return None
    killed = sum(1 for m in items if m.get("status") == "killed")
    return 100.0 * killed / len(items)


def _stryker_score(data: Any) -> float | None:
    """Stryker JSON: top-level `mutationScore` field, or compute from files."""
    if isinstance(data, dict) and "mutationScore" in data:
        return float(data["mutationScore"])
    files = data.get("files", {}) if isinstance(data, dict) else {}
    killed = total = 0
    for payload in files.values():
        for m in payload.get("mutants", []):
            total += 1
            if m.get("status") in ("Killed", "Timeout"):
                killed += 1
    return (100.0 * killed / total) if total else None


def _mull_score(data: Any) -> float | None:
    """Mull Elements JSON: either a top-level mutationScore int, or a
    files-keyed dict whose entries each carry a mutants list with status.
    """
    if isinstance(data, dict) and isinstance(data.get("mutationScore"), (int, float)):
        return float(data["mutationScore"])
    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        if isinstance(data.get("mutants"), list):
            items = data["mutants"]
        else:
            for file_info in data.get("files", {}).values():
                if isinstance(file_info, dict) and isinstance(file_info.get("mutants"), list):
                    items.extend(file_info["mutants"])
    if not items:
        return None
    killed = sum(
        1 for m in items if isinstance(m, dict) and m.get("status") in ("Killed", "Timeout")
    )
    return 100.0 * killed / len(items)


_PARSERS = {
    "mutmut": _mutmut_score,
    "stryker": _stryker_score,
    "mull": _mull_score,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True, choices=list(_PARSERS.keys()))
    parser.add_argument("--target", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--seed-if-empty",
        action="store_true",
        help="If baseline entry is null, write current score back to the baseline file.",
    )
    opts = parser.parse_args()

    baseline = _load_baseline()
    key = f"{opts.tool}:{opts.target}"
    floor = baseline.get(key)

    data = _read_report(opts.report)
    score = _PARSERS[opts.tool](data)
    if score is None:
        sys.stderr.write(f"check-mutation-score: could not compute score for {key}\n")
        return 1

    if floor is None:
        if opts.seed_if_empty:
            baseline[key] = round(score, 1)
            payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
            payload["baselines"] = baseline
            BASELINE_PATH.write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8",
            )
            print(f"check-mutation-score: SEEDED {key}={score:.1f}%")
            return 0
        print(f"check-mutation-score: {key} baseline=null (not seeded); current={score:.1f}%")
        return 0

    if score + 0.01 < floor:
        sys.stderr.write(
            f"\nFAIL check-mutation-score: {key} dropped from {floor:.1f}% to {score:.1f}% "
            f"(drop of {floor - score:.1f}pp)\n\n"
            "The mutation-score ratchet only goes UP. Add tests that kill the "
            "newly-surviving mutants, or (rarely) lower the floor in a separate "
            "commit with an explicit reason.\n"
        )
        return 1

    print(f"check-mutation-score: {key}={score:.1f}% (floor={floor:.1f}%) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
