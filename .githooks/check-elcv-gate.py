#!/usr/bin/env python3
"""Pre-commit ELCV gate — HARD-BLOCKS NEW code-quality violations in staged Python files.

Safety by design:
  * enforces on CHANGED code only (staged files), and
  * grandfathers every pre-existing issue via tools/elcv/gate-baseline.json, so it never
    blocks a legacy file you merely touched, and
  * fails OPEN on an internal tool error (prints a warning, never bricks a commit).

Wired into scripts/precommit-docker.sh:
    run_hard_gate check-elcv-gate python .githooks/check-elcv-gate.py
Suppress one finding with a written reason (never `--no-verify`):
    # elcv: allow <RULE_ID> -- <reason>
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ELCV = REPO / "tools" / "elcv"
BASELINE = ELCV / "gate-baseline.json"
USO_INDEX = ELCV / "uso-index.json"
sys.path.insert(0, str(ELCV))


def _staged_python_files():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, cwd=str(REPO),
    ).stdout
    return [Path(line) for line in out.splitlines() if line.endswith(".py")]


def main() -> int:
    os.chdir(REPO)  # repo-relative paths, so finding keys match the baseline/index
    try:
        import gate  # noqa: E402
        files = [p for p in _staged_python_files() if p.exists()]
        if not files:
            return 0
        index = json.loads(USO_INDEX.read_text(encoding="utf-8")) if USO_INDEX.exists() else None
        findings = gate.run_gate(files, index)
        if BASELINE.exists():
            grandfathered = set(json.loads(BASELINE.read_text(encoding="utf-8")))
            findings = gate.filter_baseline(findings, grandfathered)
    except Exception as exc:  # never block a commit on a bug in the gate itself
        print(f"WARN check-elcv-gate skipped (tool error: {exc})")
        return 0

    if not findings:
        return 0

    ordered = sorted(findings, key=lambda x: (x.path, x.line))
    first = ordered[0]
    print(f"FAIL check-elcv-gate: {len(findings)} new ELCV quality violation(s) in staged Python files")
    print(f"WHY: {first.rule} at {first.path}:{first.line} -- {first.message} "
          f"(the ELCV gate hard-blocks code-quality regressions in new/changed code)")
    print("UNBLOCK: fix the issues below, or add `# elcv: allow <RULE_ID> -- <reason>` on the line")
    for f in ordered:
        print(f"  BLOCK {f.rule}  {f.path}:{f.line}  {f.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
