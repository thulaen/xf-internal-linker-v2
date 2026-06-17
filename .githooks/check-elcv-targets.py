#!/usr/bin/env python3
"""HARD-BLOCK changes that erode a LOCKED ELCV target (the 2B-repo / 28M / 5M / 2B lock).

A scope marked "locked": true in tools/elcv/elcv-scopes.json may be RAISED but never
lowered, removed, or unlocked, unless the staged config carries a top-level
    "unlock": "<reason>"
field (a conscious, reviewed override). This stops any agent from silently down-scoping a
committed target (the Codex 28M->5M incident).

Wired into scripts/precommit-docker.sh:
    run_hard_gate check-elcv-targets python .githooks/check-elcv-targets.py
Fails OPEN on an internal error (never bricks a commit). Never use --no-verify.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CFG = "tools/elcv/elcv-scopes.json"
sys.path.insert(0, str(REPO / "tools" / "elcv"))


def _git_json(ref: str):
    result = subprocess.run(["git", "show", f"{ref}:{CFG}"],
                            capture_output=True, text=True, cwd=str(REPO))
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def main() -> int:
    try:
        import targets
        head = _git_json("HEAD")        # committed version
        staged = _git_json(":")         # staged (index) version
        if head is None or staged is None:
            return 0                    # new file / first commit / not staged -> nothing to lock
        if "unlock" in staged:
            print(f"WARN check-elcv-targets: locked-target override present "
                  f"('unlock': {staged['unlock']!r}); change allowed.")
            return 0
        violations = targets.lock_violations(head, staged)
    except Exception as exc:            # never block a commit on a bug in the gate itself
        print(f"WARN check-elcv-targets skipped (tool error: {exc})")
        return 0

    if not violations:
        return 0
    print("FAIL check-elcv-targets: a LOCKED ELCV target was eroded")
    for v in violations:
        print(f"  BLOCK {v}")
    print("WHY: locked targets (2B whole-repo / 28M ranklab / 5M aegis / 2B ceiling) are firm, "
          "agent-proof commitments; they may be raised but never lowered/removed (the "
          "Codex 28M->5M incident).")
    print('UNBLOCK: if this is truly intended, add a top-level  "unlock": "<reason>"  to '
          f"{CFG}, commit, then remove it.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
