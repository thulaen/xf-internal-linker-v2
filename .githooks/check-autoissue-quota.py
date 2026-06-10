#!/usr/bin/env python3
"""Run the hard AutoIssue and paper-trail quota checks.

This gate is the sole enforcer of the session-gate-aware AutoIssue +
paper-trail quotas (it superseded the now-removed ``check-registry-read`` /
``check-paper-trail-read`` gates), using the session-gate-aware
interface: it reads ``audit/session_gate_state.json`` for the session type
and passes ``--hard --session-type <type>`` to the verifiers. For a ``docs``
session both verifiers return "no quota required" and the gate passes.

"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_STATE = REPO_ROOT / "audit" / "session_gate_state.json"
_VALID_SESSION_TYPES = ("docs", "infrastructure", "reconciliation", "feature")

DOCKER_DOWN_MESSAGE = (
    "FAIL quota: cannot verify (Docker down). "
    "UNBLOCK: start Docker Desktop and re-run."
)


def _session_type() -> str:
    """Read the session type from the gate state, defaulting to 'feature'.

    Defaulting to the strictest real quota ('feature') is fail-safe: if the
    gate state is missing or malformed we demand the full quota rather than
    silently waving the commit through.
    """
    try:
        state = json.loads(GATE_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "feature"
    session_type = state.get("session_type", "feature")
    return session_type if session_type in _VALID_SESSION_TYPES else "feature"


def main() -> int:
    session_type = _session_type()

    # Hard quota gates — these block the commit.
    for label, command_parts in (
        ("AutoIssue quota", ("verify_autoissue_quota", "--hard",
                             "--session-type", session_type)),
        ("paper-trail quota", ("verify_paper_trail_quota", "--hard",
                              "--session-type", session_type)),
    ):
        code = _run_management_command(label, command_parts)
        if code == 3:
            print(DOCKER_DOWN_MESSAGE, file=sys.stderr)
            return 2
        if code != 0:
            print(f"FAIL quota: {label} did not pass.", file=sys.stderr)
            return 2
    return 0


def _run_management_command(label: str, command_parts: tuple[str, ...]) -> int:
    command = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", *command_parts,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return 3
    _relay_output(result)
    return result.returncode


def _relay_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
